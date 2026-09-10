"""Helpers géométriques partagés pour la gestion de l'antiméridien.

Le découpage effectué à l'import (`migrate_legacy_data.build_zone_geom`, via
la lib `antimeridian`) produit un `MultiPolygon` géométriquement correct pour
les zones à cheval sur ±180° (Tuvalu, Kiribati, Fidji,
Afrique_Asie_centrale) : une partie collée à -180°, l'autre à +180°.

Mais affichée telle quelle sur une carte plate classique (Leaflet, widget
carte de l'admin GeoDjango...), cette géométrie apparaît comme deux
esquilles déconnectées aux deux bords opposés de l'écran — -180° et +180°
sont la même ligne sur le globe mais aux deux extrémités d'une carte plate.

Ce module recompose virtuellement ces deux morceaux en décalant de +360°
la partie côté -180°, pour obtenir un bloc continu autour de 180°/-180°
(par ex. 179°→181° au lieu de 179°→180° et -180°→-179° séparément). Purement
visuel : la géométrie stockée en base n'est jamais modifiée par ces helpers.
"""

import shapely.affinity
import shapely.geometry
import shapely.wkt

# Tolérance sous les ±180° exacts pour repérer une partie "collée" au bord
# (les coordonnées sources ne tombent pas toujours pile sur 180.0).
_EDGE_TOLERANCE = 0.1


def _shift_west_parts(shapely_geom):
    """Renvoie la liste des polygones d'une géométrie Shapely, en décalant de
    +360 tout polygone dont le bord gauche touche -180 (partie "ouest" issue
    d'un découpage à l'antiméridien). Utilisé pour recomposer une géométrie
    à cheval sur l'antiméridien en un seul bloc continu, que ce soit pour un
    aperçu visuel ou pour calculer un centre correct.
    """
    parts = [shapely_geom] if shapely_geom.geom_type == "Polygon" else list(shapely_geom.geoms)
    return [
        shapely.affinity.translate(p, xoff=360) if p.bounds[0] <= -180 + _EDGE_TOLERANCE else p
        for p in parts
    ]


def touches_antimeridian(shapely_geom):
    """True si la géométrie a des parties collées aux deux bords -180 et
    +180 (signe d'un découpage à l'antiméridien, plutôt qu'un MultiPolygon
    pour une autre raison, ex. buffer(0) sur auto-intersection)."""
    parts = [shapely_geom] if shapely_geom.geom_type == "Polygon" else list(shapely_geom.geoms)
    if len(parts) < 2:
        return False
    touches_west = any(p.bounds[0] <= -180 + _EDGE_TOLERANCE for p in parts)
    touches_east = any(p.bounds[2] >= 180 - _EDGE_TOLERANCE for p in parts)
    return touches_west and touches_east


def recompose_antimeridian(geos_geom):
    """Géométrie Shapely recomposée (partie ouest décalée de +360) si
    `geos_geom` franchit l'antiméridien, sinon la géométrie Shapely
    équivalente inchangée. Point d'entrée principal du module : prend une
    géométrie GEOS (colonne PostGIS) et rend une géométrie Shapely prête à
    être affichée (aperçu SVG, GeoJSON pour Leaflet, calcul de centre...).
    """
    shapely_geom = shapely.wkt.loads(geos_geom.wkt)
    if not touches_antimeridian(shapely_geom):
        return shapely_geom
    shifted = _shift_west_parts(shapely_geom)
    return shapely.geometry.MultiPolygon(shifted) if len(shifted) > 1 else shifted[0]


def zone_center_lonlat(geom):
    """Centre (lon, lat) d'une géométrie de Zone, correct même à cheval sur
    l'antiméridien.

    Un centroïde GEOS/Shapely classique fait une moyenne pondérée par aire
    des coordonnées *littérales*. Pour une zone découpée en deux parties de
    part et d'autre de ±180° (Tuvalu, Kiribati, Fidji,
    Afrique_Asie_centrale — cf. build_zone_geom), ça place le centre au
    milieu du monde plutôt que dans la zone elle-même (ex. Fidji retombait à
    64°E, dans l'océan Indien, au lieu de ~179°E). On recompose donc la
    géométrie via recompose_antimeridian avant de calculer le centroïde,
    puis on ramène le résultat dans l'intervalle standard [-180, 180].
    """
    combined = recompose_antimeridian(geom)
    centroid = combined.centroid
    lon = centroid.x - 360 if centroid.x > 180 else centroid.x
    return lon, centroid.y
