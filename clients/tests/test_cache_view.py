import datetime

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

from clients.models import NotificationLog, Utilisateur, UserRiskZoneStatus
from risks.models import ConduiteATenir, Endemie, Risque, Zone


def _rect(lon_min, lat_min, lon_max, lat_max):
    return MultiPolygon(Polygon((
        (lon_min, lat_min), (lon_max, lat_min), (lon_max, lat_max),
        (lon_min, lat_max), (lon_min, lat_min),
    )))


class CacheViewTests(APITestCase):
    def setUp(self):
        # Le cache mondial est gardé en mémoire quelques minutes (risks.cache) :
        # on le vide pour que chaque test parte des données qu'il a créées.
        cache.clear()
        self.addCleanup(cache.clear)

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
        return self.client.post(self.url, donnees, format="json")

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

    def test_le_cache_est_mondial_sans_position(self):
        # Zones aux antipodes l'une de l'autre : toutes deux dans le cache, sans
        # qu'aucune position ait été transmise.
        loin = Zone.objects.create(source_id=2, nom="Zone lointaine", geom=_rect(170, -40, 172, -38))
        e_loin = Endemie.objects.create(zone=loin, conduite_a_tenir=self.conduite)

        corps = self._post().json()

        self.assertEqual(
            sorted(e["id"] for e in corps["cache"]["endemies"]),
            sorted([self.endemie.pk, e_loin.pk]),
        )
        self.assertIsNone(corps["cache"]["rayon_km"])

    def test_une_position_envoyee_est_ignoree(self):
        # Une ancienne version de l'appli pourrait joindre lat/lon : sans effet,
        # le cache reste identique et mondial.
        sans = self._post().json()["cache"]
        avec = self._post(lat=10.5, lon=10.5).json()["cache"]

        self.assertEqual(sans["version"], avec["version"])

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

    def test_le_cache_est_garde_en_memoire_puis_reconstruit_apres_expiration(self):
        premier = self._post().json()["cache"]["version"]

        # Modification en base : la version mémorisée est encore servie...
        self.conduite.recommandation_fr = "<p>Nouveau texte.</p>"
        self.conduite.save()
        self.assertEqual(self._post().json()["cache"]["version"], premier)

        # ... jusqu'à expiration de la mémoire (simulée ici en la vidant).
        cache.clear()
        self.assertNotEqual(self._post().json()["cache"]["version"], premier)
