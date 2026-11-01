"""Tests du cache hors ligne (risks.cache) — cf. saintex-spec-technique.md §5.

Le test central est la COHÉRENCE entre la détection PostGIS existante
(risks.detection.zones_actives_pour_point, historiquement utilisée côté
serveur) et la détection de référence rejouée à partir du seul cache
(endemies_actives_dans_cache), que les modules natifs devront reproduire.

Depuis l'évolution « Modulation » d'octobre 2026, le cache contient les
risques (description + recommandation unique) et les modulations (phrase +
période) séparément ; les endémies y renvoient par leur code.
"""

import datetime
import json

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import SimpleTestCase, TestCase

from risks.cache import construire_cache, endemies_actives_dans_cache, message_detail_html
from risks.detection import zones_actives_pour_point
from risks.models import Endemie, Modulation, Risque, Zone

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
    def _risque(self, code="PAL", couleur="rgb(255,0,0)", **kwargs):
        defaults = dict(
            libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="Transmission par moustique.", nature_du_risque_en="Mosquito-borne.",
            recommandation_fr="<p>Protégez-vous.</p>", recommandation_en="<p>Protect yourself.</p>",
            couleur_legende=couleur,
        )
        defaults.update(kwargs)
        return Risque.objects.create(code=code, **defaults)

    def _modulation(self, code="PAL_T1", **kwargs):
        return Modulation.objects.create(code=code, **kwargs)

    def _zone(self, source_id, nom, geom):
        return Zone.objects.create(source_id=source_id, nom=nom, geom=geom)


