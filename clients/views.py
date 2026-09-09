"""
Vues API voyageurs (cf. Saintex.rtf §4).

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

from .models import PreferenceChangeLog, Position
from .serializers import PositionInSerializer, UtilisateurPreferencesSerializer


class PositionPollView(APIView):
    """POST /api/positions/ — reçoit la position envoyée par le client toutes
    les 6h (cf. §4). Met aussi à jour Utilisateur.last_seen_at, utilisé par
    le futur watchdog de relance (§6) pour détecter le silence > 7h.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PositionInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        utilisateur = request.user
        Position.objects.create(utilisateur=utilisateur, point=serializer.to_point())
        utilisateur.last_seen_at = timezone.now()
        utilisateur.save(update_fields=["last_seen_at"])

        # Pas de corps de réponse : la détection de zone à risque et la
        # décision de notification (§6) ne sont pas encore implémentées ;
        # le client n'a de toute façon rien à faire de la réponse (§4 :
        # "aucune notification générée localement").
        return Response(status=status.HTTP_201_CREATED)


class MePreferencesView(APIView):
    """GET/PATCH /api/me/ — écran "préférences de notification" (§4).

    Chaque changement effectif sur un champ tracé est journalisé dans
    PreferenceChangeLog (§5), un par champ modifié.
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
