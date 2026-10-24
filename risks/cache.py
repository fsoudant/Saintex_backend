"""
Cache hors ligne transmis au téléphone (cf. saintex-spec-technique.md §5).

Depuis la révision d'octobre 2026, c'est le téléphone qui détecte l'entrée en
zone à risque et affiche l'alerte : le serveur lui fournit, à chaque contact,
les zones à risque situées dans un rayon autour de sa dernière position, avec
les recommandations associées. Le cache est remplacé intégralement à chaque
contact (jamais cumulé).

Deux fonctions :
- `construire_cache` : génère le cache (côté serveur) ;
- `endemies_actives_dans_cache` : IMPLÉMENTATION DE RÉFÉRENCE de la détection
  que les modules natifs (Swift, Kotlin) doivent reproduire à l'identique —
  test position / période de validité / saison / zone effective, en Python
  pur à partir du cache seul (sans base de données). Elle est vérifiée contre
  la détection PostGIS existante (risks.detection.zones_actives_pour_point) et
  servira à produire un jeu de cas de test partagé.

Format du cache (JSON, un seul niveau d'indirection pour éviter de répéter
les textes et géométries partagés entre endémies) :

    {
      "version": "a1b2c3d4e5f60718",   # empreinte du contenu (hors date)
      "genere_le": "2026-10-24T10:00:00+00:00",
      "rayon_km": 500,
      "conduites": {                    # une entrée par conduite à tenir
        "PAL_T3": {
          "risque": {"code", "libelle_fr", "libelle_en", "couleur"},
          "saison": {"debut": 8, "fin": 11} | null,
          "recommandation_fr": "<p>…</p>",   # HTML assaini (cf. risks.richtext)
          "recommandation_en": "<p>…</p>"
        }
      },
      "geometries": {                   # géométries EFFECTIVES, simplifiées
        "z12": {"type": "MultiPolygon", "coordinates": [...]},   # zone seule
        "e345": {...}                                             # zone moins zone exclue
      },
      "endemies": [
        {"id": 345, "zone_id": 12, "zone_nom": "…", "conduite": "PAL_T3",
         "geometrie": "e345", "valide_du": iso | null, "valide_au": iso | null}
      ]
    }

Choix de conception :
- La géométrie « zone moins zone exclue » est précalculée ici pour que le
  téléphone n'ait qu'UN test point-dans-polygone par endémie, sans gérer
  d'exclusions. Une endémie sans exclusion partage la géométrie de sa zone
  (clé "z<id>") avec les autres endémies de la même zone.
- Les zones à cheval sur l'antiméridien sont stockées découpées en deux
  parties collées à ±180° (cf. risks.geo_utils) : on les transmet TELLES
  QUELLES. Un test planaire sur ces parties fonctionne directement avec une
  longitude comprise dans [-180, 180], sans recomposition.
- Les endémies déjà terminées (date_fin passée) ne sont pas transmises. Les
  endémies futures et la saisonnalité sont transmises et évaluées par le
  téléphone à la date du jour : le cache n'a pas de date de péremption.
- Limite connue : PostGIS (type geography) trace des arêtes géodésiques, le
  téléphone teste en plan sur des coordonnées lon/lat. Pour des polygones à
  précision kilométrique, la différence est négligeable ; elle ne l'est
  plus pour de très longues arêtes (plusieurs centaines de km). À surveiller
  sur les données réelles (cf. test de cohérence PostGIS / cache).
"""

import hashlib
import json
from datetime import datetime

import shapely.geometry
import shapely.wkt
from django.contrib.gis.measure import D
from django.db.models import Q
from django.utils import timezone
from shapely.validation import make_valid

from .models import Endemie
from .richtext import sanitize_html

RAYON_DEFAUT_KM = 500
# ≈ 1 km en degrés (cf. spec §5 : précision cible kilométrique, simplification
# de l'ordre du kilomètre sans perte de sens pour l'utilisateur).
TOLERANCE_SIMPLIFICATION_DEG = 0.01
DECIMALES = 4  # ≈ 11 m : largement sous la tolérance de simplification


def _en_shapely(geos_geom):
    return shapely.wkt.loads(geos_geom.wkt)


