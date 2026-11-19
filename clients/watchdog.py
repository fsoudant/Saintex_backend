"""
Watchdog "appli silencieuse" (cf. saintex-spec-technique.md §8) — Phase 4 du
moteur de notification, suite de clients.notifications (Phase 3, qui décide
et envoie mais ne détecte pas elle-même le silence).

Détecte les utilisateurs dont `last_contact_at` dépasse le seuil de silence et
déclenche `notifications.envoyer_relance_silence` pour chacun. Le seuil de la
PROCHAINE relance se déduit de la dernière relance déjà envoyée sur ce cycle
de silence, en interrogeant directement `NotificationLog` — pas de compteur
ni de champ dédié à ajouter au modèle : c'est le journal probatoire (§7) qui
sert aussi de mémoire au watchdog, avec la garantie qu'il ne peut pas se
désynchroniser du journal réellement envoyé.

Seuils (cf. config/settings.py, variables SAINTEX_SILENCE_* du .env) : la spec
fixe 7 h puis une relance toutes les 6 h, indéfiniment, ce qui suppose que le
téléphone contacte le serveur toutes les 6 h. Or, sans notification silencieuse
(APNs, qui exige un compte Apple Developer), iOS ne réveille l'appli que sur un
déplacement : un voyageur immobile plusieurs jours, appli parfaitement saine,
serait relancé à tort. Tant que ce signal de vie manque, on allonge les seuils et
on plafonne le nombre de relances (ex. 48 h, puis 24 h, 3 relances au plus).

Une relance n'a de sens que pendant le contrat : avant la date de départ ou
après l'expiration, l'appli est volontairement muette (§6), et un voyageur qui a
désinstallé l'appli après son voyage ne doit pas être relancé indéfiniment.

Destiné à être appelé périodiquement (Render Cron Job, ou LaunchDaemon sur le Mac
de démo, cf. DEPLOY.md « Cas D ») via la commande `manage.py
watchdog_relance_silence`.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import NotificationLog, Utilisateur
from .notifications import _contrat_actif as contrat_actif
from .notifications import envoyer_relance_silence


def delai_premiere_relance():
    return timedelta(hours=settings.SAINTEX_SILENCE_PREMIERE_RELANCE_H)


def delai_relances_suivantes():
    return timedelta(hours=settings.SAINTEX_SILENCE_RELANCES_SUIVANTES_H)


def max_relances():
    """Nombre maximal de relances par cycle de silence ; 0 = illimité (spec)."""
    return settings.SAINTEX_SILENCE_MAX_RELANCES


def _prochaine_echeance(utilisateur):
    """Date à partir de laquelle cet utilisateur doit recevoir sa prochaine
    relance, si son silence se prolonge jusque-là ; None si le plafond de
    relances du cycle est atteint.

    Ne considère que les relances envoyées DEPUIS `last_contact_at` : une
    relance plus ancienne appartient à un cycle de silence précédent, clos
    par un check-in depuis (last_contact_at a alors été remis à jour), et ne
    doit pas influencer le cycle en cours.
    """
    relances = utilisateur.notifications.filter(
        type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
        sent_at__gte=utilisateur.last_contact_at,
    )
    plafond = max_relances()
    # Une relance journalise une ligne par canal actif ; le SMS est toujours actif
    # (§8) : il sert à compter les relances elles-mêmes.
    if plafond and relances.filter(canal=NotificationLog.Canal.SMS).count() >= plafond:
        return None

    derniere_relance = relances.order_by("-sent_at").first()
    if derniere_relance is None:
        return utilisateur.last_contact_at + delai_premiere_relance()
    return derniere_relance.sent_at + delai_relances_suivantes()


def utilisateurs_en_silence(moment=None):
    """Utilisateurs dont l'échéance de relance (cf. `_prochaine_echeance`)
    est atteinte à `moment` (défaut : maintenant), pendant leur contrat.

    Filtre d'abord grossièrement en base (silence total > premier seuil, pour
    limiter le nombre de lignes à examiner) puis calcule l'échéance exacte en
    Python par utilisateur — acceptable au volume actuel (prototype) ; à revoir
    si la base d'utilisateurs grossit significativement (cf. is_in_season, même
    logique de filtre Python assumé pour les mêmes raisons de simplicité).
    """
    moment = moment or timezone.now()
    aujourdhui = timezone.localtime(moment).date()

    candidats = Utilisateur.objects.filter(
        last_contact_at__isnull=False,
        last_contact_at__lte=moment - delai_premiere_relance(),
    )

    en_silence = []
    for utilisateur in candidats:
        if not contrat_actif(utilisateur, aujourdhui):
            continue
        echeance = _prochaine_echeance(utilisateur)
        if echeance is not None and moment >= echeance:
            en_silence.append(utilisateur)
    return en_silence


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
