"""
Modèles du domaine "voyageurs" pour Saintex (cf. saintex-spec-technique.md, §7).

Utilisateur est volontairement séparé de django.contrib.auth.User : un
voyageur ne se connecte jamais à l'admin Django (seule l'équipe médicale/
back-office le fait, via les comptes staff existants). Le séparer évite de
polluer la liste des comptes admin avec potentiellement des milliers de
voyageurs, et permet une authentification API dédiée et minimale (jeton
opaque), sans mot de passe ni notion de session web.
"""

import calendar
import secrets

from django.contrib.gis.db import models as gis_models
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# Valeur d'amorçage pour ParametreContrat.horizon_max_mois (cf. classe
# ci-dessous) : sert de default au champ modèle et de secours si la ligne de
# config n'existe pas encore (première migration). La valeur qui compte en
# fonctionnement normal est celle stockée en base, éditable depuis l'admin
# sans déploiement — cf. §6, "6 à 12 mois" non arrêté précisément au PV de
# réunion.
CONTRACT_START_DATE_MAX_MONTHS_AHEAD = 12


class ParametreContrat(models.Model):
    """Singleton de paramétrage métier pour le contrat (cf. §6) — permet à
    l'équipe (médicale/business) d'ajuster l'horizon max de
    `contract_start_date` depuis l'admin, sans nouveau déploiement, tant que
    le chiffre exact ("6 à 12 mois") n'est pas figé avec le co-fondateur
    médical. Une seule ligne existe en pratique (pk=1, cf. get_solo()).
    """

    horizon_max_mois = models.PositiveSmallIntegerField(
        default=CONTRACT_START_DATE_MAX_MONTHS_AHEAD,
        help_text=(
            "Horizon maximal (en mois) auquel un utilisateur peut fixer sa "
            "date de début de contrat (cf. §6 — \"6 à 12 mois\", chiffre exact "
            "non arrêté au PV de réunion)."
        ),
    )

    class Meta:
        verbose_name = "Paramétrage du contrat"
        verbose_name_plural = "Paramétrage du contrat"

    def __str__(self):
        return f"Horizon max de début de contrat : {self.horizon_max_mois} mois"

    def save(self, *args, **kwargs):
        self.pk = 1  # force le singleton, quelle que soit la façon dont l'objet a été instancié
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Le singleton ne doit jamais disparaître : valider_date_debut_contrat
        # en dépend à chaque appel (cf. get_solo()).
        pass

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def _ajouter_mois(date_ref, mois):
    """Ajoute `mois` mois calendaires à `date_ref`, sans dépendance externe
    (dateutil n'est pas dans les paquets du projet, cf. tools-and-environment).
    Cale le jour sur le dernier jour du mois cible si nécessaire (ex. 31
    janvier + 1 mois -> 28/29 février)."""
    mois_total = date_ref.month - 1 + mois
    annee = date_ref.year + mois_total // 12
    mois_resultat = mois_total % 12 + 1
    jour = min(date_ref.day, calendar.monthrange(annee, mois_resultat)[1])
    return date_ref.replace(year=annee, month=mois_resultat, day=jour)


