"""
Vues API voyageurs (cf. saintex-spec-technique.md §4).

Ne couvre pour l'instant que le polling de position et la lecture/mise à
jour des préférences de notification. L'inscription (création du compte
Utilisateur et remise du jeton API lors de l'onboarding) n'est volontairement
pas traitée ici : elle est liée au consentement RGPD explicite (§7), dont le
parcours exact reste à définir avant de coder l'endpoint correspondant.
"""

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from risks.detection import zones_actives_pour_point

from .models import PreferenceChangeLog, UserRiskZoneStatus
from .notifications import envoyer_alerte_entree, envoyer_rappel_si_echeance
from .serializers import (
    PositionInSerializer,
    UtilisateurContratSerializer,
    UtilisateurPreferencesSerializer,
)


class PositionPollView(APIView):
    """POST /api/positions/ — reçoit la position envoyée par le client toutes
    les 6h (cf. §4). Met à jour Utilisateur.last_contact_at (utilisé par le
    watchdog de relance, §8, pour détecter le silence > 7h) et détecte les
    zones à risque actives à cette position (§7/§8) pour maintenir
    UserRiskZoneStatus à jour.

    La position reçue n'est jamais persistée (cf. §7, minimisation
    maximale) : elle ne sert qu'au calcul ci-dessous, puis est écartée.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PositionInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        utilisateur = request.user
        point = serializer.to_point()

        utilisateur.last_contact_at = timezone.now()
        utilisateur.save(update_fields=["last_contact_at"])

        for endemie in zones_actives_pour_point(point):
            statut_zone, cree = UserRiskZoneStatus.objects.get_or_create(
                utilisateur=utilisateur, endemie=endemie
            )
            if cree:
                # Nouvelle zone détectée pour cet utilisateur : alerte
                # d'entrée (§8), envoyée une seule fois grâce à
                # get_or_create ci-dessus.
                envoyer_alerte_entree(utilisateur, statut_zone, point)
            else:
                # Zone déjà active : notifier seulement si l'échéance de
                # reminder_delay est atteinte depuis le dernier rappel (§8).
                envoyer_rappel_si_echeance(utilisateur, statut_zone, point)

        # Pas de corps de réponse : le client n'a de toute façon rien à
        # faire de la réponse (§4 : "aucune notification générée
        # localement", toutes les alertes proviennent du serveur).
        return Response(status=status.HTTP_201_CREATED)


class MePreferencesView(APIView):
    """GET/PATCH /api/me/ — écran "préférences de notification" (§4).

    Chaque changement effectif sur un champ tracé est journalisé dans
    PreferenceChangeLog (§7), un par champ modifié.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UtilisateurPreferencesSerializer(request.user).data)

    def patch(self, request):
        utilisateur = request.user
        avant = {
            champ: getattr(utilisateur, champ) for champ in PreferenceChangeLog.CHAMPS_TRACES
        }

        serializer = UtilisateurPreferencesSerializer(utilisateur, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        for champ, ancienne_valeur in avant.items():
            PreferenceChangeLog.enregistrer(
                utilisateur=utilisateur,
                champ=champ,
                ancienne_valeur=str(ancienne_valeur),
                nouvelle_valeur=str(getattr(utilisateur, champ)),
            )

        return Response(serializer.data)


class MeContratView(APIView):
    """GET/PATCH /api/me/contrat/ — écran de gestion du contrat (cf.
    saintex-spec-technique.md §6). Seule `contract_start_date` est
    modifiable, et seulement tant que le contrat n'a pas démarré (cf.
    UtilisateurContratSerializer.validate_contract_start_date). Contrairement
    à MePreferencesView, les changements ne sont pas journalisés dans
    PreferenceChangeLog : ce journal est réservé aux préférences de
    notification (§7), pas au contrat.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UtilisateurContratSerializer(request.user).data)

    def patch(self, request):
        serializer = UtilisateurContratSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
