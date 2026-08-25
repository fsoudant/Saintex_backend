"""
Modèles du domaine "risques infectieux" pour Saintex.

Reprend le modèle métier existant côté médical (base MariaDB historique) :
un Risque de base (ex. Paludisme), décliné en plusieurs ConduiteATenir
("risque modulé" — variantes contextuelles avec leur propre recommandation),
elles-mêmes activées sur des Zone géographiques via des lignes Endemie
(chaque ligne = une zone + une conduite à tenir + une période de validité).
"""

from django.contrib.gis.db import models as gis_models
from django.db import models


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

    # Métadonnées d'affichage héritées du back-office existant
    ordre = models.IntegerField(null=True, blank=True, help_text="Ordre d'affichage suggéré")
    couleur_legende = models.CharField(max_length=30, null=True, blank=True)
    legende_fr = models.CharField(max_length=100, blank=True)
    legende_en = models.CharField(max_length=100, blank=True)
    lien_fr = models.URLField(null=True, blank=True)
    lien_en = models.URLField(null=True, blank=True)

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


class ConduiteATenir(models.Model):
    """Recommandation associée à un Risque, avec une variante contextuelle
    ("risque modulé" — ex. saison, zone rurale, durée du séjour...).
    """

    code = models.CharField(max_length=30, primary_key=True)  # ex. "P_T3_A"
    risque = models.ForeignKey(Risque, on_delete=models.PROTECT, related_name="conduites")
    nature_du_risque_fr = models.TextField(
        help_text="Description du niveau/contexte de risque pour cette variante"
    )
    nature_du_risque_en = models.TextField()
    recommandation_fr = models.TextField(
        blank=True, help_text="Conduite à tenir affichée à l'utilisateur (texte validé médical)"
    )
    recommandation_en = models.TextField(blank=True)
    legende_fr = models.CharField(max_length=256, blank=True)
    legende_en = models.CharField(max_length=256, blank=True)
    couleur = models.CharField(max_length=30, null=True, blank=True)

    def __str__(self):
        return self.code


class Endemie(models.Model):
    """Active une ConduiteATenir sur une Zone, pendant une période donnée.

    Une ligne = une zone. Le "N zones" d'une même endémie s'obtient par
    plusieurs lignes partageant la même conduite à tenir (et généralement
    la même période) — pas par une relation many-to-many.

    Note : date_debut/date_fin portent la période de VALIDITÉ de cet
    enregistrement (audit/historisation), pas la saisonnalité intra-annuelle
    du risque — celle-ci est actuellement uniquement textuelle, dans la
    ConduiteATenir liée (ex. "risque d'août à novembre").
    """

    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="endemies")
    conduite_a_tenir = models.ForeignKey(
        ConduiteATenir, on_delete=models.PROTECT, related_name="endemies"
    )
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(
        null=True, blank=True, help_text="Nul = période en cours (pas de fin connue)"
    )

    class Meta:
        indexes = [
            models.Index(fields=["zone", "date_fin"]),
            models.Index(fields=["conduite_a_tenir"]),
        ]

    def __str__(self):
        return f"{self.zone.nom} — {self.conduite_a_tenir_id}"


class Pays(models.Model):
    """Référentiel pays — utilisé pour le tunnel de paiement (sélection des
    pays visités, cf. §6 de la spec) et pour situer les ZoneSaine.

    Les champs de synthèse par maladie (CHIK, CHOLE, PALU...) proviennent
    tels quels de la base historique ; leur nomenclature ne correspond pas
    aux codes de `Risque` (ex. CHIK ↔ CHI, PALU ↔ PAL) — conservés en l'état
    dans `risques_synthese` plutôt que reliés automatiquement, pour ne pas
    forcer un mapping incertain. À normaliser plus tard si besoin.
    """

    source_id = models.IntegerField(unique=True, help_text="uid d'origine MariaDB")
    code = models.CharField(max_length=10, unique=True, help_text="Code pays (souvent ISO 3166-1 alpha-2)")
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

    def __str__(self):
        return self.libelle_fr


class ZoneSaine(models.Model):
    """Exception ponctuelle ("trou") dans une Zone endémique : un point précis
    (le plus souvent une ville) où un risque donné est absent, alors même que
    la Zone qui l'englobe est marquée à risque pour ce même risque.

    Exemple réel : Bombay est exempte de paludisme bien que la zone
    géographique qui l'entoure soit à risque.
    """

    source_id = models.IntegerField(unique=True)
    libelle_fr = models.CharField(max_length=256)
    libelle_en = models.CharField(max_length=256, blank=True, null=True)
    point = gis_models.PointField(geography=True, srid=4326)

    conduite_a_tenir = models.ForeignKey(
        ConduiteATenir,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="zones_saines",
        help_text="Risque neutralisé en ce point ; nul si l'exception n'est pas encore renseignée",
    )
    zone = models.ForeignKey(
        Zone,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="zones_saines",
        help_text="Zone endémique dans laquelle ce point fait exception",
    )
    pays = models.ForeignKey(
        Pays,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="zones_saines",
    )

    def __str__(self):
        return self.libelle_fr
