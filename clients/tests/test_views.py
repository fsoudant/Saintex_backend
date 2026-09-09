from django.urls import reverse
from rest_framework.test import APITestCase

from clients.models import PreferenceChangeLog, Position, Utilisateur


class PositionPollViewTests(APITestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.url = reverse("position_poll")

    def test_rejects_unauthenticated_request(self):
        response = self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")
        self.assertEqual(response.status_code, 401)

    def test_creates_position_and_updates_last_seen(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")
        response = self.client.post(self.url, {"lat": 48.85, "lon": 2.35}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Position.objects.filter(utilisateur=self.utilisateur).count(), 1)
        self.utilisateur.refresh_from_db()
        self.assertIsNotNone(self.utilisateur.last_seen_at)

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
