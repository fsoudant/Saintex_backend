"""
Vues API voyageurs (cf. saintex-spec-technique.md §4 et §5).

Couvre l'inscription (création du compte et remise du jeton API, ou code de
vérification par email pour un compte existant), le contact du téléphone avec
le serveur (cache, rapports d'alerte, état de santé de l'appli) et la
lecture/mise à jour des préférences et du contrat.
"""

import logging

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from risks.cache import cache_mondial_courant

from .inscription import EnvoiCodeEchoue, inscrire_ou_recuperer, masquer_email, verifier_code
from .models import PreferenceChangeLog
from .notifications import verifier_protection_appli
from .rapports import enregistrer_rapports
from .serializers import (
    CacheRequestSerializer,
    InscriptionSerializer,
    UtilisateurContratSerializer,
    UtilisateurPreferencesSerializer,
    VerificationCodeSerializer,
)
from .throttles import InscriptionThrottle, VerificationThrottle

logger = logging.getLogger(__name__)


class EnvoiCodeImpossible(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Impossible d'envoyer le code de vérification pour le moment. Réessayez dans quelques minutes."
    default_code = "envoi_code_impossible"


class InscriptionView(APIView):
    """POST /api/inscription/ — premier lancement : crée le compte du voyageur et
    lui remet son jeton API (cf. clients.inscription).

    - Aucun compte ne correspond à l'email ni au téléphone : 201 avec
      `{"api_token": ...}`. Le consentement RGPD est obligatoire (`consent: true`)
      et horodaté côté serveur.
    - Un compte existe déjà : 202 avec `{"verification_requise": true,
      "reference": ..., "email_masque": ...}`. Un code à six chiffres est envoyé à
      l'email du compte ; il s'échange contre un nouveau jeton via
      POST /api/inscription/verifier/. Les préférences saisies ne modifient pas le
      compte existant.

    Sans authentification (il n'y a pas encore de jeton) ; limité par adresse IP.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [InscriptionThrottle]

    def post(self, request):
        serializer = InscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        maintenant = timezone.now()
        try:
            utilisateur, code = inscrire_ou_recuperer(serializer.validated_data, maintenant)
        except EnvoiCodeEchoue:
            raise EnvoiCodeImpossible()

        if code is None:
            return Response({"api_token": utilisateur.api_token}, status=status.HTTP_201_CREATED)
        return Response(
            {
                "verification_requise": True,
                "reference": str(code.reference),
                "email_masque": masquer_email(utilisateur.email),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class InscriptionVerifierView(APIView):
    """POST /api/inscription/verifier/ — échange le code reçu par email (avec la
    `reference` de l'inscription) contre un NOUVEAU jeton API ; l'ancien est
    révoqué. Tout échec (code faux, périmé, épuisé) renvoie la même erreur 400.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = [VerificationThrottle]

    def post(self, request):
        serializer = VerificationCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        utilisateur = verifier_code(
            serializer.validated_data["reference"], serializer.validated_data["code"], timezone.now()
        )
        if utilisateur is None:
            raise ValidationError({"code": ["Code incorrect ou expiré."]})
        return Response({"api_token": utilisateur.api_token})


class CacheView(APIView):
    """POST /api/cache/ — contact du téléphone avec le serveur (cf.
    saintex-spec-technique.md §4 et §5, révision d'octobre 2026 : la détection
    se fait sur le téléphone, à partir d'un cache fourni par le serveur).

    Aucune position n'est transmise : le cache est MONDIAL et identique pour
    tous les téléphones (cf. risks.cache). La requête peut porter, tous champs
    facultatifs :
    - `cache_version` : la version du cache déjà détenue ;
    - `sante` : l'état de santé de l'appli (permissions de localisation « Toujours »
      et de notifications) — une protection dégradée pendant le contrat vaut au
      voyageur un SMS (et un email), au plus une fois par jour (§8) ;
    - `rapports` : les rapports d'alerte affichées par le téléphone depuis le dernier
      contact (cf. clients.rapports) ; chaque nouvelle alerte d'entrée déclenche
      un SMS court de sauvegarde (option B du §8).

    Met à jour `last_contact_at` (relance "appli silencieuse", §8) et renvoie :
    - `contrat` : dates de début et d'expiration, pour que le téléphone reste
      muet avant/après, même hors ligne (§6) ;
    - `cache` : toutes les zones à risque avec leurs recommandations (cf.
      risks.cache pour le format). Si le client envoie la version qu'il détient
      déjà et qu'elle est identique, `cache` se réduit à
      `{"version": ..., "inchange": true}` — cas le plus fréquent ;
    - `rapports_recus` : identifiants des rapports enregistrés (ou déjà connus),
      que le téléphone peut retirer de sa file d'attente ;
    - `preferences` : les préférences que le téléphone applique lui-même, puisque
      c'est lui qui affiche les alertes — pour l'instant le délai de rappel d'un
      séjour prolongé en zone à risque (`reminder_delay`).

    Le serveur ne reçoit donc plus la position du voyageur (§7, §9).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CacheRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donnees = serializer.validated_data

        maintenant = timezone.now()
        utilisateur = request.user
        utilisateur.last_contact_at = maintenant
        champs = ["last_contact_at"]
        sante = donnees.get("sante")
        if sante is not None:
            utilisateur.localisation_toujours = sante["localisation_toujours"]
            utilisateur.notifications_autorisees = sante["notifications_autorisees"]
            utilisateur.sante_declaree_le = maintenant
            champs += ["localisation_toujours", "notifications_autorisees", "sante_declaree_le"]
        utilisateur.save(update_fields=champs)

        rapports_recus = enregistrer_rapports(utilisateur, donnees.get("rapports", []), maintenant)
        if sante is not None:
            verifier_protection_appli(utilisateur, maintenant)

        cache = cache_mondial_courant()
        if serializer.validated_data.get("cache_version") == cache["version"]:
            cache = {"version": cache["version"], "inchange": True}

        debut = utilisateur.contract_start_date
        expiration = utilisateur.contract_expiry_date
        return Response({
            "contrat": {
                "debut": debut.isoformat() if debut else None,
                "expiration": expiration.isoformat() if expiration else None,
            },
            "cache": cache,
            "rapports_recus": rapports_recus,
            "preferences": {"reminder_delay": utilisateur.reminder_delay},
        })


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
