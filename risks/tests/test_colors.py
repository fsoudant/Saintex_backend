"""Tests unitaires de risks.colors (parsing, moyenne, sérialisation CSS des couleurs)."""

from django.test import SimpleTestCase

from risks.colors import average_rgb, parse_rgb, to_css


class ParseRgbTests(SimpleTestCase):
    def test_couleur_canonique(self):
        self.assertEqual(parse_rgb("rgb(255,200,0)"), (255, 200, 0))

    def test_espaces_autour_des_valeurs(self):
        self.assertEqual(parse_rgb("  rgb( 10, 20 , 30 )  "), (10, 20, 30))

    def test_valeurs_vides(self):
        self.assertIsNone(parse_rgb(""))
        self.assertIsNone(parse_rgb(None))

    def test_format_illisible(self):
        self.assertIsNone(parse_rgb("bleu"))
        self.assertIsNone(parse_rgb("rgb(1,2)"))
        self.assertIsNone(parse_rgb("#ff0000"))


class AverageRgbTests(SimpleTestCase):
    def test_liste_vide(self):
        self.assertIsNone(average_rgb([]))

    def test_uniquement_vides(self):
        self.assertIsNone(average_rgb([None, None]))

    def test_moyenne_tronquee(self):
        self.assertEqual(average_rgb([(10, 20, 30), (20, 40, 50)]), (15, 30, 40))

    def test_arrondi_par_defaut(self):
        self.assertEqual(average_rgb([(255, 255, 255), (0, 0, 0)]), (127, 127, 127))

    def test_ignore_les_vides(self):
        # Les exclusions sans couleur ne doivent pas fausser la moyenne.
        self.assertEqual(
            average_rgb([(255, 0, 0), None, (255, 0, 0)]),
            (255, 0, 0),
        )

    def test_une_seule_couleur(self):
        self.assertEqual(average_rgb([(12, 34, 56)]), (12, 34, 56))


class ToCssTests(SimpleTestCase):
    def test_conversion(self):
        self.assertEqual(to_css((1, 2, 3)), "rgb(1,2,3)")

    def test_none(self):
        self.assertIsNone(to_css(None))