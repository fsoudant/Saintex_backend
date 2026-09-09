"""Tests des helpers géométriques de risks.admin : recollement à
l'antiméridien, calcul du centre et aperçu SVG.
"""

from django.contrib.gis.geos import GEOSGeometry
from django.test import SimpleTestCase

import shapely.geometry

from risks.admin import _antimeridian_preview_svg, _shift_west_parts, zone_center_lonlat

# MultiPolygone à cheval sur l'antiméridien, deux carrés d'un degré de côté :
# l'un collé à -180°, l'autre à +180° (comme après fix_polygon dans l'import).
_WEST_WKT = "POLYGON ((-180 0, -179 0, -179 1, -180 1, -180 0))"
_EAST_WKT = "POLYGON ((179 1, 180 1, 180 2, 179 2, 179 1))"
_CHEVAL_WKT = (
    "MULTIPOLYGON "
    "(((-180 0, -179 0, -179 1, -180 1, -180 0)), "
    "((179 1, 180 1, 180 2, 179 2, 179 1)))"
)

_SIMPLE_WKT = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"


class ShiftWestPartsTests(SimpleTestCase):
    def test_polygon_simple_non_decale(self):
        geom = shapely.wkt.loads(_SIMPLE_WKT)
        parts = _shift_west_parts(geom)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].bounds, (0.0, 0.0, 10.0, 10.0))

    def test_polygon_colle_a_ouest_decale_de_360(self):
        geom = shapely.wkt.loads(_WEST_WKT)
        parts = _shift_west_parts(geom)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].bounds[0], 180.0)  # -180 -> +180

    def test_multipolygon_cheval_seulement_la_partie_ouest(self):
        geom = shapely.wkt.loads(_CHEVAL_WKT)
        parts = sorted(_shift_west_parts(geom), key=lambda p: p.bounds[0])
        # La partie collée à -180 a été décalée à [180, 181] ; l'autre à [179, 180].
        self.assertEqual(parts[0].bounds[0], 179.0)
        self.assertEqual(parts[1].bounds[0], 180.0)


class ZoneCenterLonLatTests(SimpleTestCase):
    def test_centre_dun_polygon_simple(self):
        geom = GEOSGeometry(_SIMPLE_WKT, srid=4326)
        lon, lat = zone_center_lonlat(geom)
        self.assertAlmostEqual(lon, 5.0)
        self.assertAlmostEqual(lat, 5.0)

    def test_centre_a_cheval_sur_lantimeridien(self):
        # Avant le recollement, le centroïde naïf atterrirait au milieu du
        # monde (près de 0°) au lieu de la zone réelle (près de 180°E).
        geom = GEOSGeometry(_CHEVAL_WKT, srid=4326)
        lon, lat = zone_center_lonlat(geom)
        self.assertAlmostEqual(lon, 180.0)
        self.assertAlmostEqual(lat, 1.0)

    def test_centre_ramene_dans_lintervalle_standard(self):
        # Une zone entièrement à l'est ne doit pas renvoyer > 180.
        wkt = "POLYGON ((179 0, 180 0, 180 1, 179 1, 179 0))"
        geom = GEOSGeometry(wkt, srid=4326)
        lon, lat = zone_center_lonlat(geom)
        self.assertTrue(-180.0 <= lon <= 180.0)
        self.assertAlmostEqual(lon, 179.5)


class AntimeridianPreviewSvgTests(SimpleTestCase):
    def test_aucun_apercu_pour_un_polygon_simple(self):
        geom = GEOSGeometry(_SIMPLE_WKT, srid=4326)
        self.assertIsNone(_antimeridian_preview_svg(geom))

    def test_aucun_apercu_pour_un_multipolygon_non_antimeridien(self):
        wkt = (
            "MULTIPOLYGON (((0 0, 5 0, 5 5, 0 5, 0 0)), "
            "((20 20, 25 20, 25 25, 20 25, 20 20)))"
        )
        geom = GEOSGeometry(wkt, srid=4326)
        self.assertIsNone(_antimeridian_preview_svg(geom))

    def test_aucun_apercu_si_seule_la_partie_ouest_touche(self):
        wkt = (
            "MULTIPOLYGON (((-180 0, -179 0, -179 1, -180 1, -180 0)), "
            "((-180 2, -179 2, -179 3, -180 3, -180 2)))"
        )
        geom = GEOSGeometry(wkt, srid=4326)
        self.assertIsNone(_antimeridian_preview_svg(geom))

    def test_apercu_svg_recollant_les_deux_moities(self):
        geom = GEOSGeometry(_CHEVAL_WKT, srid=4326)
        svg = _antimeridian_preview_svg(geom)
        self.assertIsNotNone(svg)
        self.assertIn("<svg", svg)
        self.assertIn("180°", svg)  # repère visuel de la couture
        # La géométrie source n'est jamais modifiée par l'aperçu.
        self.assertEqual(geom.geom_type, "MultiPolygon")
        self.assertEqual(geom.num_geom, 2)