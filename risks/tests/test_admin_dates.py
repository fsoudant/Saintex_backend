"""Champ « date seule » de l'admin des end\u00e9mies (p\u00e9riode de validit\u00e9 sans heures)."""

import datetime

from django.test import SimpleTestCase
from django.utils import timezone

from risks.admin import _DateSeuleField, _jour


class DateSeuleFieldTests(SimpleTestCase):
    def test_debut_a_minuit(self):
        valeur = _DateSeuleField().clean("2026-08-15")

        self.assertEqual(timezone.localtime(valeur).time(), datetime.time(0, 0, 0))
        self.assertEqual(timezone.localtime(valeur).date(), datetime.date(2026, 8, 15))

    def test_fin_en_fin_de_journee(self):
        valeur = _DateSeuleField(fin_de_journee=True).clean("2026-12-31")

        self.assertEqual(timezone.localtime(valeur).time(), datetime.time(23, 59, 59))
        self.assertEqual(timezone.localtime(valeur).date(), datetime.date(2026, 12, 31))

    def test_vide_accepte_si_non_requis(self):
        self.assertIsNone(_DateSeuleField(required=False).clean(""))

    def test_affiche_seulement_le_jour(self):
        instant = timezone.make_aware(datetime.datetime(2026, 8, 15, 13, 45))

        self.assertEqual(_DateSeuleField().prepare_value(instant), datetime.date(2026, 8, 15))

    def test_non_modifie_quand_le_jour_est_le_meme(self):
        # L'heure stock\u00e9e (ici 00:00, ancienne donn\u00e9e) ne doit pas faire croire \u00e0
        # une modification quand l'utilisateur n'a rien chang\u00e9.
        instant = timezone.make_aware(datetime.datetime(2026, 8, 15, 0, 0))
        champ = _DateSeuleField(fin_de_journee=True)

        self.assertFalse(champ.has_changed(instant, "2026-08-15"))
        self.assertTrue(champ.has_changed(instant, "2026-08-16"))
        self.assertTrue(champ.has_changed(None, "2026-08-16"))

    def test_jour_pour_la_liste(self):
        self.assertEqual(_jour(timezone.make_aware(datetime.datetime(2026, 8, 5, 22, 30))), "05/08/2026")
        self.assertEqual(_jour(None), "")
