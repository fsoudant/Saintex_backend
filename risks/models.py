"""
Modèles du domaine "risques infectieux" pour Saintex.

Reprend le modèle métier existant côté médical (base MariaDB historique),
refondu en octobre 2026 (cf. saintex-spec-technique.md §7 et §8) :
un Risque (ex. Paludisme) porte sa description et UNE SEULE recommandation ;
une Modulation est une phrase courte et facultative qui précise le contexte
(milieu rural, altitude...) et la période de l'année concernée ; une ligne
Endemie active un Risque, avec sa Modulation éventuelle, sur une Zone
géographique (une ligne = une zone + un risque + une période de validité).
"""

from django.contrib.gis.db import models as gis_models
from django.core.exceptions import ValidationError
from django.db import models

from .richtext import sanitize_html

MOIS_CHOICES = [
    (1, "Janvier"), (2, "Février"), (3, "Mars"), (4, "Avril"),
    (5, "Mai"), (6, "Juin"), (7, "Juillet"), (8, "Août"),
    (9, "Septembre"), (10, "Octobre"), (11, "Novembre"), (12, "Décembre"),
]


class Zone(models.Model):
    """Pure géométrie — aucune notion de risque ici.

    Les polygones sont délimités par des critères écologiques/environnementaux
    (altitude, hydrographie, couvert végétal...), pas par les frontières
    administratives. Précision cible : de l'ordre du kilomètre.
    """

    source_id = models.IntegerField(
        unique=True,
        help_text="id d'origine dans la base MariaDB historique, conservé pour traçabilité",
    )
    nom = models.CharField(max_length=256)
    geom = gis_models.MultiPolygonField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
        help_text="Nul pour les zones sans géométrie exploitable à l'import (cf. note)",
    )
    note = models.CharField(
        max_length=256,
        blank=True,
        help_text="Anomalie constatée à l'import (géométrie manquante ou tronquée)",
    )
    pays = models.ForeignKey(
        "Pays",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="zones_frontiere",
        help_text=(
            "Renseigné uniquement pour les Zone qui portent la frontière "
            "administrative d'un pays (issues des anciens placeholders "
            "'zone_XX') — nul pour les zones de risque écologiques."
        ),
    )

    class Meta:
        indexes = [models.Index(fields=["source_id"])]

    def __str__(self):
        return self.nom


class Risque(models.Model):
    """Catalogue de base des maladies/risques (ex. Paludisme, Dengue...)."""

    code = models.CharField(max_length=10, primary_key=True)  # ex. "PAL", "CHI"
    libelle_fr = models.CharField(max_length=256)
    libelle_en = models.CharField(max_length=256)
    nature_du_risque_fr = models.TextField(
        help_text="Description du mécanisme du risque (ex. mode de transmission)"
    )
    nature_du_risque_en = models.TextField()
    recommandation_fr = models.TextField(
        blank=True,
        help_text=(
            "Recommandation unique du risque (texte enrichi validé par l'équipe "
            "médicale), identique pour tous les voyageurs et toutes les zones "
            "(cf. spec §8)."
        ),
    )
    recommandation_en = models.TextField(blank=True)

    # Métadonnées d'affichage héritées du back-office existant
    ordre = models.IntegerField(null=True, blank=True, help_text="Ordre d'affichage suggéré")
    couleur_legende = models.CharField(max_length=30, null=True, blank=True)
    legende_fr = models.CharField(max_length=100, blank=True)
    legende_en = models.CharField(max_length=100, blank=True)
    lien_fr = models.URLField(null=True, blank=True)
    lien_en = models.URLField(null=True, blank=True)

    vaccin_disponible = models.BooleanField(
        default=False,
        help_text=(
            "Information indicative : un vaccin existe-t-il pour ce risque ? "
            "Faux notamment pour le paludisme (PAL), qui n'a pas de vaccin. "
            "N'intervient plus dans les notifications depuis l'abandon du "
            "questionnaire vaccinal (octobre 2026)."
        ),
    )

    # Texte affiché pour les zones sans risque actif (ex. recommandations
    # vaccinales de base même hors zone à risque)
    cat_zones_saines_fr = models.TextField(blank=True)
    cat_zones_saines_en = models.TextField(blank=True)
    legende_zones_saines_fr = models.CharField(max_length=256, blank=True)
    legende_zones_saines_en = models.CharField(max_length=256, blank=True)

    class Meta:
        ordering = ["ordre", "code"]

    def __str__(self):
        return self.libelle_fr

    def save(self, *args, **kwargs):
        # Les recommandations sont du texte enrichi (HTML limité, cf.
        # risks.richtext) : assaini à chaque écriture, quelle qu'en soit la
        # source (admin, import legacy, shell), pour que ce qui est en base
        # soit toujours sûr à afficher et à envoyer. Un texte brut encore
        # reçu (import legacy) est converti en HTML au passage.
        self.recommandation_fr = sanitize_html(self.recommandation_fr)
        self.recommandation_en = sanitize_html(self.recommandation_en)
        super().save(*args, **kwargs)