class ConstruireCacheTests(_Fixtures, TestCase):
    def setUp(self):
        self.risque = self._risque()
        self.zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        self.endemie = Endemie.objects.create(zone=self.zone, risque=self.risque)
        self.point = Point(10.5, 10.5, srid=4326)

    def test_inclut_la_zone_proche_et_exclut_la_zone_lointaine(self):
        loin = self._zone(2, "Zone lointaine", multi(rect(100, 10, 102, 12)))
        Endemie.objects.create(zone=loin, risque=self.risque)

        cache = construire_cache(self.point, rayon_km=500)

        self.assertEqual([e["id"] for e in cache["endemies"]], [self.endemie.pk])

    def test_le_rayon_est_pris_en_compte(self):
        # Zone à ~390 km au nord-est du point.
        loin = self._zone(2, "Zone à 390 km", multi(rect(13, 13, 14, 14)))
        e_loin = Endemie.objects.create(zone=loin, risque=self.risque)

        ids_500 = [e["id"] for e in construire_cache(self.point, rayon_km=500)["endemies"]]
        ids_100 = [e["id"] for e in construire_cache(self.point, rayon_km=100)["endemies"]]

        self.assertIn(e_loin.pk, ids_500)
        self.assertNotIn(e_loin.pk, ids_100)

    def test_cache_mondial_par_defaut(self):
        # Sans position ni rayon : toutes les zones, y compris aux antipodes.
        loin = self._zone(2, "Zone aux antipodes", multi(rect(-170, -40, -168, -38)))
        e_loin = Endemie.objects.create(zone=loin, risque=self.risque)

        cache = construire_cache()

        self.assertEqual(sorted(e["id"] for e in cache["endemies"]), sorted([self.endemie.pk, e_loin.pk]))
        self.assertIsNone(cache["rayon_km"])

    def test_format_du_cache(self):
        self.assertEqual(construire_cache(self.point)["format"], 2)

    def test_risque_et_geometrie_partages_entre_endemies(self):
        autre = Endemie.objects.create(zone=self.zone, risque=self.risque)

        cache = construire_cache(self.point)

        self.assertEqual(len(cache["endemies"]), 2)
        self.assertEqual(list(cache["risques"]), ["PAL"])
        self.assertEqual(cache["modulations"], {})
        self.assertEqual(list(cache["geometries"]), [f"z{self.zone.pk}"])
        self.assertEqual({e["geometrie"] for e in cache["endemies"]}, {f"z{self.zone.pk}"})
        self.assertIn(autre.pk, [e["id"] for e in cache["endemies"]])

    def test_modulation_partagee_entre_endemies_de_risques_differents(self):
        # Le catalogue de modulations est indépendant du risque.
        rural = self._modulation(
            "RURAL", modulation_fr="Le risque est majoré si vous séjournez en milieu rural.",
        )
        autre_risque = self._risque("DEN", libelle_fr="Dengue", libelle_en="Dengue")
        Endemie.objects.filter(pk=self.endemie.pk).update(modulation=rural)
        Endemie.objects.create(zone=self.zone, risque=autre_risque, modulation=rural)

        cache = construire_cache(self.point)

        self.assertEqual(sorted(cache["risques"]), ["DEN", "PAL"])
        self.assertEqual(list(cache["modulations"]), ["RURAL"])

    def test_endemie_sans_modulation(self):
        entree = construire_cache(self.point)["endemies"][0]

        self.assertEqual(entree["risque"], "PAL")
        self.assertIsNone(entree["modulation"])

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
            zone=self.zone, risque=self.risque, date_fin=moment(2025, 1, 1)
        )

        ids = [e["id"] for e in construire_cache(self.point, moment=moment(2026, 7, 1))["endemies"]]

        self.assertNotIn(passee.pk, ids)
        self.assertIn(self.endemie.pk, ids)

    def test_recommandation_en_html_assaini(self):
        self.risque.recommandation_fr = '<p>Ok</p><script>alert(1)</script>'
        self.risque.save()

        cache = construire_cache(self.point)

        self.assertEqual(cache["risques"]["PAL"]["recommandation_fr"], "<p>Ok</p>")

    def test_recommandation_vide_transmise_vide_avec_la_description(self):
        # Plus de repli de la recommandation sur la description : celle-ci est
        # un champ à part, toujours transmis (cf. spec §8, composition du message).
        self.risque.recommandation_fr = ""
        self.risque.recommandation_en = ""
        self.risque.save()

        risque = construire_cache(self.point)["risques"]["PAL"]

        self.assertEqual(risque["recommandation_fr"], "")
        self.assertEqual(risque["recommandation_en"], "")
        self.assertEqual(risque["description_fr"], "<p>Transmission par moustique.</p>")
        self.assertEqual(risque["description_en"], "<p>Mosquito-borne.</p>")

    def test_expose_risque_modulation_et_saison(self):
        modulation = self._modulation(
            "PAL_T1", modulation_fr="Phrase fr", modulation_en="Phrase en",
            saison_mois_debut=10, saison_mois_fin=2,
        )
        Endemie.objects.filter(pk=self.endemie.pk).update(modulation=modulation)

        cache = construire_cache(self.point)

        self.assertEqual(
            cache["modulations"]["PAL_T1"],
            {"fr": "Phrase fr", "en": "Phrase en", "saison": {"debut": 10, "fin": 2}},
        )
        self.assertEqual(cache["endemies"][0]["modulation"], "PAL_T1")
        risque = cache["risques"]["PAL"]
        self.assertEqual(risque["libelle_fr"], "Paludisme")
        self.assertEqual(risque["couleur"], "rgb(255,0,0)")

    def test_modulation_sans_periode_a_une_saison_nulle(self):
        modulation = self._modulation("RURAL", modulation_fr="Milieu rural")
        Endemie.objects.filter(pk=self.endemie.pk).update(modulation=modulation)

        self.assertIsNone(construire_cache(self.point)["modulations"]["RURAL"]["saison"])

    def test_version_stable_puis_modifiee_avec_le_contenu(self):
        v1 = construire_cache(self.point, moment=moment(2026, 7, 1))["version"]
        v2 = construire_cache(self.point, moment=moment(2026, 7, 2))["version"]
        self.assertEqual(v1, v2)  # la date de génération n'entre pas dans la version

        self.risque.recommandation_fr = "<p>Nouvelle recommandation.</p>"
        self.risque.save()

        self.assertNotEqual(construire_cache(self.point)["version"], v1)

    def test_cache_serialisable_en_json(self):
        json.dumps(construire_cache(self.point))