def valider_date_debut_contrat(ancienne_valeur, nouvelle_valeur, aujourdhui=None, horizon_max_mois=None):
    """Valide un changement de Utilisateur.contract_start_date (cf.
    saintex-spec-technique.md §6, décision réunion médicale) :

    - la date ne doit pas être dans le passé ;
    - elle ne doit pas dépasser l'horizon défini par ParametreContrat (éditable
      en admin, cf. classe ci-dessus) à l'avance ;
    - si une date était déjà fixée et que "aujourd'hui" l'a atteinte ou
      dépassée, le contrat a démarré effectivement et la date n'est plus
      modifiable (validation rule actée : "editable while date_actuelle <
      contract_start_date").

    Fonction libre (pas une méthode d'instance) pour rester appelable aussi
    bien depuis Utilisateur.clean() que depuis le serializer DRF, sans
    dupliquer la règle. `horizon_max_mois` est surchargeable explicitement
    (tests, appels spécifiques) ; par défaut lu depuis ParametreContrat.get_solo().
    Ne renvoie rien ; lève ValidationError si invalide.
    """
    aujourdhui = aujourdhui or timezone.localdate()
    if horizon_max_mois is None:
        horizon_max_mois = ParametreContrat.get_solo().horizon_max_mois

    if ancienne_valeur is not None and nouvelle_valeur != ancienne_valeur and aujourdhui >= ancienne_valeur:
        raise ValidationError(
            "Le contrat a déjà démarré : la date de début n'est plus modifiable."
        )
    if nouvelle_valeur < aujourdhui:
        raise ValidationError("La date de début de contrat ne peut pas être dans le passé.")
    borne_max = _ajouter_mois(aujourdhui, horizon_max_mois)
    if nouvelle_valeur > borne_max:
        raise ValidationError(
            "La date de début de contrat ne peut pas être fixée à plus de "
            f"{horizon_max_mois} mois à l'avance."
        )


def generate_api_token():
    """Jeton opaque (32 octets, hex) remis au client mobile lors de
    l'onboarding et envoyé sur chaque requête d'API (cf. authentication.py).
    """
    return secrets.token_hex(32)


class Utilisateur(models.Model):
    """Compte voyageur (cf. saintex-spec-technique.md §7 "Utilisateur").

    Le téléphone est obligatoire car le SMS est le seul canal garanti sans
    connexion data (cf. §8) et n'est pas désactivable — il n'y a donc pas de
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
            "implémentée (dépend du moteur de notification, cf. §8) : la "
            "valeur ci-dessus n'est pour l'instant qu'un défaut global à "
            "l'inscription, modifiable ensuite par l'utilisateur."
        ),
    )

    voyage_en_famille = models.BooleanField(
        default=False,
        help_text=(
            "Question \"voyagez-vous en famille ?\" posée à l'inscription "
            "(cf. §8, décision réunion médicale). Si True, la couverture "
            "vaccinale déclarée par risque (VaccinationRisque.vaccine) se lit "
            "comme \"tous les membres de la famille sont protégés contre ce "
            "risque\" plutôt que \"cet utilisateur est vacciné\" — cf. "
            "clients/notifications.py, _composer_recommandation."
        ),
    )

    subscription_status = models.CharField(
        max_length=20, choices=StatutAbonnement.choices, default=StatutAbonnement.ESSAI
    )

    contract_duration = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Durée du contrat en mois, choisie à l'achat (1, 2, 3...)",
    )

    purchased_at = models.DateTimeField(
        null=True, blank=True, help_text="Horodatage de l'achat"
    )

    contract_start_date = models.DateField(
        null=True,
        blank=True,
        help_text=(
            "Date de début du contrat, fixée par l'utilisateur lui-même à "
            "l'achat (cf. saintex-spec-technique.md §6 — la sélection de pays "
            "comme déclencheur d'activation a été abandonnée au profit d'une "
            "date déclarée). Modifiable tant que cette date n'est pas encore "
            "arrivée ; figée dès que le contrat démarre effectivement (cf. "
            "contrat_demarre / valider_date_debut_contrat)."
        ),
    )

    last_contact_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Horodatage seul (aucune position associée) du dernier check-in "
            "reçu — sert uniquement à déclencher la relance \"appli silencieuse\" "
            "(cf. saintex-spec-technique.md §8)."
        ),
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

    @property
    def contract_expiry_date(self):
        """Date d'expiration du contrat (début + durée, cf. §6 : "Expiration =
        date de déclenchement + durée choisie"), ou None tant que l'une des
        deux informations n'est pas encore renseignée."""
        if self.contract_start_date is None or self.contract_duration is None:
            return None
        return _ajouter_mois(self.contract_start_date, self.contract_duration)

    @property
    def contrat_demarre(self):
        """True si le contrat a effectivement démarré (date de début atteinte
        ou dépassée — cf. §6 : le compteur démarre le jour même, pas
        seulement après)."""
        if self.contract_start_date is None:
            return False
        return timezone.localdate() >= self.contract_start_date

    def clean(self):
        super().clean()
        if self.contract_start_date is not None:
            ancienne_valeur = None
            if self.pk:
                ancienne_valeur = (
                    Utilisateur.objects.filter(pk=self.pk)
                    .values_list("contract_start_date", flat=True)
                    .first()
                )
            if ancienne_valeur != self.contract_start_date:
                valider_date_debut_contrat(ancienne_valeur, self.contract_start_date)

    def __str__(self):
        return self.email


