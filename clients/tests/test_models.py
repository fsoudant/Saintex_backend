from django.test import TestCase

from clients.models import PreferenceChangeLog, Utilisateur


class UtilisateurTests(TestCase):
    def test_api_token_generated_automatically(self):
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.assertTrue(u.api_token)

    def test_api_token_unique_per_user(self):
        u1 = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u2 = Utilisateur.objects.create(email="b@example.com", phone="+33600000001")
        self.assertNotEqual(u1.api_token, u2.api_token)

    def test_is_authenticated_always_true(self):
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.assertTrue(u.is_authenticated)


class PreferenceChangeLogTests(TestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")

    def test_enregistrer_creates_entry_on_change(self):
        entry = PreferenceChangeLog.enregistrer(self.utilisateur, "push_active", "True", "False")
        self.assertIsNotNone(entry)
        self.assertEqual(PreferenceChangeLog.objects.count(), 1)

    def test_enregistrer_is_noop_when_value_unchanged(self):
        entry = PreferenceChangeLog.enregistrer(self.utilisateur, "push_active", "True", "True")
        self.assertIsNone(entry)
        self.assertEqual(PreferenceChangeLog.objects.count(), 0)

    def test_enregistrer_rejects_untracked_field(self):
        with self.assertRaises(ValueError):
            PreferenceChangeLog.enregistrer(self.utilisateur, "email", "a@example.com", "b@example.com")
