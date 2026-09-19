"""
Watchdog "appli silencieuse" (cf. saintex-spec-technique.md §8) — Phase 4 du
moteur de notification, suite de clients.notifications (Phase 3, qui décide
et envoie mais ne détecte pas elle-même le silence).

Détecte les utilisateurs dont `last_contact_at` dépasse le seuil de silence
(7h, puis relances toutes les 6h, indéfiniment) et déclenche
`notifications.envoyer_relance_silence` pour chacun. Le seuil de la
PROCHAINE relance se déduit de la dernière relance déjà envoyée sur ce cycle
de silence, en interrogeant directement `NotificationLog` — pas de compteur
ni de champ dédié à ajouter au modèle : c'est le journal probatoire (§7) qui
sert aussi de mémoire au watchdog, avec la garantie qu'il ne peut pas se
désynchroniser du journal réellement envoyé.

Destiné à être appelé périodiquement par un Render Cron Job (cf. spec §8,
qui remplace ici la mention initiale de Celery Beat — décision actée) via la
commande `manage.py watchdog_relance_silence`.
"""

from datetime import timedelta

from django.utils import timezone

from .models import NotificationLog, Utilisateur
from .notifications import envoyer_relance_silence

DELAI_PREMIERE_RELANCE = timedelta(hours=7)
DELAI_RELANCES_SUIVANTES = timedelta(hours=6)


def _prochaine_echeance(utilisateur):
    """Date à partir de laquelle cet utilisateur doit recevoir sa prochaine
    relance, si son silence se prolonge jusque-là.

    Ne considère que les relances envoyées DEPUIS `last_contact_at` : une
    relance plus ancienne appartient à un cycle de silence précédent, clos
    par un check-in depuis (last_contact_at a alors été remis à jour), et ne
    doit pas influencer le cycle en cours.
    """
    derniere_relance = (
        utilisateur.notifications.filter(
            type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
            sent_at__gte=utilisateur.last_contact_at,
        )
        .order_by("-sent_at")
        .first()
    )
    if derniere_relance is None:
        return utilisateur.last_contact_at + DELAI_PREMIERE_RELANCE
    return derniere_relance.sent_at + DELAI_RELANCES_SUIVANTES


def utilisateurs_en_silence(moment=None):
    """Utilisateurs dont l'échéance de relance (cf. `_prochaine_echeance`)
    est atteinte à `moment` (défaut : maintenant).

    Filtre d'abord grossièrement en base (silence total > 7h, pour limiter
    le nombre de lignes à examiner) puis calcule l'échéance exacte en Python
    par utilisateur — acceptable au volume actuel (prototype) ; à revoir si
    la base d'utilisateurs grossit significativement (cf. is_in_season, même
    logique de filtre Python assumé pour les mêmes raisons de simplicité).
    """
    moment = moment or timezone.now()

    candidats = Utilisateur.objects.filter(
        last_contact_at__isnull=False,
        last_contact_at__lte=moment - DELAI_PREMIERE_RELANCE,
    )

    return [u for u in candidats if moment >= _prochaine_echeance(u)]


def traiter_relances_silence(moment=None):
    """Point d'entrée du watchdog (§8) : envoie une relance à chaque
    utilisateur en silence dont l'échéance est atteinte, et renvoie la liste
    des utilisateurs notifiés. Idempotent à l'échelle d'un même run : deux
    appels rapprochés ne dupliquent pas l'envoi tant que l'échéance
    suivante n'est pas encore atteinte (cf. `_prochaine_echeance`)."""
    moment = moment or timezone.now()

    notifies = []
    for utilisateur in utilisateurs_en_silence(moment):
        envoyer_relance_silence(utilisateur, moment=moment)
        notifies.append(utilisateur)
    return notifies
