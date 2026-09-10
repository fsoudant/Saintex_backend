"""Tests de risks.geo_utils : recomposition des géométries à cheval sur
l'antiméridien, partagée entre l'aperçu admin et la carte des risques
publique (risks.views).
"""

from django.contrib.gis.geos import GEOSGeometry
from django.test import SimpleTestCase

from risks.geo_utils import recompose_antimeridian, touches_antimeridian

# Mêmes fixtures que test_geom_helpers.py : deux carrés d'un degré de côté,
# l'un collé à -180°, l'autre à +180° (comme après fix_polygon dans l'import).
_CHEVAL_WKT = (
    "MULTIPOLYGON "
    "(((-180 0, -179 0, -179 1, -180 1, -180 0)), "
    "((179 1, 180 1, 180 2, 179 2, 179 1)))"
)
_SIMPLE_WKT = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"


class TouchesAntimeridianTests(SimpleTestCase):
    def test_zone_simple_ne_touche_pas(self):
        import shapely.wkt
        geom = shapely.wkt.loads(_SIMPLE_WKT)
        self.assertFalse(touches_antimeridian(geom))

    def test_zone_a_cheval_touche(self):
        import shapely.wkt
        geom = shapely.wkt.loads(_CHEVAL_WKT)
        self.assertTrue(touches_antimeridian(geom))


class RecomposeAntimeridianTests(SimpleTestCase):
    def test_geometrie_simple_inchangee(self):
        geom = GEOSGeometry(_SIMPLE_WKT, srid=4326)
        recomposed = recompose_antimeridian(geom)
        self.assertEqual(recomposed.bounds, (0.0, 0.0, 10.0, 10.0))

    def test_geometrie_a_cheval_devient_un_seul_bloc_continu(self):
        geom = GEOSGeometry(_CHEVAL_WKT, srid=4326)
        recomposed = recompose_antimeridian(geom)
        # Avant recomposition : deux carrés disjoints, aux bords opposés
        # (-180→-179 et 179→180). Après : un seul bloc continu 179→181.
        self.assertEqual(recomposed.geom_type, "MultiPolygon")
        minx, miny, maxx, maxy = recomposed.bounds
        self.assertAlmostEqual(minx, 179.0)
        self.assertAlmostEqual(maxx, 181.0)
        # Les deux parties se touchent maintenant à x=180 (plus de trou).
        xs = sorted({round(x, 1) for poly in recomposed.geoms for x in poly.exterior.coords.xy[0]})
        self.assertIn(180.0, xs)

    def test_geometrie_source_non_modifiee(self):
        geom = GEOSGeometry(_CHEVAL_WKT, srid=4326)
        recompose_antimeridian(geom)
        # L'appel ne doit jamais toucher à la géométrie GEOS passée en entrée.
        self.assertEqual(geom.wkt, GEOSGeometry(_CHEVAL_WKT, srid=4326).wkt)
