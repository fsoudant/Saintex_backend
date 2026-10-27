"""
Messages envoyés PAR LE SERVEUR aux voyageurs (cf. saintex-spec-technique.md §8).

Depuis la révision d'octobre 2026, la détection des zones à risque et
l'affichage des alertes et rappels se font sur le TÉLÉPHONE (cache mondial,
§5) : le serveur n'envoie plus lui-même ces alertes. Il envoie uniquement des
messages de service :

- le SMS court de sauvegarde, à chaque alerte d'entrée en zone rapportée par
  le téléphone (option B du §8) ;
- la relance "appli silencieuse" (cf. clients.watchdog) ;
- l'avertissement de protection dégradée (permissions retirées).

Sépare volontairement la DÉCISION (quoi envoyer, à qui, sur quel canal) de
l'ENVOI (comment l'acheminer réellement) : le choix des prestataires SMS et
email (Brevo pressenti côté email) n'est pas encore arrêté. Les
`NotificationSender` ci-dessous ne sont donc, pour l'instant, que des
implémentations "stub" qui journalisent et simulent un envoi réussi — un
branchement réel (Brevo, etc.) remplacera uniquement `SENDERS`, sans toucher
à la logique de décision.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from .models import NotificationLog

logger = logging.getLogger("saintex.notifications")

# SMS court de sauvegarde à chaque alerte d'entrée rapportée par le téléphone
# (option B du §8, tranchée en octobre 2026) : au-delà de ce délai entre
# l'affichage de l'alerte et sa réception, le SMS précise depuis combien de
# temps le voyageur est entré en zone, pour ne pas laisser croire qu'il y est
# encore. Seuil non arrêté au PV (« à définir » dans la spec) : 1 h par défaut.
SEUIL_RETARD_SMS_ALERTE = timedelta(hours=1)

# Protection dégradée (§8) : tant que le voyageur n'a pas rétabli ses permissions,
# on le prévient au plus une fois par ce délai (le téléphone contacte le serveur
# toutes les 6 h : sans ce garde-fou, il recevrait un SMS à chaque contact).
DELAI_RAPPEL_PROTECTION_DEGRADEE = timedelta(days=1)


class NotificationSender:
    """Interface d'envoi pour un canal donné. Cf. docstring du module : tant
    qu'aucun prestataire n'est choisi, les implémentations se contentent de
    journaliser et de simuler un succès."""

    def send(self, destinataire, message, message_html=None):
        """`message` : texte brut (tous les canaux). `message_html` : version
        mise en forme, pour le canal email — inutilisée à ce jour, les
        messages du serveur étant courts et en texte brut."""
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
        f"Nous n'avons plus de nouvelles de votre appli depuis {heures} h. "
        "Merci d'ouvrir l'application Saintex pour confirmer que tout va bien."
    )


def _envoyer(utilisateur, message, type_notification, endemie=None, canaux=None):
    """Envoi générique, commun aux types de message du serveur : compose une
    entrée NotificationLog par canal actif pour cet utilisateur. `endemie`
    n'est renseignée que pour le SMS d'une alerte d'entrée (cf.
    NotificationLog.endemie). `canaux`, si fourni, restreint l'envoi à ces
    canaux (ensemble de NotificationLog.Canal) parmi les canaux actifs de
    l'utilisateur."""
    logs = []
    for canal, destinataire in _canaux_actifs(utilisateur):
        if canaux is not None and canal not in canaux:
            continue
        ok = SENDERS[canal].send(destinataire, message)
        logs.append(
            NotificationLog.objects.create(
                utilisateur=utilisateur,
                type_notification=type_notification,
                endemie=endemie,
                message=message,
                destinataire=destinataire,
                canal=canal,
                statut=NotificationLog.Statut.ENVOYE if ok else NotificationLog.Statut.ECHEC,
            )
        )
    return logs


def envoyer_relance_silence(utilisateur, moment=None):
    """Relance "appli silencieuse" (§8) — ne porte ni zone ni position. Le
    déclenchement (seuil de 7h puis relances toutes les 6h) est décidé en
    amont par clients.watchdog ; cette fonction ne fait qu'envoyer et
    journaliser."""
    moment = moment or timezone.now()
    message = _composer_message_relance_silence(utilisateur, moment)
    return _envoyer(utilisateur, message, NotificationLog.TypeNotification.RELANCE_SILENCE)