class PushToken(models.Model):
    """Un jeton push par device (un voyageur peut avoir plusieurs
    téléphones/réinstallations) — cf. saintex-spec-technique.md §7, champ push_tokens.
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


class PreferenceChangeLog(models.Model):
    """Traçabilité de chaque changement de préférence (cf. saintex-spec-technique.md §7) :
    utilisateur, champ modifié, ancienne/nouvelle valeur, horodatage.
    """

    # Liste fermée des champs traçables, pour éviter d'y glisser n'importe
    # quel nom de champ par erreur depuis le code appelant.
    CHAMPS_TRACES = ("email_active", "push_active", "reminder_delay", "voyage_en_famille")

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


class VaccinationRisque(models.Model):
    """Couverture vaccinale déclarée d'un voyageur pour un Risque donné.

    Simple booléen : vacciné / non vacciné. N'a de sens que pour les risques
    disposant d'un vaccin (Risque.vaccin_disponible=True) — le paludisme
    (PAL), qui n'a pas de vaccin, ne peut donc jamais avoir d'entrée ici : la
    règle est imposée structurellement par clean() ci-dessous, pas seulement
    par convention dans l'admin.

    Objectif : ne pas notifier un voyageur déjà protégé lorsqu'il entre dans
    une zone à risque pour laquelle il est vacciné — à exploiter côté moteur
    de notification (cf. saintex-spec-technique.md §8). Ne suppose jamais
    l'alerte : elle en module uniquement le contenu (texte protégé vs non
    protégé, cf. ConduiteATenir.recommandation_protege_fr/recommandation_non_protege_fr).

    Cf. Utilisateur.voyage_en_famille : pour un voyageur en famille, `vaccine`
    se lit comme "tous les membres de la famille sont protégés contre ce
    risque" plutôt que "cet utilisateur est vacciné" (cf. décision réunion
    médicale, §8) — même champ, sémantique contextuelle selon le profil.
    """

    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE, related_name="vaccinations"
    )
    risque = models.ForeignKey(
        "risks.Risque", on_delete=models.CASCADE, related_name="vaccinations_utilisateurs"
    )
    vaccine = models.BooleanField(
        default=False, help_text="True = voyageur vacciné/protégé pour ce risque"
    )
    declared_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "risque"], name="une_entree_vaccination_par_risque"
            ),
        ]
        verbose_name = "Couverture vaccinale"
        verbose_name_plural = "Couvertures vaccinales"

    def clean(self):
        super().clean()
        if self.risque_id and not self.risque.vaccin_disponible:
            raise ValidationError(
                f"« {self.risque} » n'a pas de vaccin disponible "
                "(Risque.vaccin_disponible=False) — la couverture vaccinale n'a pas "
                "de sens pour ce risque."
            )

    def save(self, *args, **kwargs):
        # full_clean() (et pas juste clean()) pour que la règle tienne aussi
        # depuis une future création via l'API mobile, pas seulement via les
        # formulaires admin qui appellent full_clean() automatiquement.
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        statut = "vacciné" if self.vaccine else "non vacciné"
        return f"{self.utilisateur.email} / {self.risque.code} : {statut}"


class UserRiskZoneStatus(models.Model):
    """État courant d'une zone à risque active pour un utilisateur
    (cf. saintex-spec-technique.md §7 "UserRiskZoneStatus") — permet de
    savoir si une alerte d'entrée a déjà été envoyée pour cette zone, et
    quand déclencher le prochain rappel de séjour prolongé (§8).

    Référence une Endemie (zone + conduite à tenir + période de validité)
    plutôt que la seule Zone géométrique : une même Zone peut porter
    plusieurs risques actifs simultanément (ex. paludisme et encéphalite à
    tiques sur une même zone géographique), et c'est bien un risque précis
    — pas la géométrie seule — qui doit être suivi/notifié individuellement.

    Ne stocke jamais de coordonnées GPS (cf. §7 : "référence à la zone,
    jamais de coordonnées GPS") — seul NotificationLog conserve une
    position, et uniquement au moment d'un envoi effectif.
    """

    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE, related_name="zones_actives"
    )
    endemie = models.ForeignKey(
        "risks.Endemie", on_delete=models.CASCADE, related_name="utilisateurs_actifs"
    )
    entered_at = models.DateTimeField(
        auto_now_add=True, help_text="Première détection d'entrée dans cette zone à risque"
    )
    last_reminded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Dernier rappel envoyé pour cette zone (séjour prolongé) — sert à "
            "calculer le prochain rappel selon Utilisateur.reminder_delay (§8)"
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["utilisateur", "endemie"], name="un_statut_par_utilisateur_et_endemie"
            ),
        ]
        verbose_name = "Statut de zone à risque"
        verbose_name_plural = "Statuts de zone à risque"

    def __str__(self):
        return f"{self.utilisateur.email} @ {self.endemie}"


class NotificationLog(models.Model):
    """Journal de toute notification effectivement envoyée à un voyageur
    (cf. saintex-spec-technique.md §7 "NotificationLog") — conservé à des
    fins probatoires (§9), durée de rétention à valider avec un juriste/DPO.

    Seule table du domaine "clients" qui conserve une position GPS, et
    uniquement au moment d'un envoi effectif — la position brute du check-in
    n'est jamais persistée ailleurs (cf. §7 : minimisation maximale, calcul
    en mémoire puis position écartée ; seul UserRiskZoneStatus garde une
    trace, sans coordonnées). `message` est un texte figé au moment de
    l'envoi (pas une référence vivante à la ConduiteATenir, qui peut évoluer
    ensuite) : ce qui compte en cas de contentieux, c'est ce qui a
    réellement été transmis.
    """

    class TypeNotification(models.TextChoices):
        ALERTE_ZONE = "alerte_zone", "Alerte entrée en zone à risque"
        RAPPEL_ZONE = "rappel_zone", "Rappel de séjour prolongé"
        RELANCE_SILENCE = "relance_silence", "Relance appli silencieuse"

    class Canal(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        PUSH = "push", "Push"

    class Statut(models.TextChoices):
        EN_ATTENTE = "pending", "En attente"
        ENVOYE = "sent", "Envoyé"
        ECHEC = "failed", "Échec"

    utilisateur = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE, related_name="notifications"
    )
    type_notification = models.CharField(max_length=20, choices=TypeNotification.choices)
    endemie = models.ForeignKey(
        "risks.Endemie",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Renseigné pour alerte_zone/rappel_zone, nul pour relance_silence",
    )
    position = gis_models.PointField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
        help_text=(
            "Position ayant déclenché la notification (alerte/rappel de zone). "
            "Nulle pour une relance_silence, qui ne porte par définition aucune "
            "position (c'est justement l'absence de contact qui la déclenche)."
        ),
    )
    message = models.TextField(help_text="Texte effectivement transmis, figé au moment de l'envoi")
    destinataire = models.CharField(
        max_length=255, help_text="Email ou numéro de téléphone, figé au moment de l'envoi"
    )
    canal = models.CharField(max_length=10, choices=Canal.choices)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.EN_ATTENTE)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["utilisateur", "-sent_at"]),
        ]
        ordering = ["-sent_at"]
        verbose_name = "Journal de notification"
        verbose_name_plural = "Journal des notifications"

    def __str__(self):
        return f"{self.utilisateur.email} — {self.get_type_notification_display()} ({self.canal}, {self.statut})"
