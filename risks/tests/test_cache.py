"""Tests du cache hors ligne (risks.cache) — cf. saintex-spec-technique.md §5.

Le test central est la COHÉRENCE entre la détection PostGIS existante
(risks.detection.zones_actives_pour_point, historiquement utilisée côté
serveur) et la détection de référence rejouée à partir du seul cache
(endemies_actives_dans_cache), que les modules natifs devront reproduire.
"""

import datetime

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import TestCase

from risks.cache import construire_cache, endemies_actives_dans_cache
from risks.detection import zones_actives_pour_point
from risks.models import ConduiteATenir, Endemie, Risque, Zone

UTC = datetime.timezone.utc


def rect(lon_min, lat_min, lon_max, lat_max):
    return Polygon((
        (lon_min, lat_min), (lon_max, lat_min), (lon_max, lat_max),
        (lon_min, lat_max), (lon_min, lat_min),
    ))


def multi(*polygones):
    return MultiPolygon(*polygones)


def moment(annee, mois, jour):
    return datetime.datetime(annee, mois, jour, 12, 0, tzinfo=UTC)


class _Fixtures:
    def _risque(self, code="PAL", couleur="rgb(255,0,0)"):
        return Risque.objects.create(
            code=code, libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="Transmission par moustique.", nature_du_risque_en="Mosquito-borne.",
            couleur_legende=couleur,
        )

    def _conduite(self, risque, code="PAL_T1", **kwargs):
        defaults = dict(nature_du_risque_fr="...", nature_du_risque_en="...",
                        recommandation_fr="<p>Protégez-vous.</p>")
        defaults.update(kwargs)
        return ConduiteATenir.objects.create(code=code, risque=risque, **defaults)

    def _zone(self, source_id, nom, geom):
        return Zone.objects.create(source_id=source_id, nom=nom, geom=geom)


