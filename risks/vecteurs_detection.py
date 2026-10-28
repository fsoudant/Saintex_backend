"""
Jeu de cas de test PARTAGÉ pour la détection locale (cf.
saintex-spec-technique.md §5, « Détection locale », et §9 « Cohérence des
implémentations »).

La détection de l'entrée en zone à risque existe en trois exemplaires : la
référence Python (risks.cache.endemies_actives_dans_cache) et les modules
natifs Swift et Kotlin. Ce module produit un fichier JSON versionné
(`tests_partages/detection_cache.json`) contenant :

- un petit CACHE de test, au format exact de risks.cache.construire_cache ;
- une liste de CAS (position, instant) avec les identifiants d'endémies
  ATTENDUS, calculés par la référence Python.

Chaque module natif charge ce fichier dans ses tests et vérifie qu'il obtient
exactement les mêmes endémies pour chaque cas. Le fichier se régénère avec
`python manage.py generer_vecteurs_detection` ; un test serveur vérifie qu'il
est à jour (il échoue si la référence ou le jeu de cas ont changé sans
régénération), ce qui empêche le jeu partagé de dériver de la référence.

Le cache de test est écrit à la main (formes simples, identifiants stables),
pas tiré de la base : il couvre précisément les cas délicats —
trou dans un polygone (zone moins zone exclue), polygone non convexe, zone en
plusieurs morceaux disjoints, zone à cheval sur l'antiméridien (deux parties
collées à ±180°), saison à cheval sur le nouvel an, bornes de validité, mois
évalué en UTC, points sur le bord d'un polygone.
"""

import json
from datetime import datetime
from pathlib import Path

from django.conf import settings

from .cache import endemies_actives_dans_cache

VERSION_FORMAT = 1

REGLES = [
    "Coordonnées : [longitude, latitude] en degrés, longitude dans [-180, 180] (ordre GeoJSON).",
    "Les géométries du cache sont des MultiPolygon GeoJSON, avec trous éventuels (anneaux intérieurs) ; une zone à cheval sur l'antiméridien est fournie en deux parties collées à +180 et -180, à tester telles quelles (test planaire, sans recomposition).",
    "Une position est DANS une géométrie si elle est à l'intérieur OU sur son bord (« covers ») ; un point dans un trou est hors de la géométrie. Les cas marqués \"bord\": true testent ce comportement et peuvent être sensibles à l'arithmétique flottante : un module natif doit les réussir, ou documenter explicitement l'écart.",
    "Période de validité : valide_du et valide_au sont des instants ISO 8601, bornes INCLUSES ; une borne nulle signifie « sans limite ».",
    "Saison : saison.debut et saison.fin sont des mois 1-12, bornes incluses ; si debut > fin, la saison est à cheval sur le nouvel an (ex. 11 à 2 = novembre à février).",
    "Le mois évalué est celui de l'instant EXPRIMÉ EN UTC : un instant avec décalage horaire est d'abord converti en UTC.",
    "Une endémie est active si et seulement si : instant dans la période de validité ET mois dans la saison de sa conduite ET position dans sa géométrie.",
    "Le résultat attendu est la liste des identifiants d'endémies actives, dans l'ordre croissant des identifiants.",
]

# --- Cache de test ---------------------------------------------------------

_RISQUE = {"code": "PAL", "libelle_fr": "Paludisme", "libelle_en": "Malaria", "couleur": "rgb(255,0,0)"}


def _conduite(saison, texte):
    return {
        "risque": _RISQUE,
        "saison": saison,
        "recommandation_fr": f"<p>{texte}</p>",
        "recommandation_en": f"<p>{texte} (en)</p>",
    }


def _rect(lon_min, lat_min, lon_max, lat_max):
    return [[lon_min, lat_min], [lon_max, lat_min], [lon_max, lat_max], [lon_min, lat_max], [lon_min, lat_min]]