def _surfaces(geom):
    """MultiPolygon ne gardant que les surfaces de `geom` (None si vide).
    Une différence ou une réparation de géométrie peut produire des lignes ou
    des points isolés, sans intérêt pour un test d'appartenance."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return shapely.geometry.MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    if geom.geom_type == "GeometryCollection":
        polygones = []
        for partie in geom.geoms:
            if partie.geom_type == "Polygon":
                polygones.append(partie)
            elif partie.geom_type == "MultiPolygon":
                polygones.extend(partie.geoms)
        return shapely.geometry.MultiPolygon(polygones) if polygones else None
    return None


def _geometrie_effective(zone_geom, zone_exclue, tolerance):
    """Géométrie Shapely (MultiPolygon) « zone moins zone exclue », simplifiée,
    ou None si plus rien ne reste."""
    geom = make_valid(_en_shapely(zone_geom))
    if zone_exclue is not None:
        geom = geom.difference(make_valid(_en_shapely(zone_exclue)))
    geom = _surfaces(geom)
    if geom is None:
        return None
    if tolerance:
        geom = _surfaces(geom.simplify(tolerance, preserve_topology=True)) or geom
    return geom


def _arrondir(coordonnees):
    if isinstance(coordonnees[0], (int, float)):
        return [round(c, DECIMALES) for c in coordonnees]
    return [_arrondir(c) for c in coordonnees]


def _en_geojson(geom):
    mapping = shapely.geometry.mapping(geom)
    return {"type": mapping["type"], "coordinates": _arrondir(mapping["coordinates"])}


def _iso(valeur):
    return valeur.isoformat() if valeur else None


def construire_cache(point, rayon_km=RAYON_DEFAUT_KM, moment=None, tolerance=TOLERANCE_SIMPLIFICATION_DEG):
    """Construit le cache pour un téléphone dont la dernière position connue
    est `point` (GEOS Point, srid 4326). Renvoie un dict sérialisable en JSON
    (format décrit dans la docstring du module).

    `tolerance` : simplification en degrés (0 pour la désactiver, utile aux
    tests de cohérence exacts).
    """
    moment = moment or timezone.now()

    endemies = (
        Endemie.objects.filter(zone__geom__dwithin=(point, D(km=rayon_km)))
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=moment))
        .select_related("zone", "conduite_a_tenir", "conduite_a_tenir__risque")
        .order_by("pk")
    )

    conduites = {}
    geometries = {}
    entrees = []

    for endemie in endemies:
        zone = endemie.zone
        conduite = endemie.conduite_a_tenir

        if endemie.zone_exclue is None:
            cle_geometrie = f"z{zone.pk}"
            if cle_geometrie not in geometries:
                geom = _geometrie_effective(zone.geom, None, tolerance)
                if geom is None:
                    continue
                geometries[cle_geometrie] = _en_geojson(geom)
        else:
            cle_geometrie = f"e{endemie.pk}"
            geom = _geometrie_effective(zone.geom, endemie.zone_exclue, tolerance)
            if geom is None:
                # Zone entièrement couverte par son exclusion : rien à signaler.
                continue
            geometries[cle_geometrie] = _en_geojson(geom)

        if conduite.pk not in conduites:
            risque = conduite.risque
            saison = None
            if conduite.saison_mois_debut is not None and conduite.saison_mois_fin is not None:
                saison = {"debut": conduite.saison_mois_debut, "fin": conduite.saison_mois_fin}
            conduites[conduite.pk] = {
                "risque": {
                    "code": risque.code,
                    "libelle_fr": risque.libelle_fr,
                    "libelle_en": risque.libelle_en,
                    "couleur": risque.couleur_legende,
                },
                "saison": saison,
                # Jamais de texte vide transmis : repli sur la description du
                # risque tant que l'équipe médicale n'a pas rédigé la conduite.
                "recommandation_fr": sanitize_html(conduite.recommandation_fr)
                or sanitize_html(risque.nature_du_risque_fr),
                "recommandation_en": sanitize_html(conduite.recommandation_en)
                or sanitize_html(risque.nature_du_risque_en),
            }

        entrees.append({
            "id": endemie.pk,
            "zone_id": zone.pk,
            "zone_nom": zone.nom,
            "conduite": conduite.pk,
            "geometrie": cle_geometrie,
            "valide_du": _iso(endemie.date_debut),
            "valide_au": _iso(endemie.date_fin),
        })

    contenu = {
        "rayon_km": rayon_km,
        "conduites": conduites,
        "geometries": geometries,
        "endemies": entrees,
    }
    version = hashlib.sha256(
        json.dumps(contenu, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]

    return {"version": version, "genere_le": moment.isoformat(), **contenu}


def _en_saison(saison, moment):
    """Même règle que ConduiteATenir.is_in_season (mois seulement, périodes
    à cheval sur le nouvel an comprises)."""
    if saison is None:
        return True
    mois, debut, fin = moment.month, saison["debut"], saison["fin"]
    if debut <= fin:
        return debut <= mois <= fin
    return mois >= debut or mois <= fin


def endemies_actives_dans_cache(cache, lon, lat, moment=None):
    """Implémentation de référence de la détection locale : identifiants des
    endémies du `cache` actives à (`lon`, `lat`) au `moment` donné (défaut :
    maintenant). Les bornes de validité et le bord des polygones sont inclus,
    comme dans la détection PostGIS (`covers`, `date_debut <= moment <=
    date_fin`).
    """
    moment = moment or timezone.now()
    point = shapely.geometry.Point(lon, lat)
    geometries = {}
    actives = []

    for entree in cache["endemies"]:
        if entree["valide_du"] and moment < datetime.fromisoformat(entree["valide_du"]):
            continue
        if entree["valide_au"] and moment > datetime.fromisoformat(entree["valide_au"]):
            continue
        if not _en_saison(cache["conduites"][entree["conduite"]]["saison"], moment):
            continue
        cle = entree["geometrie"]
        if cle not in geometries:
            geometries[cle] = shapely.geometry.shape(cache["geometries"][cle])
        if geometries[cle].covers(point):
            actives.append(entree["id"])
    return actives
