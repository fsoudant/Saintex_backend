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

import logging
from datetime import timedelta

from django.utils import timezone

from .models import NotificationLog, Utilisateur, VaccinationRisque

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

    def send(self, destinataire, message):
        raise NotImplementedError


class _LoggingSender(NotificationSender):
    """Implémentation "stub" commune aux trois canaux — seul le préfixe de
    log change, pour distinguer les canaux dans les logs en attendant un
    vrai prestataire par canal."""

    def __init__(self, label):
        self.label = label

    def send(self, destinataire, message):
        logger.info("%s (stub, non transmis) → %s : %s", self.label, destinataire, message)
        return True


SENDERS = {
    NotificationLog.Canal.SMS: _LoggingSender("SMS"),
    NotificationLog.Canal.EMAIL: _LoggingSender("Email"),
    NotificationLog.Canal.PUSH: _LoggingSender("Push"),
}


def _est_vaccine(utilisateur, risque):
    """Cf. Utilisateur.voyage_en_famille : même requête, sémantique différente
    selon le profil — "cet utilisateur est vacciné" pour un individuel, "tous
    les membres de la famille sont protégés" pour un voyageur en famille.
    C'est _composer_recommandation qui applique la bonne lecture ; cette
    fonction se contente de lire la déclaration brute."""
    return VaccinationRisque.objects.filter(
        utilisateur=utilisateur, risque=risque, vaccine=True
    ).exists()


def _composer_recommandation(conduite, utilisateur):
    """Texte de conduite à tenir pour cette conduite/cet utilisateur (cf.
    saintex-spec-technique.md §8, décision réunion médicale) :

    - individuel protégé (vacciné) -> recommandation_protege_fr
    - individuel non protégé -> recommandation_non_protege_fr
    - famille, "tous protégés" déclaré -> recommandation_protege_fr (comme un
      individuel protégé : toute la famille est couverte)
    - famille, "tous protégés" non déclaré -> message composite couvrant les
      deux cas, faute de savoir qui précisément dans la famille est protégé
      ("Pour les membres non protégés contre X, ... Pour les membres
      protégés, ...")

    Tant que recommandation_protege_fr n'est pas rédigé par l'équipe médicale
    pour une conduite donnée, on retombe sur recommandation_non_protege_fr :
    jamais de texte vide envoyé, et la modulation vaccinale ne fait jamais
    disparaître l'alerte (cf. decisions-and-principles).
    """
    risque = conduite.risque
    non_protege = conduite.recommandation_non_protege_fr or risque.nature_du_risque_fr
    protege = conduite.recommandation_protege_fr or non_protege

    tous_proteges = _est_vaccine(utilisateur, risque)

    if utilisateur.voyage_en_famille and not tous_proteges:
        return (
            f"Pour les membres non protégés contre {risque.libelle_fr}, {non_protege} "
            f"Pour les membres protégés, {protege}"
        ).strip()

    return protege if tous_proteges else non_protege


def _composer_message(endemie, utilisateur, type_notification):
    """Compose le texte transmis, figé au moment de l'envoi (cf.
    NotificationLog.message). La conduite à tenir varie selon la couverture
    vaccinale déclarée et le profil individuel/famille de l'utilisateur (cf.
    _composer_recommandation) — texte validé par l'équipe médicale dans les
    deux cas, jamais de placeholder non validé (cf. spec §8).
    """
    conduite = endemie.conduite_a_tenir
    risque = conduite.risque
    recommandation = _composer_recommandation(conduite, utilisateur)

    if type_notification == NotificationLog.TypeNotification.RAPPEL_ZONE:
        entete = f"[Rappel] Vous êtes toujours en zone à risque : {risque.libelle_fr}."
    else:
        entete = f"Vous entrez dans une zone à risque : {risque.libelle_fr}."

    return f"{entete} {recommandation}".strip()


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


def _envoyer(utilisateur, message, type_notification, endemie=None, point=None):
    """Envoi générique, commun aux trois types de notification (alerte/rappel
    de zone, relance silence) : compose une entrée NotificationLog par canal
    actif pour cet utilisateur. `endemie`/`point` restent nuls pour une
    relance_silence, qui ne porte par définition ni zone ni position
    (cf. NotificationLog.endemie/position, et spec §7)."""
    logs = []
    for canal, destinataire in _canaux_actifs(utilisateur):
        ok = SENDERS[canal].send(destinataire, message)
        logs.append(
            NotificationLog.objects.create(
                utilisateur=utilisateur,
                type_notification=type_notification,
                endemie=endemie,
                position=point,
                message=message,
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
    message = _composer_message(endemie, utilisateur, NotificationLog.TypeNotification.ALERTE_ZONE)
    return _envoyer(
        utilisateur, message, NotificationLog.TypeNotification.ALERTE_ZONE, endemie=endemie, point=point
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
    message = _composer_message(endemie, utilisateur, NotificationLog.TypeNotification.RAPPEL_ZONE)
    logs = _envoyer(
        utilisateur, message, NotificationLog.TypeNotification.RAPPEL_ZONE, endemie=endemie, point=point
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