class Modulation(models.Model):
    """Phrase de modulation d'un risque et période de l'année concernée
    (ex. « Le risque est majoré si vous séjournez en milieu rural. »).

    Ex-ConduiteATenir (octobre 2026) : ne porte plus ni le risque, ni la
    description, ni la recommandation, ni la légende, ni la couleur — tout
    cela vit désormais sur `Risque`. Catalogue indépendant du risque : une
    même modulation (« en milieu rural », « Pas de données »...) peut être
    partagée par les endémies de risques différents.
    """

    code = models.CharField(max_length=30, primary_key=True)  # ex. "P_T3_A"
    modulation_fr = models.TextField(
        blank=True,
        help_text=(
            "Phrase qui précise le contexte du risque (ex. « Le risque est majoré "
            "si vous séjournez en milieu rural. », « Le risque est réduit "
            "au-dessus de 1500 mètres d'altitude »)."
        ),
    )
    modulation_en = models.TextField(blank=True)

    saison_mois_debut = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=MOIS_CHOICES,
        help_text=(
            "Mois de début de la période à risque (ex. rec_fr mentionnant "
            "'d'août à novembre'). Vide = risque non saisonnier, actif toute "
            "l'année. À renseigner avec saison_mois_fin, jamais seul."
        ),
    )
    saison_mois_fin = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=MOIS_CHOICES,
        help_text=(
            "Mois de fin de la période à risque (inclus). Peut être inférieur à "
            "saison_mois_debut pour une période à cheval sur le nouvel an "
            "(ex. 'd'octobre à février' → début=10, fin=2)."
        ),
    )

    def clean(self):
        super().clean()
        debut_vide = self.saison_mois_debut is None
        fin_vide = self.saison_mois_fin is None
        if debut_vide != fin_vide:
            raise ValidationError(
                "saison_mois_debut et saison_mois_fin doivent être renseignés "
                "ensemble, ou tous les deux laissés vides (risque non saisonnier)."
            )

    def is_in_season(self, when):
        """True si la date/datetime `when` tombe dans la période à risque
        saisonnière de cette modulation.

        Toujours True si aucune saisonnalité n'est définie (risque actif
        toute l'année). Gère les périodes à cheval sur le nouvel an (ex.
        octobre → février) : le test se fait uniquement sur le mois, sans
        tenir compte de l'année ni du jour.
        """
        if self.saison_mois_debut is None or self.saison_mois_fin is None:
            return True
        mois = when.month
        if self.saison_mois_debut <= self.saison_mois_fin:
            return self.saison_mois_debut <= mois <= self.saison_mois_fin
        return mois >= self.saison_mois_debut or mois <= self.saison_mois_fin

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(saison_mois_debut__isnull=True, saison_mois_fin__isnull=True)
                    | models.Q(saison_mois_debut__isnull=False, saison_mois_fin__isnull=False)
                ),
                name="modulation_saison_mois_ensemble",
            ),
        ]

    def __str__(self):
        return self.code