def _endemie(identifiant, zone_id, conduite, geometrie, valide_du=None, valide_au=None):
    return {
        "id": identifiant,
        "zone_id": zone_id,
        "zone_nom": f"Zone {zone_id}",
        "conduite": conduite,
        "geometrie": geometrie,
        "valide_du": valide_du,
        "valide_au": valide_au,
    }


CACHE_TEST = {
    "version": "vecteurs-test-1",
    "genere_le": "2026-01-01T00:00:00+00:00",
    "rayon_km": None,
    "conduites": {
        "TOUTE_ANNEE": _conduite(None, "Toute l'année"),
        "SAISON_ETE": _conduite({"debut": 6, "fin": 9}, "Juin à septembre"),
        "SAISON_HIVER": _conduite({"debut": 11, "fin": 2}, "Novembre à février"),
    },
    "geometries": {
        # Carré simple.
        "z1": {"type": "MultiPolygon", "coordinates": [[_rect(10, 10, 12, 12)]]},
        # Couronne : carré 20-24 × 10-14 avec un trou 21-23 × 11-13 (zone moins zone exclue).
        "e2": {
            "type": "MultiPolygon",
            "coordinates": [[_rect(20, 10, 24, 14), [[21, 11], [21, 13], [23, 13], [23, 11], [21, 11]]]],
        },
        # À cheval sur l'antiméridien : deux parties collées à +180 et -180.
        "z3": {
            "type": "MultiPolygon",
            "coordinates": [[_rect(179, -19, 180, -17)], [_rect(-180, -19, -179, -17)]],
        },
        # Polygone non convexe en L : 30-34 × 10-12 plus 30-32 × 12-14 (encoche en 32-34 × 12-14).
        "z4": {
            "type": "MultiPolygon",
            "coordinates": [[[[30, 10], [34, 10], [34, 12], [32, 12], [32, 14], [30, 14], [30, 10]]]],
        },
        # Deux morceaux disjoints.
        "z5": {
            "type": "MultiPolygon",
            "coordinates": [[_rect(40, 0, 41, 1)], [_rect(45, 0, 46, 1)]],
        },
    },
    "endemies": [
        _endemie(1, 1, "TOUTE_ANNEE", "z1"),
        _endemie(2, 2, "SAISON_ETE", "e2"),
        _endemie(3, 3, "TOUTE_ANNEE", "z3"),
        _endemie(4, 4, "SAISON_HIVER", "z4"),
        _endemie(5, 5, "TOUTE_ANNEE", "z5", "2026-08-01T00:00:00+00:00", "2026-12-31T23:59:59+00:00"),
        # Deuxième endémie sur la même zone et la même géométrie que la première.
        _endemie(6, 1, "SAISON_ETE", "z1"),
    ],
}

# --- Cas de test : (nom, longitude, latitude, instant, options) ---------------

