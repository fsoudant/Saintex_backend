"""
Décision et envoi des notifications (cf. saintex-spec-technique.md §8) —
Phase 3 du moteur de notification, suite de risks.detection (Phase 2, qui se
contente de détecter les zones actives) et des modèles clients (Phase 1).

Sépare volontairement la DÉCISION (quoi envoyer, à qui, sur quel canal) de
l'ENVOI (comment l'acheminer réellement) : le choix des prestataires SMS et
email (Brevo pressenti côté email, cf. spec §10 "Points encore ouverts")
n'est pas encore arrêté. Les `NotificationSender` ci-dessous ne sont donc,
pour l'instant, que des implémentations "stub" qui journalisent et simulent
un envoi réussi — un branchement réel (Brevo, etc.) remplacera uniquement
`SENDERS`, sans toucher à la logique de décision.
"""

import html
import logging
from datetime import timedelta

from django.utils import timezone

from risks.richtext import html_to_text, sanitize_html

from .models import NotificationLog, Utilisateur

logger = logging.getLogger("saintex.notifications")

# Mapping Utilisateur.DelaiRappel -> délai avant le prochain rappel de
# séjour prolongé (cf. spec §7/§8). None = pas de rappel après l'alerte
# d'entrée initiale ("une fois").
DELAI_RAPPEL = {
    Utilisateur.DelaiRappel.UNE_FOIS: None,
    Utilisateur.DelaiRappel.QUOTIDIEN: timedelta(days=1),
    Utilisateur.DelaiRappel.DEUX_JOURS: timedelta(days=2),
    Utilisateur.DelaiRappel.HEBDOMADAIRE: timedelta(weeks=1),
}


class NotificationSender:
    """Interface d'envoi pour un canal donné. Cf. docstring du module : tant
    qu'aucun prestataire n'est choisi, les implémentations se contentent de
    journaliser et de simuler un succès."""

    def send(self, destinataire, message, message_html=None):
        """`message` : texte brut (tous les canaux). `message_html` : version
        mise en forme, transmise uniquement au canal email (SMS, push et
        notification locale n'affichent pas de HTML)."""
        raise NotImplementedError


class _LoggingSender(NotificationSender):
    """Implémentation "stub" commune aux trois canaux — seul le préfixe de
    log change, pour distinguer les canaux dans les logs en attendant un
    vrai prestataire par canal."""

    def __init__(self, label):
        self.label = label

    def send(self, destinataire, message, message_html=None):
        logger.info("%s (stub, non transmis) → %s : %s", self.label, destinataire, message)
        return True


SENDERS = {
    NotificationLog.Canal.SMS: _LoggingSender("SMS"),
    NotificationLog.Canal.EMAIL: _LoggingSender("Email"),
    NotificationLog.Canal.PUSH: _LoggingSender("Push"),
}


def _composer_recommandation_html(conduite):
    """Texte de conduite à tenir transmis au voyageur, en HTML assaini (texte
    enrichi : gras, italique, taille, liens hypertexte — cf. risks.richtext
    et saintex-spec-technique.md §8) : un texte unique par conduite à tenir,
    identique pour tous les voyageurs. La modulation selon une couverture
    vaccinale déclarée (et le profil famille) a été abandonnée en octobre
    2026 : ces déclarations ne sont pas fiables (cf. decisions-and-principles).

    Si la recommandation n'est pas encore rédigée par l'équipe médicale, on
    retombe sur la description du risque (texte brut, converti en HTML) :
    jamais de texte vide envoyé. `sanitize_html` est réappliqué ici par
    défense en profondeur (un `update()` en base contourne ConduiteATenir.save).
    """
    return sanitize_html(conduite.recommandation_fr) or sanitize_html(
        conduite.risque.nature_du_risque_fr
    )


def _composer_message(endemie, type_notification):
    """Compose le message transmis, figé au moment de l'envoi (cf.
    NotificationLog.message / message_html) : en-tête (entrée ou rappel) +
    conduite à tenir validée par l'équipe médicale (cf. spec §8).

    Retourne (texte_brut, html) : le texte brut sert au SMS, au push et à la
    notification locale (liens réduits à « texte (url) ») ; le HTML, à l'email.
    """
    conduite = endemie.conduite_a_tenir
    risque = conduite.risque
    recommandation_html = _composer_recommandation_html(conduite)
    recommandation = html_to_text(recommandation_html)

    if type_notification == NotificationLog.TypeNotification.RAPPEL_ZONE:
        entete = f"[Rappel] Vous êtes toujours en zone à risque : {risque.libelle_fr}."
    else:
        entete = f"Vous entrez dans une zone à risque : {risque.libelle_fr}."

    separateur = "\n" if "\n" in recommandation else " "
    texte = f"{entete}{separateur}{recommandation}".strip()
    message_html = f"<p><strong>{html.escape(entete, quote=False)}</strong></p>{recommandation_html}"
    return texte, message_html


