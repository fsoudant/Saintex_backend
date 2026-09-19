from datetime import datetime, timezone as dt_timezone

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import TestCase

from risks.detection import zones_actives_pour_point
from risks.models import ConduiteATenir, Endemie, Risque, Zone

PARIS = Point(2.35, 48.85, srid=4326)

# Carré englobant largement Paris.
CARRE_PARIS = MultiPolygon(
    Polygon(((2.0, 48.6), (2.7, 48.6), (2.7, 49.1), (2.0, 49.1), (2.0, 48.6)))
)

# Carré loin de Paris.
CARRE_LOINTAIN = MultiPolygon(
    Polygon(((10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0), (10.0, 10.0)))
)


class ZonesActivesPourPointTests(TestCase):
    def setUp(self):
        self.risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )

    def _conduite(self, code="PAL_T1", **kwargs):
        return ConduiteATenir.objects.create(
            code=code, risque=self.risque, nature_du_risque_fr="...", nature_du_risque_en="...",
            **kwargs,
        )

    def test_point_dans_zone_est_detecte(self):
        zone = Zone.objects.create(source_id=1, nom="Zone test", geom=CARRE_PARIS)
        endemie = Endemie.objects.create(zone=zone, conduite_a_tenir=self._conduite())

        self.assertEqual(zones_actives_pour_point(PARIS), [endemie])

    def test_point_hors_zone_non_detecte(self):
        zone = Zone.objects.create(source_id=1, nom="Zone lointaine", geom=CARRE_LOINTAIN)
        Endemie.objects.create(zone=zone, conduite_a_tenir=self._conduite())

        self.assertEqual(zones_actives_pour_point(PARIS), [])

    def test_point_sur_la_frontiere_est_couvert(self):
        # `covers` (contrairement à `contains`) inclut la frontière du
        # polygone — un voyageur exactement sur la limite doit être alerté.
        zone = Zone.objects.create(source_id=1, nom="Zone test", geom=CARRE_PARIS)
        endemie = Endemie.objects.create(zone=zone, conduite_a_tenir=self._conduite())

        point_frontiere = Point(2.0, 48.8, srid=4326)
        self.assertEqual(zones_actives_pour_point(point_frontiere), [endemie])

    def test_point_dans_zone_exclue_non_detecte(self):
        zone = Zone.objects.create(source_id=1, nom="Zone test", geom=CARRE_PARIS)
        # Petit carré autour de Paris, exclu du risque (ex. ville épargnée).
        exclusion = MultiPolygon(
            Polygon(((2.2, 48.7), (2.5, 48.7), (2.5, 49.0), (2.2, 49.0), (2.2, 48.7)))
        )
        Endemie.objects.create(
            zone=zone, conduite_a_tenir=self._conduite(), zone_exclue=exclusion
        )

        self.assertEqual(zones_actives_pour_point(PARIS), [])

    def test_hors_periode_de_validite_non_detecte(self):
        zone = Zone.objects.create(source_id=1, nom="Zone test", geom=CARRE_PARIS)
        Endemie.objects.create(
            zone=zone,
            conduite_a_tenir=self._conduite(),
            date_debut=datetime(2020, 1, 1, tzinfo=dt_timezone.utc),
            date_fin=datetime(2020, 12, 31, tzinfo=dt_timezone.utc),
        )

        self.assertEqual(
            zones_actives_pour_point(PARIS, moment=datetime(2026, 6, 1, tzinfo=dt_timezone.utc)),
            [],
        )

    def test_hors_saison_non_detecte(self):
        zone = Zone.objects.create(source_id=1, nom="Zone test", geom=CARRE_PARIS)
        # Risque saisonnier d'août (8) à novembre (11).
        conduite = self._conduite(saison_mois_debut=8, saison_mois_fin=11)
        Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        self.assertEqual(
            zones_actives_pour_point(PARIS, moment=datetime(2026, 3, 1, tzinfo=dt_timezone.utc)),
            [],
        )

    def test_en_saison_est_detecte(self):
        zone = Zone.objects.create(source_id=1, nom="Zone test", geom=CARRE_PARIS)
        conduite = self._conduite(saison_mois_debut=8, saison_mois_fin=11)
        endemie = Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        self.assertEqual(
            zones_actives_pour_point(PARIS, moment=datetime(2026, 9, 1, tzinfo=dt_timezone.utc)),
            [endemie],
        )

    def test_plusieurs_risques_actifs_sur_meme_zone(self):
        # Une même Zone peut porter plusieurs risques actifs simultanément
        # (ex. paludisme et encéphalite à tiques) — cf. docstring
        # UserRiskZoneStatus.
        zone = Zone.objects.create(source_id=1, nom="Zone test", geom=CARRE_PARIS)
        autre_risque = Risque.objects.create(
            code="ENC", libelle_fr="Encéphalite à tiques", libelle_en="Tick-borne encephalitis",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        autre_conduite = ConduiteATenir.objects.create(
            code="ENC_T1", risque=autre_risque, nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        endemie_1 = Endemie.objects.create(zone=zone, conduite_a_tenir=self._conduite())
        endemie_2 = Endemie.objects.create(zone=zone, conduite_a_tenir=autre_conduite)

        self.assertCountEqual(zones_actives_pour_point(PARIS), [endemie_1, endemie_2])
