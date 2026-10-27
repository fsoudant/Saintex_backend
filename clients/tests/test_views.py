import datetime

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from clients.models import PreferenceChangeLog, Utilisateur


class AncienContactPositionSupprimeTests(APITestCase):
    """Depuis la révision d'octobre 2026 (cf. saintex-spec-technique.md §4/§5),
    le serveur ne reçoit plus la position du voyageur : l'ancien contact
    `/api/positions/` n'existe plus, remplacé par `/api/cache/`."""

    def test_l_ancien_endpoint_n_existe_plus(self):
        utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {utilisateur.api_token}")

        reponse = self.client.post("/api/positions/", {"lat": 48.85, "lon": 2.35}, format="json")

        self.assertEqual(reponse.status_code, 404)


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


class MeContratViewTests(APITestCase):
    """Cf. saintex-spec-technique.md §6 : écran de gestion du contrat,
    contract_start_date modifiable tant que le contrat n'a pas démarré."""

    def setUp(self):
        self.aujourdhui = timezone.localdate()
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.url = reverse("me_contrat")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")

    def test_get_returns_contract_info(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("contract_start_date", response.data)

    def test_patch_sets_start_date_within_bounds(self):
        nouvelle_date = self.aujourdhui + datetime.timedelta(days=30)
        response = self.client.patch(
            self.url, {"contract_start_date": nouvelle_date.isoformat()}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.utilisateur.refresh_from_db()
        self.assertEqual(self.utilisateur.contract_start_date, nouvelle_date)

    def test_patch_rejects_past_date(self):
        hier = self.aujourdhui - datetime.timedelta(days=1)
        response = self.client.patch(self.url, {"contract_start_date": hier.isoformat()}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_patch_rejects_change_once_contract_started(self):
        self.utilisateur.contract_start_date = self.aujourdhui - datetime.timedelta(days=1)
        self.utilisateur.save(update_fields=["contract_start_date"])

        nouvelle_date = self.aujourdhui + datetime.timedelta(days=10)
        response = self.client.patch(
            self.url, {"contract_start_date": nouvelle_date.isoformat()}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_patch_ignores_read_only_contract_duration(self):
        self.client.patch(self.url, {"contract_duration": 6}, format="json")
        self.utilisateur.refresh_from_db()
        self.assertIsNone(self.utilisateur.contract_duration)
