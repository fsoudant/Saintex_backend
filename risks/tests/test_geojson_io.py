"""Tests de l'import / export GeoJSON des zones (risks.geojson_io)."""

import json
from types import SimpleNamespace

from django.test import SimpleTestCase

from risks.geojson_io import DECIMALES, GeoJSONInvalide, geojson_vers_multipolygon, zone_vers_geojson


def _carre(x, y, cote=1.0):
    return [[x, y], [x + cote, y], [x + cote, y + cote], [x, y + cote], [x, y]]


def _feature(coordonnees, type_="Polygon", **proprietes):
    return {"type": "Feature", "properties": proprietes, "geometry": {"type": type_, "coordinates": coordonnees}}


def _importer(donnees, **kwargs):
    return geojson_vers_multipolygon(json.dumps(donnees), **kwargs)


def _toutes_les_coordonnees(multipolygon):
    for polygone in multipolygon.coords:
        for anneau in polygone:
            for point in anneau:
                yield from point


class ImportGeoJSONTests(SimpleTestCase):
    def test_feature_collection_de_deux_polygones_devient_un_multipolygon(self):
        donnees = {
            "type": "FeatureCollection",
            "features": [_feature([_carre(0, 0)]), _feature([_carre(10, 10)])],
        }
        geometrie, resume = _importer(donnees)
        self.assertEqual(geometrie.geom_type, "MultiPolygon")
        self.assertEqual(geometrie.srid, 4326)
        self.assertEqual(resume["polygones"], 2)
        self.assertEqual(resume["avertissements"], [])

    def test_polygon_nu_et_multipolygon_acceptes(self):
        polygone = {"type": "Polygon", "coordinates": [_carre(0, 0)]}
        multi = {"type": "MultiPolygon", "coordinates": [[_carre(0, 0)], [_carre(5, 5)]]}
        self.assertEqual(_importer(polygone)[1]["polygones"], 1)
        self.assertEqual(_importer(multi)[1]["polygones"], 2)

    def test_coordonnees_arrondies_a_la_precision_choisie(self):
        carre = [[round(c + 0.123456, 6) for c in point] for point in _carre(10, 20)]
        geometrie, _ = _importer(_feature([carre]))
        for valeur in _toutes_les_coordonnees(geometrie):
            echelle = valeur * 10**DECIMALES
            self.assertAlmostEqual(echelle, round(echelle), places=6)

    def test_troisieme_dimension_supprimee(self):
        carre_3d = [[x, y, 100] for x, y in _carre(0, 0)]
        geometrie, _ = _importer(_feature([carre_3d]))
        self.assertFalse(geometrie.hasz)

    def test_geometrie_invalide_corrigee_avec_avertissement(self):
        noeud_papillon = [[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]
        geometrie, resume = _importer(_feature([noeud_papillon]))
        self.assertTrue(geometrie.valid)
        self.assertTrue(resume["avertissements"])

    def test_simplification_reduit_le_nombre_de_points(self):
        # Un côté « bruité » : des points presque alignés, à 0,0005° de la droite.
        cote_bruite = [[x / 10, 0.0005 * (x % 2)] for x in range(0, 101)]
        contour = cote_bruite + [[10, 10], [0, 10], [0, 0]]
        _, sans = _importer(_feature([contour]))
        _, avec = _importer(_feature([contour]), tolerance=0.01)
        self.assertLess(avec["points"], sans["points"])

    def test_coordonnees_hors_limites_refusees(self):
        with self.assertRaisesMessage(GeoJSONInvalide, "hors limites"):
            _importer(_feature([_carre(10, 120)]))

    def test_sans_polygone_refuse(self):
        point = {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [1, 2]}}
        with self.assertRaisesMessage(GeoJSONInvalide, "Aucun polygone"):
            _importer(point)

    def test_json_illisible_refuse(self):
        with self.assertRaisesMessage(GeoJSONInvalide, "JSON illisible"):
            geojson_vers_multipolygon("{pas du json")

    def test_type_non_pris_en_charge_refuse(self):
        with self.assertRaisesMessage(GeoJSONInvalide, "non pris en charge"):
            _importer({"type": "Topology"})


class ExportGeoJSONTests(SimpleTestCase):
    def test_aller_retour_sans_perte(self):
        original, _ = _importer({
            "type": "FeatureCollection",
            "features": [_feature([_carre(88.7512, 26.7034)]), _feature([_carre(90.1, 27.2)])],
        })
        zone = SimpleNamespace(geom=original, nom="Bhoutan — test", source_id=999, pk=1)
        feature = zone_vers_geojson(zone)
        self.assertEqual(feature["type"], "Feature")
        self.assertEqual(feature["geometry"]["type"], "MultiPolygon")
        self.assertEqual(feature["properties"]["nom"], "Bhoutan — test")

        reimporte, _ = _importer(feature)
        self.assertTrue(reimporte.equals(original))

    def test_export_arrondi(self):
        brut = _importer(_feature([_carre(10.1235, 20.1235)]))[0]
        zone = SimpleNamespace(geom=brut, nom="Z", source_id=1, pk=1)
        coordonnees = zone_vers_geojson(zone)["geometry"]["coordinates"]
        premier_point = coordonnees[0][0][0]
        self.assertEqual(premier_point, [round(c, DECIMALES) for c in premier_point])