class ConstruireCacheTests(_Fixtures, TestCase):
    def setUp(self):
        self.risque = self._risque()
        self.conduite = self._conduite(self.risque)
        self.zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        self.endemie = Endemie.objects.create(zone=self.zone, conduite_a_tenir=self.conduite)
        self.point = Point(10.5, 10.5, srid=4326)

    def test_inclut_la_zone_proche_et_exclut_la_zone_lointaine(self):
        loin = self._zone(2, "Zone lointaine", multi(rect(100, 10, 102, 12)))
        Endemie.objects.create(zone=loin, conduite_a_tenir=self.conduite)

        cache = construire_cache(self.point, rayon_km=500)

        self.assertEqual([e["id"] for e in cache["endemies"]], [self.endemie.pk])

    def test_le_rayon_est_pris_en_compte(self):
        # Zone à ~390 km au nord-est du point.
        loin = self._zone(2, "Zone à 390 km", multi(rect(13, 13, 14, 14)))
        e_loin = Endemie.objects.create(zone=loin, conduite_a_tenir=self.conduite)

        ids_500 = [e["id"] for e in construire_cache(self.point, rayon_km=500)["endemies"]]
        ids_100 = [e["id"] for e in construire_cache(self.point, rayon_km=100)["endemies"]]

        self.assertIn(e_loin.pk, ids_500)
        self.assertNotIn(e_loin.pk, ids_100)

    def test_cache_mondial_par_defaut(self):
        # Sans position ni rayon : toutes les zones, y compris aux antipodes.
        loin = self._zone(2, "Zone aux antipodes", multi(rect(-170, -40, -168, -38)))
        e_loin = Endemie.objects.create(zone=loin, conduite_a_tenir=self.conduite)

        cache = construire_cache()

        self.assertEqual(sorted(e["id"] for e in cache["endemies"]), sorted([self.endemie.pk, e_loin.pk]))
        self.assertIsNone(cache["rayon_km"])

    def test_conduite_et_geometrie_partagees_entre_endemies(self):
        autre = Endemie.objects.create(zone=self.zone, conduite_a_tenir=self.conduite)

        cache = construire_cache(self.point)

        self.assertEqual(len(cache["endemies"]), 2)
        self.assertEqual(list(cache["conduites"]), ["PAL_T1"])
        self.assertEqual(list(cache["geometries"]), [f"z{self.zone.pk}"])
        self.assertEqual({e["geometrie"] for e in cache["endemies"]}, {f"z{self.zone.pk}"})
        self.assertIn(autre.pk, [e["id"] for e in cache["endemies"]])

    def test_zone_exclue_retiree_de_la_geometrie_effective(self):
        self.endemie.zone_exclue = multi(rect(9.5, 9.5, 10.5, 10.5))
        self.endemie.save()

        cache = construire_cache(self.point, tolerance=0)

        self.assertEqual(cache["endemies"][0]["geometrie"], f"e{self.endemie.pk}")
        self.assertEqual(endemies_actives_dans_cache(cache, 10.0, 10.0, moment(2026, 7, 1)), [])
        self.assertEqual(endemies_actives_dans_cache(cache, 9.2, 9.2, moment(2026, 7, 1)), [self.endemie.pk])

    def test_zone_entierement_exclue_non_transmise(self):
        self.endemie.zone_exclue = multi(rect(8, 8, 12, 12))
        self.endemie.save()

        cache = construire_cache(self.point)

        self.assertEqual(cache["endemies"], [])

    def test_endemie_terminee_non_transmise(self):
        passee = Endemie.objects.create(
            zone=self.zone, conduite_a_tenir=self.conduite, date_fin=moment(2025, 1, 1)
        )

        ids = [e["id"] for e in construire_cache(self.point, moment=moment(2026, 7, 1))["endemies"]]

        self.assertNotIn(passee.pk, ids)
        self.assertIn(self.endemie.pk, ids)

    def test_recommandation_en_html_assaini(self):
        self.conduite.recommandation_fr = '<p>Ok</p><script>alert(1)</script>'
        self.conduite.save()

        cache = construire_cache(self.point)

        self.assertEqual(cache["conduites"]["PAL_T1"]["recommandation_fr"], "<p>Ok</p>")

    def test_repli_sur_la_description_du_risque_si_recommandation_vide(self):
        self.conduite.recommandation_fr = ""
        self.conduite.recommandation_en = ""
        self.conduite.save()

        conduite = construire_cache(self.point)["conduites"]["PAL_T1"]

        self.assertEqual(conduite["recommandation_fr"], "<p>Transmission par moustique.</p>")
        self.assertEqual(conduite["recommandation_en"], "<p>Mosquito-borne.</p>")

    def test_expose_risque_et_saison(self):
        self.conduite.saison_mois_debut = 10
        self.conduite.saison_mois_fin = 2
        self.conduite.save()

        conduite = construire_cache(self.point)["conduites"]["PAL_T1"]

        self.assertEqual(conduite["saison"], {"debut": 10, "fin": 2})
        self.assertEqual(conduite["risque"]["code"], "PAL")
        self.assertEqual(conduite["risque"]["couleur"], "rgb(255,0,0)")

    def test_version_stable_puis_modifiee_avec_le_contenu(self):
        v1 = construire_cache(self.point, moment=moment(2026, 7, 1))["version"]
        v2 = construire_cache(self.point, moment=moment(2026, 7, 2))["version"]
        self.assertEqual(v1, v2)  # la date de génération n'entre pas dans la version

        self.conduite.recommandation_fr = "<p>Nouvelle recommandation.</p>"
        self.conduite.save()

        self.assertNotEqual(construire_cache(self.point)["version"], v1)

    def test_cache_serialisable_en_json(self):
        import json

        json.dumps(construire_cache(self.point))


