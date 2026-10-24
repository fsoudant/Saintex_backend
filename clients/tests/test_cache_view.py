import datetime

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.urls import reverse
from rest_framework.test import APITestCase

from clients.models import NotificationLog, ParametreContrat, Utilisateur, UserRiskZoneStatus
from risks.models import ConduiteATenir, Endemie, Risque, Zone


def _rect(lon_min, lat_min, lon_max, lat_max):
    return MultiPolygon(Polygon((
        (lon_min, lat_min), (lon_max, lat_min), (lon_max, lat_max),
        (lon_min, lat_max), (lon_min, lat_min),
    )))


class CacheViewTests(APITestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(
            email="a@example.com", phone="+33600000000",
            contract_start_date=datetime.date(2026, 11, 1), contract_duration=3,
        )
        self.url = reverse("cache")
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
            recommandation_fr="<p>Protégez-vous.</p>",
        )
        self.zone = Zone.objects.create(source_id=1, nom="Zone A", geom=_rect(9, 9, 11, 11))
        self.endemie = Endemie.objects.create(zone=self.zone, conduite_a_tenir=conduite)
        self.conduite = conduite
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")

    def _post(self, **donnees):
        return self.client.post(self.url, {"lat": 10.5, "lon": 10.5, **donnees}, format="json")

    def test_rejette_une_requete_non_authentifiee(self):
        self.client.credentials()
        self.assertEqual(self._post().status_code, 401)

    def test_renvoie_le_cache_et_les_dates_du_contrat(self):
        reponse = self._post()

        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertEqual(corps["contrat"], {"debut": "2026-11-01", "expiration": "2027-02-01"})
        self.assertEqual([e["id"] for e in corps["cache"]["endemies"]], [self.endemie.pk])
        self.assertEqual(
            corps["cache"]["conduites"]["PAL_T1"]["recommandation_fr"], "<p>Protégez-vous.</p>"
        )

    def test_contrat_sans_dates(self):
        self.utilisateur.contract_start_date = None
        self.utilisateur.contract_duration = None
        self.utilisateur.save()

        self.assertEqual(self._post().json()["contrat"], {"debut": None, "expiration": None})

    def test_met_a_jour_last_contact_at(self):
        self._post()
        self.utilisateur.refresh_from_db()
        self.assertIsNotNone(self.utilisateur.last_contact_at)

    def test_n_enclenche_pas_le_moteur_d_alerte_serveur(self):
        # La détection se fait sur le téléphone (spec §4/§5) : ce contact ne
        # crée ni statut de zone ni notification côté serveur.
        self._post()
        self.assertFalse(UserRiskZoneStatus.objects.exists())
        self.assertFalse(NotificationLog.objects.exists())

    def test_version_identique_repond_inchange(self):
        version = self._post().json()["cache"]["version"]

        corps = self._post(cache_version=version).json()

        self.assertEqual(corps["cache"], {"version": version, "inchange": True})
        self.assertIn("contrat", corps)

    def test_version_differente_renvoie_le_cache_complet(self):
        corps = self._post(cache_version="ancienne").json()
        self.assertIn("endemies", corps["cache"])
        self.assertNotIn("inchange", corps["cache"])

    def test_le_rayon_vient_du_parametrage(self):
        # Zone à ~390 km du point.
        loin = Zone.objects.create(source_id=2, nom="Zone lointaine", geom=_rect(13, 13, 14, 14))
        e_loin = Endemie.objects.create(zone=loin, conduite_a_tenir=self.conduite)

        ids = [e["id"] for e in self._post().json()["cache"]["endemies"]]
        self.assertIn(e_loin.pk, ids)

        parametre = ParametreContrat.get_solo()
        parametre.cache_rayon_km = 100
        parametre.save()

        ids = [e["id"] for e in self._post().json()["cache"]["endemies"]]
        self.assertNotIn(e_loin.pk, ids)
        self.assertIn(self.endemie.pk, ids)

    def test_position_invalide(self):
        self.assertEqual(self._post(lat=95).status_code, 400)
