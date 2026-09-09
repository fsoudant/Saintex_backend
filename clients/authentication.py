"""Authentification API des voyageurs, par jeton opaque (Utilisateur.api_token).

Volontairement distincte de rest_framework.authtoken (qui suppose un
django.contrib.auth.User) : les voyageurs ne sont pas des comptes Django
(cf. docstring de clients.models). Le client mobile envoie l'en-tête :

    Authorization: Bearer <api_token>

reçu une fois pour toutes à l'inscription (onboarding, cf. Saintex.rtf §4).
"""

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import Utilisateur


class UtilisateurTokenAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword:
            return None  # pas de tentative d'authentification par ce schéma

        if len(auth) != 2:
            raise AuthenticationFailed("En-tête Authorization malformé (attendu: 'Bearer <token>').")

        token = auth[1].decode("utf-8")
        try:
            utilisateur = Utilisateur.objects.get(api_token=token)
        except Utilisateur.DoesNotExist:
            raise AuthenticationFailed("Jeton invalide.")

        # (utilisateur, auth) : DRF place utilisateur dans request.user, ce
        # qui suffit à permissions.IsAuthenticated grâce à la propriété
        # Utilisateur.is_authenticated (cf. clients.models).
        return (utilisateur, token)

    def authenticate_header(self, request):
        return "Bearer"