class DetectionDansLeCacheTests(_Fixtures, TestCase):
    def setUp(self):
        self.risque = self._risque()
        self.point = Point(10.5, 10.5, srid=4326)

    def test_saison_a_cheval_sur_le_nouvel_an(self):
        conduite = self._conduite(self.risque, saison_mois_debut=10, saison_mois_fin=2)
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        endemie = Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)
        cache = construire_cache(self.point, tolerance=0)

        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, 12, 1)), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2027, 1, 15)), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, 6, 1)), [])

    def test_periode_de_validite(self):
        conduite = self._conduite(self.risque)
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        endemie = Endemie.objects.create(
            zone=zone, conduite_a_tenir=conduite,
            date_debut=moment(2026, 8, 1), date_fin=moment(2026, 12, 31),
        )
        cache = construire_cache(self.point, moment=moment(2026, 1, 1), tolerance=0)

        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, 7, 31)), [])
        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, 9, 1)), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2027, 1, 2)), [])

    def test_zone_a_cheval_sur_l_antimeridien(self):
        # Zone découpée à ±180° comme à l'import (cf. risks.geo_utils) : une
        # partie collée à +180, l'autre à -180. Un test planaire sur chaque
        # partie, avec une longitude dans [-180, 180], doit suffire.
        conduite = self._conduite(self.risque)
        zone = self._zone(
            1, "Fidji-like",
            multi(rect(179, -19, 180, -17), rect(-180, -19, -179, -17)),
        )
        endemie = Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)
        cache = construire_cache(Point(179.5, -18, srid=4326), tolerance=0)

        self.assertEqual(len(cache["endemies"]), 1)
        self.assertEqual(endemies_actives_dans_cache(cache, 179.5, -18, moment(2026, 7, 1)), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, -179.5, -18, moment(2026, 7, 1)), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, 170, -18, moment(2026, 7, 1)), [])


class CoherenceAvecLaDetectionPostGISTests(_Fixtures, TestCase):
    """La détection rejouée sur le cache doit donner le même résultat que la
    détection PostGIS pour les mêmes points et les mêmes dates (hors bords
    exacts, où les arêtes géodésiques de `geography` et planaires du cache
    peuvent différer de quelques centaines de mètres)."""

    def setUp(self):
        risque = self._risque()
        conduite_toute_annee = self._conduite(risque, code="PAL_T1")
        conduite_saisonniere = self._conduite(
            risque, code="PAL_T2", saison_mois_debut=6, saison_mois_fin=9
        )
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        zone_b = self._zone(2, "Zone B", multi(rect(11.5, 9, 13, 11)))

        Endemie.objects.create(zone=zone, conduite_a_tenir=conduite_toute_annee)
        Endemie.objects.create(
            zone=zone, conduite_a_tenir=conduite_saisonniere,
            zone_exclue=multi(rect(9.5, 9.5, 10.5, 10.5)),
        )
        Endemie.objects.create(
            zone=zone_b, conduite_a_tenir=conduite_toute_annee,
            date_debut=moment(2026, 8, 1), date_fin=moment(2026, 12, 31),
        )
        self.centre = Point(10.5, 10.5, srid=4326)

    def test_memes_endemies_actives(self):
        points = [
            (10.0, 10.0),    # dans l'exclusion de la zone A
            (9.2, 9.2),      # zone A hors exclusion
            (10.8, 10.8),    # zone A hors exclusion
            (9.7, 10.3),     # dans l'exclusion
            (10.0, 9.1),     # zone A hors exclusion
            (9.05, 10.0),    # près du bord de la zone A, à l'intérieur
            (12.0, 10.0),    # zone B
            (11.25, 10.0),   # entre les zones A et B : aucune
            (8.5, 10.0),     # hors de toute zone
            (12.0, 12.0),    # hors de toute zone
        ]
        dates = [moment(2026, 2, 1), moment(2026, 7, 15), moment(2026, 8, 15), moment(2027, 1, 15)]
        cache = construire_cache(self.centre, moment=moment(2026, 1, 1), tolerance=0)

        for lon, lat in points:
            for date in dates:
                attendu = sorted(
                    e.pk for e in zones_actives_pour_point(Point(lon, lat, srid=4326), date)
                )
                obtenu = sorted(endemies_actives_dans_cache(cache, lon, lat, date))
                self.assertEqual(obtenu, attendu, f"écart en ({lon}, {lat}) au {date.date()}")