CAS = [
    ("z1 : centre, en janvier (une seule endémie, toute l'année)", 11, 11, "2026-01-15T12:00:00+00:00", {}),
    ("z1 : centre, en juillet (deux endémies sur la même zone)", 11, 11, "2026-07-15T12:00:00+00:00", {}),
    ("hors de toute zone", 0, 0, "2026-07-15T12:00:00+00:00", {}),
    ("z1 : sur le bord ouest", 10, 11, "2026-01-15T12:00:00+00:00", {"bord": True}),
    ("z1 : sur un coin", 12, 12, "2026-01-15T12:00:00+00:00", {"bord": True}),
    ("z1 : juste à l'extérieur du bord ouest", 9.9999, 11, "2026-01-15T12:00:00+00:00", {}),
    ("z2 : dans la couronne, en saison", 20.5, 12, "2026-07-15T12:00:00+00:00", {}),
    ("z2 : dans le trou, en saison", 22, 12, "2026-07-15T12:00:00+00:00", {}),
    ("z2 : dans la couronne, hors saison", 20.5, 12, "2026-01-15T12:00:00+00:00", {}),
    ("z3 : antiméridien, partie est", 179.5, -18, "2026-01-15T12:00:00+00:00", {}),
    ("z3 : antiméridien, partie ouest", -179.5, -18, "2026-01-15T12:00:00+00:00", {}),
    ("z3 : juste en dehors de la partie est", 178, -18, "2026-01-15T12:00:00+00:00", {}),
    ("z4 : branche basse du L, en saison (décembre)", 33, 11, "2026-12-10T12:00:00+00:00", {}),
    ("z4 : encoche du L, en saison", 33, 13, "2026-12-10T12:00:00+00:00", {}),
    ("z4 : branche haute du L, en saison", 31, 13, "2026-12-10T12:00:00+00:00", {}),
    ("z4 : branche haute du L, hors saison (juillet)", 31, 13, "2026-07-15T12:00:00+00:00", {}),
    ("z4 : saison à cheval sur le nouvel an (janvier)", 31, 13, "2027-01-20T12:00:00+00:00", {}),
    ("z4 : premier jour de la saison (1er novembre)", 33, 11, "2026-11-01T00:00:00+00:00", {}),
    ("z4 : dernier jour de la saison (fin février)", 33, 11, "2027-02-28T23:59:59+00:00", {}),
    ("z4 : premier jour hors saison (1er mars)", 33, 11, "2027-03-01T00:00:00+00:00", {}),
    ("z5 : avant le début de validité", 40.5, 0.5, "2026-07-31T23:59:59+00:00", {}),
    ("z5 : borne de début incluse", 40.5, 0.5, "2026-08-01T00:00:00+00:00", {}),
    ("z5 : pendant la validité, premier morceau", 40.5, 0.5, "2026-09-01T12:00:00+00:00", {}),
    ("z5 : pendant la validité, second morceau", 45.5, 0.5, "2026-09-01T12:00:00+00:00", {}),
    ("z5 : entre les deux morceaux", 43, 0.5, "2026-09-01T12:00:00+00:00", {}),
    ("z5 : borne de fin incluse", 40.5, 0.5, "2026-12-31T23:59:59+00:00", {}),
    ("z5 : après la fin de validité", 40.5, 0.5, "2027-01-01T00:00:00+00:00", {}),
    (
        "mois évalué en UTC : 31 mai 23h30 à UTC-5 est le 1er juin en UTC (saison d'été active)",
        11, 11, "2026-05-31T23:30:00-05:00", {},
    ),
    (
        "mois évalué en UTC : 30 septembre 20h à UTC-5 est le 1er octobre en UTC (saison d'été terminée)",
        11, 11, "2026-09-30T20:00:00-05:00", {},
    ),
    (
        "mois évalué en UTC : 31 octobre 20h à UTC-5 est le 1er novembre en UTC (saison d'hiver commencée)",
        33, 11, "2026-10-31T20:00:00-05:00", {},
    ),
]


def generer():
    """Jeu de test complet (dict), avec les résultats attendus calculés par la
    détection de référence."""
    cas = []
    for nom, lon, lat, instant, options in CAS:
        attendu = endemies_actives_dans_cache(CACHE_TEST, lon, lat, datetime.fromisoformat(instant))
        cas.append({"nom": nom, "lon": lon, "lat": lat, "instant": instant, "attendu": attendu, **options})
    return {
        "format": VERSION_FORMAT,
        "description": (
            "Jeu de test partagé de la détection locale (Saintex, spec §5). Fichier généré par "
            "`python manage.py generer_vecteurs_detection` : ne pas modifier à la main."
        ),
        "regles": REGLES,
        "cache": CACHE_TEST,
        "cas": cas,
    }


def serialiser(vecteurs):
    return json.dumps(vecteurs, indent=2, ensure_ascii=False) + "\n"


def chemin_fichier():
    return Path(settings.BASE_DIR) / "tests_partages" / "detection_cache.json"
