"""Tests unitaires du widget couleur nullable (risks.widgets)."""

from django import forms
from django.test import SimpleTestCase

from risks.widgets import (
    NullableColorWidget,
    RGBColorField,
    _hex_to_rgb_css,
    _rgb_to_hex,
)


class RgbToHexTests(SimpleTestCase):
    def test_couleur_valide(self):
        self.assertEqual(_rgb_to_hex("rgb(255,200,0)"), "#ffc800")

    def test_vide_retourne_noir(self):
        self.assertEqual(_rgb_to_hex(None), "#000000")
        self.assertEqual(_rgb_to_hex(""), "#000000")

    def test_illisible_retourne_noir(self):
        self.assertEqual(_rgb_to_hex("bleu"), "#000000")


class HexToRgbCssTests(SimpleTestCase):
    def test_conversion(self):
        self.assertEqual(_hex_to_rgb_css("#ffc800"), "rgb(255,200,0)")

    def test_sans_diese(self):
        self.assertEqual(_hex_to_rgb_css("ff0000"), "rgb(255,0,0)")

    def test_vide_ou_invalide(self):
        self.assertIsNone(_hex_to_rgb_css(None))
        self.assertIsNone(_hex_to_rgb_css(""))
        self.assertIsNone(_hex_to_rgb_css("zzz"))  # ValueError int(.., 16)
        self.assertIsNone(_hex_to_rgb_css("#1"))  # IndexError


class RGBColorFieldTests(SimpleTestCase):
    def test_widget_associe(self):
        self.assertIsInstance(RGBColorField().widget, NullableColorWidget)

    def test_compress_couleur_selectionnee(self):
        field = RGBColorField()
        self.assertEqual(field.compress(["#ff0000", False]), "rgb(255,0,0)")

    def test_compress_aucune_couleur(self):
        # La case "Aucune couleur" cochée -> NULL (et pas rgb(0,0,0) par défaut).
        field = RGBColorField()
        self.assertIsNone(field.compress(["#000000", True]))

    def test_compress_donnees_absentes(self):
        field = RGBColorField()
        self.assertIsNone(field.compress([]))
        self.assertIsNone(field.compress(None))

    def test_compress_hex_invalide_avec_case_visible(self):
        # Hex illisible mais case non cochée : on ne renvoie pas de couleur.
        field = RGBColorField()
        self.assertIsNone(field.compress([None, False]))


class NullableColorWidgetTests(SimpleTestCase):
    def test_decompress_couleur(self):
        widget = NullableColorWidget()
        self.assertEqual(widget.decompress("rgb(255,0,0)"), ["#ff0000", False])

    def test_decompress_vide(self):
        widget = NullableColorWidget()
        self.assertEqual(widget.decompress(None), ["#000000", True])

    def test_nombre_de_sous_widgets(self):
        widget = NullableColorWidget()
        self.assertIsInstance(widget.widgets[0], forms.TextInput)
        self.assertIsInstance(widget.widgets[1], forms.CheckboxInput)