class MessageDetailTests(SimpleTestCase):
    """Assemblage du message de l'écran de détail (implémentation de référence)."""

    def _risque(self, **kwargs):
        defaults = dict(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="Maladie parasitaire.", nature_du_risque_en="Parasitic disease.",
            recommandation_fr="<ol><li>Protégez-vous.</li></ol>",
            recommandation_en="<ol><li>Protect yourself.</li></ol>",
        )
        defaults.update(kwargs)
        return Risque(**defaults)

    def test_ordre_des_quatre_blocs(self):
        modulation = Modulation(code="RURAL", modulation_fr="Le risque est majoré en milieu rural.")

        html = message_detail_html(self._risque(), modulation, "fr")

        self.assertEqual(
            html,
            "<p>Vous vous trouvez actuellement dans une zone où existe un risque de Paludisme.</p>"
            "<p>Le risque est majoré en milieu rural.</p>"
            "<p>Maladie parasitaire.</p>"
            "<ol><li>Protégez-vous.</li></ol>",
        )

    def test_sans_modulation(self):
        html = message_detail_html(self._risque(), None, "fr")

        self.assertNotIn("milieu rural", html)
        self.assertTrue(html.startswith("<p>Vous vous trouvez actuellement"))
        self.assertIn("<p>Maladie parasitaire.</p>", html)

    def test_modulation_vide_ignoree(self):
        html = message_detail_html(self._risque(), Modulation(code="X", modulation_fr="  "), "fr")

        self.assertEqual(html.count("<p>"), 2)

    def test_recommandation_vide_omise(self):
        html = message_detail_html(self._risque(recommandation_fr=""), None, "fr")

        self.assertEqual(html.count("<p>"), 2)
        self.assertNotIn("<ol>", html)

    def test_anglais(self):
        modulation = Modulation(code="RURAL", modulation_fr="fr", modulation_en="Risk is higher in rural areas.")

        html = message_detail_html(self._risque(), modulation, "en")

        self.assertIn("risk of Malaria.</p>", html)
        self.assertIn("<p>Risk is higher in rural areas.</p>", html)
        self.assertIn("<p>Parasitic disease.</p>", html)
        self.assertIn("<li>Protect yourself.</li>", html)

    def test_texte_brut_echappe(self):
        html = message_detail_html(self._risque(nature_du_risque_fr="a < b & c"), None, "fr")

        self.assertIn("<p>a &lt; b &amp; c</p>", html)

    def test_description_avec_mise_en_forme_n_est_pas_echappee(self):
        # `nature_du_risque` peut contenir de l'HTML léger (ex. nom latin en italique).
        risque = self._risque(nature_du_risque_fr="Moustiques <i>Anopheles</i> infectés.")

        html = message_detail_html(risque, None, "fr")

        self.assertIn("<p>Moustiques <i>Anopheles</i> infectés.</p>", html)
        self.assertNotIn("&lt;i&gt;", html)

    def test_description_dangereuse_assainie(self):
        risque = self._risque(nature_du_risque_fr="<p>Ok</p><script>alert(1)</script>")

        self.assertNotIn("<script", message_detail_html(risque, None, "fr"))


class DetectionDansLeCacheTests(_Fixtures, TestCase):
    def setUp(self):
        self.risque = self._risque()
        self.point = Point(10.5, 10.5, srid=4326)

    def test_saison_a_cheval_sur_le_nouvel_an(self):
        modulation = self._modulation(saison_mois_debut=10, saison_mois_fin=2)
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        endemie = Endemie.objects.create(zone=zone, risque=self.risque, modulation=modulation)
        cache = construire_cache(self.point, tolerance=0)

        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, 12, 1)), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2027, 1, 15)), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, 6, 1)), [])

    def test_endemie_sans_modulation_active_toute_l_annee(self):
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        endemie = Endemie.objects.create(zone=zone, risque=self.risque)
        cache = construire_cache(self.point, tolerance=0)

        for mois in (1, 4, 8, 12):
            self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, mois, 10)), [endemie.pk])

    def test_modulation_sans_periode_active_toute_l_annee(self):
        modulation = self._modulation("RURAL", modulation_fr="Milieu rural")
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        endemie = Endemie.objects.create(zone=zone, risque=self.risque, modulation=modulation)
        cache = construire_cache(self.point, tolerance=0)

        self.assertEqual(endemies_actives_dans_cache(cache, 10, 10, moment(2026, 3, 10)), [endemie.pk])

    def test_periode_de_validite(self):
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        endemie = Endemie.objects.create(
            zone=zone, risque=self.risque,
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
        zone = self._zone(
            1, "Fidji-like",
            multi(rect(179, -19, 180, -17), rect(-180, -19, -179, -17)),
        )
        endemie = Endemie.objects.create(zone=zone, risque=self.risque)
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
        modulation_saisonniere = self._modulation(
            "PAL_T2", saison_mois_debut=6, saison_mois_fin=9
        )
        zone = self._zone(1, "Zone A", multi(rect(9, 9, 11, 11)))
        zone_b = self._zone(2, "Zone B", multi(rect(11.5, 9, 13, 11)))

        Endemie.objects.create(zone=zone, risque=risque)
        Endemie.objects.create(
            zone=zone, risque=risque, modulation=modulation_saisonniere,
            zone_exclue=multi(rect(9.5, 9.5, 10.5, 10.5)),
        )
        Endemie.objects.create(
            zone=zone_b, risque=risque,
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
