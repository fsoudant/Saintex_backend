"""Tests de la construction du GeoJSON de la carte des risques
(risks.views.build_risk_map_geojson).

Zones, endémies et conduites à tenir sont simulées en mémoire : la base de
données est remplacée par un mock (Zone.objects) pour ne tester que la
logique de coloration/moyenne.
"""

from unittest import mock

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import SimpleTestCase

from risks.models import Zone
from risks.views import build_risk_map_geojson


class _FakeQuerySet(list):
    """Liste d'objets simulés qui accepte les appels ORM chaînés."""

    def prefetch_related(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def distinct(self):
        return self


def _geom():
    poly = Polygon(((0, 0), (10, 0), (10, 10), (0, 10), (0, 0)))
    return MultiPolygon(poly, srid=4326)


def _risque(couleur, libelle):
    r = mock.MagicMock()
    r.couleur_legende = couleur
    r.libelle_fr = libelle
    return r


def _conduite(pk, code, risque):
    c = mock.MagicMock()
    c.pk = pk
    c.code = code
    c.risque = risque
    return c


def _endemie(eid, conduite, exclue=None):
    e = mock.MagicMock()
    e.id = eid
    e.conduite_a_tenir = conduite
    e.conduite_a_tenir_id = conduite.pk
    e.zone_exclue = exclue
    return e


def _zone(nom, geom, endemies):
    z = mock.MagicMock()
    z.nom = nom
    z.geom = geom
    z.endemies.all.return_value = endemies
    return z


class BuildRiskMapGeoJsonTests(SimpleTestCase):
    def _patch_zones(self, zones):
        patcher = mock.patch.object(Zone, "objects")
        objects = patcher.start()
        self.addCleanup(patcher.stop)
        objects.filter.return_value = _FakeQuerySet(zones)
        return objects

    def test_aucune_zone(self):
        self._patch_zones([])
        data = build_risk_map_geojson()
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(data["features"], [])

    def test_filtre_les_zones_sans_geometrie(self):
        objects = self._patch_zones([])
        build_risk_map_geojson()
        objects.filter.assert_called_once_with(geom__isnull=False)

    def test_zone_avec_deux_risques_couleur_moyenne(self):
        paludisme = _risque("rgb(255,0,0)", "Paludisme")
        dengue = _risque("rgb(0,0,255)", "Dengue")
        c_pal = _conduite(1, "P_T3_A", paludisme)
        c_deng = _conduite(2, "D_T3_A", dengue)
        zon = _zone("Kuntaur", _geom(), [
            _endemie(10, c_pal),
            _endemie(11, c_deng),
        ])
        self._patch_zones([zon])

        data = build_risk_map_geojson()

        self.assertEqual(len(data["features"]), 1)
        props = data["features"][0]["properties"]
        self.assertEqual(props["layer"], "zone")
        self.assertEqual(props["nom"], "Kuntaur")
        # Moyenne (255,0,0) et (0,0,255) -> (127,0,127).
        self.assertEqual(props["fill"], "rgb(127,0,127)")
        self.assertEqual(props["risques"], ["Dengue", "Paludisme"])
        # La géométrie source est bien sérialisée en GeoJSON.
        self.assertEqual(data["features"][0]["geometry"]["type"], "MultiPolygon")

    def test_exclusion_sans_autre_risque_transparente(self):
        paludisme = _risque("rgb(255,0,0)", "Paludisme")
        c_pal = _conduite(1, "P_T3_A", paludisme)
        zon = _zone("Kuntaur", _geom(), [
            _endemie(10, c_pal, exclue=_geom()),
        ])
        self._patch_zones([zon])

        data = build_risk_map_geojson()

        # 1 feature zone + 1 feature exclusion.
        self.assertEqual(len(data["features"]), 2)
        exclusions = [f for f in data["features"] if f["properties"]["layer"] == "exclusion"]
        self.assertEqual(len(exclusions), 1)
        props = exclusions[0]["properties"]
        self.assertIsNone(props["fill"])  # transparente : vraie zone saine
        self.assertEqual(props["risque_exclu"], "Paludisme")
        self.assertEqual(exclusions[0]["geometry"]["type"], "MultiPolygon")

    def test_exclusion_coloree_avec_les_autres_risques_de_la_zone(self):
        paludisme = _risque("rgb(255,0,0)", "Paludisme")
        dengue = _risque("rgb(0,0,255)", "Dengue")
        c_pal = _conduite(1, "P_T3_A", paludisme)
        c_deng = _conduite(2, "D_T3_A", dengue)
        # Palu porte l'exclusion ; la dengue reste active partout.
        zon = _zone("Kuntaur", _geom(), [
            _endemie(10, c_pal, exclue=_geom()),
            _endemie(11, c_deng),
        ])
        self._patch_zones([zon])

        data = build_risk_map_geojson()

        exclusions = [f for f in data["features"] if f["properties"]["layer"] == "exclusion"]
        self.assertEqual(len(exclusions), 1)
        # La patch est coloriée de la dengue (seul autre risque de la zone).
        self.assertEqual(exclusions[0]["properties"]["fill"], "rgb(0,0,255)")

    def test_vue_filtree_par_conduite(self):
        paludisme = _risque("rgb(255,0,0)", "Paludisme")
        dengue = _risque("rgb(0,0,255)", "Dengue")
        c_pal = _conduite(1, "P_T3_A", paludisme)
        c_deng = _conduite(2, "D_T3_A", dengue)
        # La zone porte les deux risques ; on affiche "à travers" c_pal.
        zon = _zone("Kuntaur", _geom(), [
            _endemie(10, c_pal, exclue=_geom()),
            _endemie(11, c_deng),
        ])
        self._patch_zones([zon])

        data = build_risk_map_geojson(conduite_a_tenir=c_pal)

        # Une seule feature zone + l'exclusion (transparente, plus de mélange
        # avec les risques hors périmètre).
        self.assertEqual(len(data["features"]), 2)
        zone_feature = next(f for f in data["features"] if f["properties"]["layer"] == "zone")
        self.assertEqual(zone_feature["properties"]["fill"], "rgb(255,0,0)")
        self.assertEqual(zone_feature["properties"]["risques"], ["Paludisme"])
        exclusion = next(f for f in data["features"] if f["properties"]["layer"] == "exclusion")
        self.assertIsNone(exclusion["properties"]["fill"])