def _canaux_actifs(utilisateur):
    """Canaux sur lesquels notifier cet utilisateur, avec le destinataire à
    journaliser pour chacun (cf. spec §8 : SMS toujours actif, email/push
    opt-in). Le push n'est proposé que si au moins un device est enregistré
    — sinon il n'y a nulle part où l'envoyer."""
    canaux = [(NotificationLog.Canal.SMS, utilisateur.phone)]
    if utilisateur.email_active:
        canaux.append((NotificationLog.Canal.EMAIL, utilisateur.email))
    if utilisateur.push_active and utilisateur.push_tokens.exists():
        canaux.append((NotificationLog.Canal.PUSH, utilisateur.email))
    return canaux


def _composer_message_relance_silence(utilisateur, moment):
    """Texte de relance "appli silencieuse" (§8) — générique, sans référence
    à une zone ou un risque (cohérent avec endemie=None sur ce type de log) :
    l'absence de contact ne présuge d'aucune zone à risque particulière."""
    heures = int((moment - utilisateur.last_contact_at).total_seconds() // 3600)
    return (
        f"Nous n'avons plus de nouvelles de votre position depuis {heures} h. "
        "Merci d'ouvrir l'application Saintex pour confirmer que tout va bien."
    )


def _envoyer(utilisateur, message, type_notification, endemie=None, point=None, message_html=""):
    """Envoi générique, commun aux trois types de notification (alerte/rappel
    de zone, relance silence) : compose une entrée NotificationLog par canal
    actif pour cet utilisateur. `endemie`/`point` restent nuls pour une
    relance_silence, qui ne porte par définition ni zone ni position
    (cf. NotificationLog.endemie/position, et spec §7). `message_html`
    (texte enrichi) n'est transmis et journalisé que pour le canal email."""
    logs = []
    for canal, destinataire in _canaux_actifs(utilisateur):
        html_canal = message_html if canal == NotificationLog.Canal.EMAIL else ""
        ok = SENDERS[canal].send(destinataire, message, html_canal or None)
        logs.append(
            NotificationLog.objects.create(
                utilisateur=utilisateur,
                type_notification=type_notification,
                endemie=endemie,
                position=point,
                message=message,
                message_html=html_canal,
                destinataire=destinataire,
                canal=canal,
                statut=NotificationLog.Statut.ENVOYE if ok else NotificationLog.Statut.ECHEC,
            )
        )
    return logs


def envoyer_alerte_entree(utilisateur, statut_zone, point):
    """Alerte d'entrée en zone à risque (§8) — à déclencher une fois, à la
    création du UserRiskZoneStatus (nouvelle zone détectée pour cet
    utilisateur)."""
    endemie = statut_zone.endemie
    message, message_html = _composer_message(endemie, NotificationLog.TypeNotification.ALERTE_ZONE)
    return _envoyer(
        utilisateur, message, NotificationLog.TypeNotification.ALERTE_ZONE,
        endemie=endemie, point=point, message_html=message_html,
    )


def envoyer_rappel_si_echeance(utilisateur, statut_zone, point, moment=None):
    """Rappel de séjour prolongé (§8), uniquement si l'échéance de
    `reminder_delay` est atteinte depuis le dernier rappel (ou depuis
    l'entrée si aucun rappel n'a encore été envoyé). Ne rattrape pas les
    échéances manquées en rafale : au plus un rappel par appel, et
    `last_reminded_at` est réaligné sur `moment` (pas sur l'échéance
    théorique), pour repartir sur un délai plein à partir de maintenant."""
    moment = moment or timezone.now()

    delai = DELAI_RAPPEL[utilisateur.reminder_delay]
    if delai is None:
        return []

    reference = statut_zone.last_reminded_at or statut_zone.entered_at
    if moment - reference < delai:
        return []

    endemie = statut_zone.endemie
    message, message_html = _composer_message(endemie, NotificationLog.TypeNotification.RAPPEL_ZONE)
    logs = _envoyer(
        utilisateur, message, NotificationLog.TypeNotification.RAPPEL_ZONE,
        endemie=endemie, point=point, message_html=message_html,
    )
    statut_zone.last_reminded_at = moment
    statut_zone.save(update_fields=["last_reminded_at"])
    return logs


def envoyer_relance_silence(utilisateur, moment=None):
    """Relance "appli silencieuse" (§8) — ne porte ni zone ni position, cf.
    NotificationLog.endemie/position (nuls pour ce type). Le déclenchement
    (seuil de 7h puis relances toutes les 6h) est décidé en amont par
    clients.watchdog ; cette fonction ne fait qu'envoyer et journaliser,
    comme envoyer_alerte_entree/envoyer_rappel_si_echeance ci-dessus."""
    moment = moment or timezone.now()
    message = _composer_message_relance_silence(utilisateur, moment)
    return _envoyer(utilisateur, message, NotificationLog.TypeNotification.RELANCE_SILENCE)
