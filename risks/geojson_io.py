"""Import / export GeoJSON de la géométrie d'une Zone (boutons de la fiche
Zone du back-office, cf. ZoneAdmin).

Pourquoi : la géométrie d'une zone se stocke en EWKT, ce qui est pénible à
produire depuis les outils usuels (geojson.io, geojson-maps...) qui parlent
GeoJSON, avec des coordonnées à 6 décimales (~10 cm) inutiles ici : la
précision cible des zones est de l'ordre du kilomètre (spec §7).

- Export : géométrie stockée → Feature GeoJSON, coordonnées arrondies à
  `DECIMALES` décimales, que l'on peut rouvrir telle quelle dans geojson.io.
- Import : FeatureCollection / Feature / Polygon / MultiPolygon → MultiPolygon
  WGS84 propre : 2D, dans les limites, corrigé si invalide (auto-intersection,
  chevauchement), simplifié si demandé, arrondi à `DECIMALES` décimales.
"""

import json

import shapely
import shapely.geometry
import shapely.wkt
from django.contrib.gis.geos import GEOSGeometry

# 4 décimales ≈ 11 m à l'équateur : très en deçà de la précision kilométrique
# visée, et 30 % de texte en moins par rapport aux 6 décimales usuelles.
DECIMALES = 4
_GRILLE = 10 ** -DECIMALES


class GeoJSONInvalide(ValueError):
    """Contenu GeoJSON inutilisable ; le message est affiché tel quel à
    l'utilisateur du back-office."""


def _polygones(geom):
    """Polygones contenus dans une géométrie Shapely (points et lignes
    ignorés)."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type in ("MultiPolygon", "GeometryCollection"):
        resultat = []
        for partie in geom.geoms:
            resultat.extend(_polygones(partie))
        return resultat
    return []


def _geometries_du_geojson(donnees):
    type_ = donnees.get("type")
    if type_ == "FeatureCollection":
        return [f.get("geometry") for f in donnees.get("features", []) if f.get("geometry")]
    if type_ == "Feature":
        return [donnees["geometry"]] if donnees.get("geometry") else []
    if type_ in ("Polygon", "MultiPolygon", "GeometryCollection"):
        return [donnees]
    raise GeoJSONInvalide(
        f"Type GeoJSON non pris en charge : « {type_} » "
        "(attendu : FeatureCollection, Feature, Polygon ou MultiPolygon)."
    )


def _compter_points(geom):
    return int(shapely.get_num_coordinates(geom))


def geojson_vers_multipolygon(texte, tolerance=0.0):
    """Convertit un texte GeoJSON en `MultiPolygon` GEOS (SRID 4326).

    `tolerance` : simplification en degrés (0 = aucune ; 0,001° ≈ 100 m,
    0,01° ≈ 1 km), appliquée avant l'arrondi, sans changer la topologie.

    Renvoie `(geometrie, resume)` où `resume` décrit le résultat
    (polygones, points, avertissements éventuels) pour le message affiché.
    Lève `GeoJSONInvalide` si rien d'exploitable.
    """
    try:
        donnees = json.loads(texte)
    except ValueError as erreur:
        raise GeoJSONInvalide(f"JSON illisible : {erreur}")
    if not isinstance(donnees, dict):
        raise GeoJSONInvalide("Le JSON doit être un objet GeoJSON (FeatureCollection, Feature...).")

    avertissements = []
    polygones = []
    ignorees = 0
    for geometrie in _geometries_du_geojson(donnees):
        try:
            forme = shapely.geometry.shape(geometrie)
        except Exception as erreur:  # shapely lève des types variés selon le défaut
            raise GeoJSONInvalide(f"Géométrie illisible : {erreur}")
        trouves = _polygones(forme)
        if not trouves:
            ignorees += 1
        polygones.extend(trouves)
    if not polygones:
        raise GeoJSONInvalide(
            "Aucun polygone trouvé : seuls les Polygon et MultiPolygon sont importés "
            "(les points et les lignes sont ignorés)."
        )
    if ignorees:
        avertissements.append(f"{ignorees} élément(s) sans polygone ignoré(s).")

    geom = shapely.force_2d(shapely.geometry.MultiPolygon(polygones))

    min_x, min_y, max_x, max_y = geom.bounds
    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
        raise GeoJSONInvalide(
            "Coordonnées hors limites (longitude ±180, latitude ±90) : longitude et latitude "
            "inversées, ou projection autre que WGS84 ? GeoJSON attend [longitude, latitude]."
        )

    if not geom.is_valid:
        geom = shapely.geometry.MultiPolygon(_polygones(shapely.make_valid(geom)))
        avertissements.append("Géométrie invalide corrigée automatiquement (auto-intersection ou chevauchement).")

    if tolerance and tolerance > 0:
        geom = geom.simplify(tolerance, preserve_topology=True)

    # Arrondi sur une grille : supprime aussi les points devenus identiques.
    geom = shapely.set_precision(geom, _GRILLE)
    polygones_finaux = _polygones(geom)
    if not polygones_finaux:
        raise GeoJSONInvalide("Le résultat est vide après simplification/arrondi : tolérance trop forte ?")
    geom = shapely.geometry.MultiPolygon(polygones_finaux)

    wkt = shapely.to_wkt(geom, rounding_precision=DECIMALES, trim=True)
    resultat = GEOSGeometry(wkt, srid=4326)
    resume = {
        "polygones": len(polygones_finaux),
        "points": _compter_points(geom),
        "avertissements": avertissements,
    }
    return resultat, resume


def _arrondir(coordonnees):
    if isinstance(coordonnees[0], (int, float)):
        return [round(c, DECIMALES) for c in coordonnees[:2]]
    return [_arrondir(c) for c in coordonnees]


def zone_vers_geojson(zone):
    """Feature GeoJSON (dict) d'une Zone portant une géométrie. La géométrie
    est celle stockée, telle quelle (pas de recomposition à l'antiméridien),
    arrondie à `DECIMALES` décimales : réimportable sans perte."""
    forme = shapely.wkt.loads(zone.geom.wkt)
    geometrie = shapely.geometry.mapping(forme)
    return {
        "type": "Feature",
        "properties": {"nom": zone.nom, "source_id": zone.source_id, "id": zone.pk},
        "geometry": {
            "type": geometrie["type"],
            "coordinates": _arrondir(geometrie["coordinates"]),
        },
    }