class Endemie(models.Model):
    """Active un Risque sur une Zone, avec une Modulation éventuelle.

    Une ligne = une zone. Le "N zones" d'une même endémie s'obtient par
    plusieurs lignes partageant le même risque et la même modulation (et
    généralement la même période) — pas par une relation many-to-many.

    Note : date_debut/date_fin portent la période de VALIDITÉ de cet
    enregistrement (audit/historisation), pas la saisonnalité intra-annuelle
    du risque — celle-ci est portée par la Modulation liée (mois de début /
    de fin) ; sans modulation, l'endémie est active toute l'année.
    """

    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="endemies")
    risque = models.ForeignKey(Risque, on_delete=models.PROTECT, related_name="endemies")
    modulation = models.ForeignKey(
        Modulation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="endemies",
        help_text=(
            "Précision facultative du risque (milieu rural, altitude...) et "
            "période de l'année concernée ; vide = risque actif toute l'année, "
            "sans précision."
        ),
    )
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(
        null=True, blank=True, help_text="Nul = période en cours (pas de fin connue)"
    )
    zone_exclue = gis_models.MultiPolygonField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
        help_text=(
            "Zone géographique où ce risque précis est absent malgré la Zone "
            "englobante (ex. une ville épargnée par le paludisme). Remplace "
            "l'ancien mécanisme ZoneSaine : porté ici plutôt que sur Zone "
            "elle-même, car une même Zone peut porter plusieurs risques et "
            "l'exclusion ne concerne généralement qu'un seul d'entre eux."
        ),
    )

    class Meta:
        indexes = [
            models.Index(fields=["zone", "date_fin"]),
            models.Index(fields=["risque"], name="risks_endem_risque_idx"),
            models.Index(fields=["modulation"], name="risks_endem_modul_idx"),
        ]

    def __str__(self):
        return f"{self.zone.nom} — {self.risque_id}"


class Pays(models.Model):
    """Référentiel pays — utilisé pour le tunnel de paiement (sélection des
    pays visités, cf. §6 de la spec) et relié à la Zone qui porte sa
    frontière administrative (cf. Zone.pays), pour détecter l'entrée dans
    le pays et déclencher le contrat.

    Les champs de synthèse par maladie (CHIK, CHOLE, PALU...) proviennent
    tels quels de la base historique ; leur nomenclature ne correspond pas
    aux codes de `Risque` (ex. CHIK ↔ CHI, PALU ↔ PAL) — conservés en l'état
    dans `risques_synthese` plutôt que reliés automatiquement, pour ne pas
    forcer un mapping incertain. À normaliser plus tard si besoin.
    """

    source_id = models.IntegerField(unique=True, help_text="uid d'origine MariaDB")
    code = models.CharField(max_length=30, unique=True, help_text="Code pays (souvent ISO 3166-1 alpha-2 ; quelques entrées historiques utilisent un libellé complet, ex. Galápagos)")
    libelle_fr = models.CharField(max_length=256)
    libelle_en = models.CharField(max_length=256)

    # Utile pour centrer/cadrer une carte de sélection de pays
    box_so_lat = models.FloatField(null=True, blank=True)
    box_so_long = models.FloatField(null=True, blank=True)
    box_ne_lat = models.FloatField(null=True, blank=True)
    box_ne_long = models.FloatField(null=True, blank=True)
    center = gis_models.PointField(geography=True, srid=4326, null=True, blank=True)

    # Bulletin d'alerte ponctuel, saisi par l'équipe médicale
    flash_fr = models.TextField(blank=True, null=True)
    flash_en = models.TextField(blank=True, null=True)

    risques_synthese = models.JSONField(
        default=dict,
        blank=True,
        help_text="Champs hérités tels quels de la base historique (CHIK, PALU, FJ_*, ZIKA...)",
    )

    class Meta:
        verbose_name_plural = "Pays"

    def __str__(self):
        return self.libelle_fr