def _duree_lisible(duree):
    """« 5 h », « 2 j » : durée arrondie à l'unité inférieure, pour un SMS court."""
    heures = int(duree.total_seconds() // 3600)
    return f"{heures} h" if heures < 48 else f"{heures // 24} j"


def composer_sms_alerte(rapport, moment):
    """SMS court de sauvegarde pour une alerte d'entrée rapportée par le
    téléphone (option B du §8). Reste dans l'alphabet SMS standard (GSM-7 : pas de
    guillemets typographiques, ni d'apostrophe courbe, ni de « ê », « î »...) pour
    tenir en un seul SMS. Le détail de la conduite à tenir reste dans l'appli."""
    endemie = rapport.endemie
    risque = f" ({endemie.conduite_a_tenir.risque.libelle_fr})" if endemie else ""

    retard = moment - rapport.affichee_le
    if retard >= SEUIL_RETARD_SMS_ALERTE:
        debut = f"Saintex : il y a {_duree_lisible(retard)}, vous êtes entré(e) dans une zone à risque{risque}."
    else:
        debut = f"Saintex : vous entrez dans une zone à risque{risque}."
    return f"{debut} Consultez l'application pour la conduite à tenir."


def envoyer_sms_alerte(utilisateur, rapport, moment=None):
    """SMS court envoyé à chaque alerte d'entrée en zone rapportée par le
    téléphone (option B du §8 : filet de sécurité indépendant des permissions
    de notification de l'appli). Les rappels restent locaux, sans SMS. SMS
    uniquement : l'email et le push ne doublent pas l'alerte locale.

    Si le rapport arrive avec retard (téléphone resté hors ligne), le SMS part
    à la réception et précise depuis combien de temps le voyageur est entré en
    zone (cf. SEUIL_RETARD_SMS_ALERTE).
    """
    moment = moment or timezone.now()
    return _envoyer(
        utilisateur,
        composer_sms_alerte(rapport, moment),
        NotificationLog.TypeNotification.ALERTE_ZONE,
        endemie=rapport.endemie,
        canaux={NotificationLog.Canal.SMS},
    )


def _contrat_actif(utilisateur, aujourdhui=None):
    """True si le contrat est en cours : date de début atteinte et expiration
    pas encore atteinte (le téléphone, lui, reste muet avant et après, cf. §6)."""
    aujourdhui = aujourdhui or timezone.localdate()
    debut = utilisateur.contract_start_date
    if debut is None or aujourdhui < debut:
        return False
    expiration = utilisateur.contract_expiry_date
    return expiration is None or aujourdhui < expiration


def _composer_message_protection_degradee(utilisateur):
    causes = []
    if utilisateur.localisation_toujours is False:
        causes.append("localisation en arrière-plan désactivée")
    if utilisateur.notifications_autorisees is False:
        causes.append("notifications désactivées")
    return (
        f"Saintex : votre application ne peut plus vous alerter ({' et '.join(causes)}). "
        "Ouvrez-la et rétablissez l'autorisation pour rester protégé(e)."
    )


def verifier_protection_appli(utilisateur, moment=None):
    """Protection dégradée (§8) : si le téléphone a déclaré que la localisation
    « Toujours » ou les notifications ne sont plus autorisées, l'appli ne peut
    plus alerter le voyageur : on le prévient par SMS (et email s'il est actif).

    - Seul un `False` explicite déclenche l'avertissement : `None` (état jamais
      déclaré, ancienne version de l'appli) ne présume de rien.
    - Uniquement pendant le contrat : avant la date de début (ou après
      expiration) l'appli est volontairement muette, et le premier lancement
      est justement le moment où les permissions sont accordées.
    - Au plus un avertissement par `DELAI_RAPPEL_PROTECTION_DEGRADEE`, déduit
      du dernier NotificationLog de ce type (pas de compteur séparé, comme pour
      la relance "appli silencieuse").
    """
    if utilisateur.localisation_toujours is not False and utilisateur.notifications_autorisees is not False:
        return []
    if not _contrat_actif(utilisateur):
        return []

    moment = moment or timezone.now()
    dernier = (
        NotificationLog.objects.filter(
            utilisateur=utilisateur,
            type_notification=NotificationLog.TypeNotification.PROTECTION_DEGRADEE,
        )
        .order_by("-sent_at")
        .first()
    )
    if dernier is not None and moment - dernier.sent_at < DELAI_RAPPEL_PROTECTION_DEGRADEE:
        return []

    return _envoyer(
        utilisateur,
        _composer_message_protection_degradee(utilisateur),
        NotificationLog.TypeNotification.PROTECTION_DEGRADEE,
        canaux={NotificationLog.Canal.SMS, NotificationLog.Canal.EMAIL},
    )
