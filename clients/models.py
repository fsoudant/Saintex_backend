"""
Modèles du domaine "voyageurs" pour Saintex (cf. Saintex.rtf, §5).

Utilisateur est volontairement séparé de django.contrib.auth.User : un
voyageur ne se connecte jamais à l'admin Django (seule l'équipe médicale/
back-office le fait, via les comptes staff existants). Le séparer évite de
polluer la liste des comptes admin avec potentiellement des milliers de
voyageurs, et permet une authentification API dédiée et minimale (jeton
opaque), sans mot de passe ni notion de session web.
"""

import secrets

from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils import timezone


def generate_api_token():
    """Jeton opaque (32 octets, hex) remis au client mobile lors de
    l'onboarding et envoyé sur chaque requête d'API (cf. authentication.py).
    """
    return secrets.token_hex(32)


class Utilisateur(models.Model):
    """Compte voyageur (cf. Saintex.rtf §5 "Utilisateur").

    Le téléphone est obligatoire car le SMS est le seul canal garanti sans
    connexion data (cf. §6) et n'est pas désactivable — il n'y a donc pas de
    champ "sms_active" symétrique à email_active/push_active.
    """

    class DelaiRappel(models.TextChoices):
        UNE_FOIS = "once", "Une fois"
        QUOTIDIEN = "daily", "Quotidien"
        DEUX_JOURS = "every_2_days", "Tous les 2 jours"
        HEBDOMADAIRE = "weekly", "Hebdomadaire"

    class StatutAbonnement(models.TextChoices):
        # Valeurs volontairement minimales : à affiner une fois le modèle
        # commercial (essai gratuit, paiement, durée...) précisé — le
        # cahier des charges n'entre pas dans le détail (§5 mentionne juste
        # subscription_status sans énumération).
        ESSAI = "trial", "Essai"
        ACTIF = "active", "Actif"
        EXPIRE = "expired", "Expiré"
        ANNULE = "cancelled", "Annulé"

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, unique=True, help_text="Format international (ex. +33...)")

    email_active = models.BooleanField(default=True)
    push_active = models.BooleanField(default=True)

    reminder_delay = models.CharField(
        max_length=20,
        choices=DelaiRappel.choices,
        default=DelaiRappel.QUOTIDIEN,
        help_text=(
            "Délai de rappel en cas de séjour prolongé en zone à risque. "
            "Le cahier des charges prévoit une valeur par défaut suggérée "
            "selon le risque de la zone traversée — logique non encore "
            "implémentée (dépend du moteur de notification, cf. §6) : la "
            "valeur ci-dessus n'est pour l'instant qu'un défaut global à "
            "l'inscription, modifiable ensuite par l'utilisateur."
        ),
    )

    subscription_status = models.CharField(
        max_length=20, choices=StatutAbonnement.choices, default=StatutAbonnement.ESSAI
    )

    last_seen_at = models.DateTimeField(
        null=True, blank=True, help_text="Mis à jour à chaque position reçue (cf. Position)"
    )

    consent_status = models.BooleanField(
        default=False, help_text="Consentement RGPD explicite donné au premier lancement"
    )
    consent_date = models.DateTimeField(null=True, blank=True)

    api_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_api_token,
        editable=False,
        help_text="Jeton d'authentification de l'appli mobile (cf. clients.authentication)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # DRF (permissions.IsAuthenticated) attend cet attribut sur request.user ;
    # Utilisateur n'hérite pas de django.contrib.auth, donc on l'expose ici.
    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        return self.email


class PushToken(models.Model):
    """Un jeton push par device (un voyageur peut avoir plusieurs
    téléphones/réinstallations) — cf. Saintex.rtf §5, champ push_tokens.
    """

    class Plateforme(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name="push_tokens")
    plateforme = models.CharField(max_length=10, choices=Plateforme.choices)
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.utilisateur.email} ({self.plateforme})"


class Position(models.Model):
    """Historique des positions reçues du client (cf. Saintex.rtf §4 : polling
    toutes les 6h, aucune intelligence côté client) et §5 : "à
    minimiser/anonymiser selon la politique de rétention RGPD" — la politique
    de rétention elle-même (purge automatique, anonymisation) n'est pas
    encore implémentée ici, à traiter avec le reste du volet RGPD (§7).
    """

    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name="positions")
    point = gis_models.PointField(geography=True, srid=4326)
    received_at = models.DateTimeField(
        default=timezone.now,
        help_text="Horodatage serveur de réception (pas forcément celui du relevé GPS)",
    )

    class Meta:
        indexes = [
            # Requête clé du futur watchdog (§6) : dernière position connue
            # par utilisateur, pour détecter le silence > 7h.
            models.Index(fields=["utilisateur", "-received_at"]),
        ]
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.utilisateur.email} @ {self.received_at:%Y-%m-%d %H:%M}"


class PreferenceChangeLog(models.Model):
    """Traçabilité de chaque changement de préférence (cf. Saintex.rtf §5) :
    utilisateur, champ modifié, ancienne/nouvelle valeur, horodatage.
    """

    # Liste fermée des champs traçables, pour éviter d'y glisser n'importe
    # quel nom de champ par erreur depuis le code appelant.
    CHAMPS_TRACES = ("email_active", "push_active", "reminder_delay")

    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE, related_name="preference_changes"
    )
    champ = models.CharField(max_length=50)
    ancienne_valeur = models.CharField(max_length=100, blank=True, null=True)
    nouvelle_valeur = models.CharField(max_length=100, blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.utilisateur.email}: {self.champ} → {self.nouvelle_valeur}"

    @classmethod
    def enregistrer(cls, utilisateur, champ, ancienne_valeur, nouvelle_valeur):
        """Crée une entrée si la valeur a réellement changé (no-op sinon)."""
        if champ not in cls.CHAMPS_TRACES:
            raise ValueError(f"Champ non traçable : {champ!r} (attendu parmi {cls.CHAMPS_TRACES})")
        if ancienne_valeur == nouvelle_valeur:
            return None
        return cls.objects.create(
            utilisateur=utilisateur,
            champ=champ,
            ancienne_valeur=ancienne_valeur,
            nouvelle_valeur=nouvelle_valeur,
        )
