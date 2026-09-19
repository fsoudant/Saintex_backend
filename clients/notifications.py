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
    return VaccinationRisque.objects.filter(
        utilisateur=utilisateur, risque=risque, vaccine=True
    ).exists()


def _composer_message(endemie, utilisateur, type_notification):
    """Compose le texte transmis, figé au moment de l'envoi (cf.
    NotificationLog.message). Utilise la conduite à tenir validée par
    l'équipe médicale ; la mention de modulation vaccinale reste un
    placeholder explicite (cf. spec §8 "à valider avec l'équipe médicale").
    """
    conduite = endemie.conduite_a_tenir
    risque = conduite.risque
    recommandation = conduite.recommandation_fr or risque.nature_du_risque_fr

    if type_notification == NotificationLog.TypeNotification.RAPPEL_ZONE:
        entete = f"[Rappel] Vous êtes toujours en zone à risque : {risque.libelle_fr}."
    else:
        entete = f"Vous entrez dans une zone à risque : {risque.libelle_fr}."

    message = f"{entete} {recommandation}".strip()

    if _est_vaccine(utilisateur, risque):
        # TODO(validation médicale, cf. spec §8) : formulation à faire
        # rédiger et valider par l'équipe médicale avant toute mise en
        # production — cette mention n'est qu'un placeholder fonctionnel
        # pour que le circuit "modulation, pas suppression" soit testable.
        message += (
            " [TODO validation médicale] Vous avez déclaré être vacciné·e "
            "contre ce risque — cette alerte reste valable pour les autres "
            "mesures de prévention."
        )

    return message


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
