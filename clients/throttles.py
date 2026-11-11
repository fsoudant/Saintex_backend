"""Limites de fréquence des endpoints publics (sans jeton) : l'inscription et la
vérification du code. Par adresse IP ; les taux sont dans
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] (config/settings.py).

Deux protections s'y ajoutent, côté clients.inscription : au plus un email de
code par minute et par compte, et cinq essais par code.
"""

from rest_framework.throttling import AnonRateThrottle


class InscriptionThrottle(AnonRateThrottle):
    scope = "inscription"


class VerificationThrottle(AnonRateThrottle):
    scope = "verification"
