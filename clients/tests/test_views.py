from django.contrib.gis.geos import MultiPolygon, Polygon
from django.urls import reverse
from rest_framework.test import APITestCase

from clients.models import NotificationLog, PreferenceChangeLog, Utilisateur, UserRiskZoneStatus
from risks.models import ConduiteATenir, Endemie, Risque, Zone


class PositionPollViewTests(APITestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.url = reverse("position_poll")

    def test_rejects_unauthenticated_request(self):
        response = self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_creates_position_and_updates_last_contact(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")
        response = self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")

        self.assertEqual(response.status_code, 201)
        self.utilisateur.refresh_from_db()
        self.assertIsNotNone(self.utilisateur.last_contact_at)

    def test_entering_risk_zone_creates_status(self):
        # Carré englobant largement Paris (2.35, 48.85).
        zone = Zone.objects.create(
            source_id=1,
            nom="Zone test",
            geom=MultiPolygon(
                Polygon(((2.0, 48.6), (2.7, 48.6), (2.7, 49.1), (2.0, 49.1), (2.0, 48.6)))
            ),
        )
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        endemie = Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")
        response = self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            UserRiskZoneStatus.objects.filter(utilisateur=self.utilisateur, endemie=endemie).exists()
        )

    def test_entering_risk_zone_sends_entry_alert(self):
        # Cf. clients.notifications : la première détection d'une zone
        # déclenche une alerte d'entrée (§8), envoyée au minimum par SMS.
        zone = Zone.objects.create(
            source_id=3,
            nom="Zone test alerte",
            geom=MultiPolygon(
                Polygon(((2.0, 48.6), (2.7, 48.6), (2.7, 49.1), (2.0, 49.1), (2.0, 48.6)))
            ),
        )
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")
        self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")

        self.assertTrue(
            NotificationLog.objects.filter(
                utilisateur=self.utilisateur,
                type_notification=NotificationLog.TypeNotification.ALERTE_ZONE,
                canal=NotificationLog.Canal.SMS,
            ).exists()
        )

    def test_second_checkin_in_same_zone_sends_no_duplicate_alert(self):
        # Cf. clients.notifications.envoyer_rappel_si_echeance : une zone
        # déjà active ne redonne pas lieu à une alerte d'entrée, et pas non
        # plus à un rappel avant l'échéance de reminder_delay.
        zone = Zone.objects.create(
            source_id=4,
            nom="Zone test rappel",
            geom=MultiPolygon(
                Polygon(((2.0, 48.6), (2.7, 48.6), (2.7, 49.1), (2.0, 49.1), (2.0, 48.6)))
            ),
        )
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")
        self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")
        self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")

        self.assertEqual(
            NotificationLog.objects.filter(
                utilisateur=self.utilisateur,
                type_notification=NotificationLog.TypeNotification.ALERTE_ZONE,
                canal=NotificationLog.Canal.SMS,
            ).count(),
            1,
        )
        self.assertEqual(
            NotificationLog.objects.filter(
                utilisateur=self.utilisateur,
                type_notification=NotificationLog.TypeNotification.RAPPEL_ZONE,
            ).count(),
            0,
        )

    def test_position_outside_any_zone_creates_no_status(self):
        zone = Zone.objects.create(
            source_id=2,
            nom="Zone lointaine",
            geom=MultiPolygon(
                Polygon(((10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0), (10.0, 10.0)))
            ),
        )
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")
        response = self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertFalse(UserRiskZoneStatus.objects.filter(utilisateur=self.utilisateur).exists())

    def test_rejects_out_of_range_coordinates(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")
        response = self.client.post(self.url, {"lat": 999, "lon": 2.35}, format="json")
        self.assertEqual(response.status_code, 400)


class MePreferencesViewTests(APITestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.url = reverse("me_preferences")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")

    def test_get_returns_current_preferences(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "a@example.com")

    def test_patch_updates_preference_and_logs_change(self):
        response = self.client.patch(self.url, {"push_active": False}, format="json")

        self.assertEqual(response.status_code, 200)
        self.utilisateur.refresh_from_db()
        self.assertFalse(self.utilisateur.push_active)
        self.assertEqual(
            PreferenceChangeLog.objects.filter(utilisateur=self.utilisateur, champ="push_active").count(),
            1,
        )

    def test_patch_ignores_read_only_fields(self):
        self.client.patch(self.url, {"email": "hacked@example.com"}, format="json")
        self.utilisateur.refresh_from_db()
        self.assertEqual(self.utilisateur.email, "a@example.com")
