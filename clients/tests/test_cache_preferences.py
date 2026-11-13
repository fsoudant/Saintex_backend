from rest_framework.test import APITestCase

from clients.models import Utilisateur


class CachePreferencesTests(APITestCase):
    """Le téléphone affiche lui-même les alertes : il doit connaître le délai de
    rappel choisi par le voyageur (cf. CacheView, clé `preferences`)."""

    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(
            email="rappels@example.com", phone="+33600000042", reminder_delay="weekly"
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")

    def test_le_contact_renvoie_le_delai_de_rappel(self):
        reponse = self.client.post("/api/cache/", {}, format="json")

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data["preferences"], {"reminder_delay": "weekly"})

    def test_un_changement_de_preference_est_repris_au_contact_suivant(self):
        self.client.patch("/api/me/", {"reminder_delay": "once"}, format="json")

        reponse = self.client.post("/api/cache/", {}, format="json")

        self.assertEqual(reponse.data["preferences"], {"reminder_delay": "once"})
