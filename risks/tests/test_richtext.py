"""Tests du texte enrichi des recommandations (risks.richtext, widget et
ConduiteATenir.save) — cf. saintex-spec-technique.md §8."""

from unittest import mock

from django.db import models
from django.test import SimpleTestCase

from risks.models import ConduiteATenir
from risks.richtext import html_to_text, looks_like_html, sanitize_html, text_to_html
from risks.widgets import RichTextWidget


class TextToHtmlTests(SimpleTestCase):
    def test_echappe_les_caracteres_speciaux(self):
        self.assertEqual(text_to_html("moins de <1500 m & plus"), "<p>moins de &lt;1500 m &amp; plus</p>")

    def test_paragraphes_et_retours_a_la_ligne(self):
        self.assertEqual(
            text_to_html("Ligne 1\nLigne 2\n\nParagraphe 2"),
            "<p>Ligne 1<br>Ligne 2</p><p>Paragraphe 2</p>",
        )

    def test_vide(self):
        self.assertEqual(text_to_html(""), "")
        self.assertEqual(text_to_html(None), "")


class LooksLikeHtmlTests(SimpleTestCase):
    def test_balise_connue(self):
        self.assertTrue(looks_like_html("<p>x</p>"))
        self.assertTrue(looks_like_html("a<br>b"))

    def test_texte_brut_avec_chevron(self):
        self.assertFalse(looks_like_html("altitude <1500 m"))
        self.assertFalse(looks_like_html("a < b et c > d"))


class SanitizeHtmlTests(SimpleTestCase):
    def test_conserve_la_mise_en_forme_autorisee(self):
        html = "<p><strong>Gras</strong> <em>italique</em> <small>petit</small> <big>grand</big></p><h3>Titre</h3>"
        self.assertEqual(sanitize_html(html), html)

    def test_supprime_script_et_attributs_dangereux(self):
        propre = sanitize_html('<p onclick="x()">ok</p><script>alert(1)</script><img src=x onerror=alert(1)>')
        self.assertEqual(propre, "<p>ok</p>")

    def test_lien_https_conserve_avec_rel(self):
        propre = sanitize_html('<a href="https://www.who.int/fr">OMS</a>')
        self.assertIn('href="https://www.who.int/fr"', propre)
        self.assertIn('rel="noopener noreferrer"', propre)

    def test_lien_javascript_refuse(self):
        propre = sanitize_html('<a href="javascript:alert(1)">piege</a>')
        self.assertNotIn("javascript", propre)
        self.assertIn("piege", propre)

    def test_attributs_de_style_retires(self):
        propre = sanitize_html('<p style="color:red">x</p>')
        self.assertEqual(propre, "<p>x</p>")

    def test_div_devient_paragraphe(self):
        self.assertEqual(sanitize_html("<div>un</div><div>deux</div>"), "<p>un</p><p>deux</p>")

    def test_texte_brut_converti(self):
        self.assertEqual(sanitize_html("Protection contre les moustiques."), "<p>Protection contre les moustiques.</p>")

    def test_contenu_vide_de_l_editeur(self):
        self.assertEqual(sanitize_html("<p><br></p>"), "")
        self.assertEqual(sanitize_html("   "), "")
        self.assertEqual(sanitize_html(None), "")

    def test_idempotent(self):
        premier = sanitize_html("<p>a <b>b</b> <a href=\"https://exemple.org\">c</a></p>")
        self.assertEqual(sanitize_html(premier), premier)


class HtmlToTextTests(SimpleTestCase):
    def test_paragraphes_et_br(self):
        self.assertEqual(html_to_text("<p>Un</p><p>Deux<br>trois</p>"), "Un\n\nDeux\ntrois")

    def test_lien_devient_texte_et_url(self):
        self.assertEqual(
            html_to_text('<p>Voir <a href="https://www.who.int/fr">l\'OMS</a>.</p>'),
            "Voir l'OMS (https://www.who.int/fr).",
        )

    def test_lien_dont_le_texte_est_l_adresse(self):
        self.assertEqual(
            html_to_text('<a href="https://www.who.int">https://www.who.int</a>'),
            "https://www.who.int",
        )

    def test_liste_a_puces(self):
        self.assertEqual(html_to_text("<p>A faire :</p><ul><li>Un</li><li>Deux</li></ul>"), "A faire :\n\n- Un\n- Deux")

    def test_entites_decodees(self):
        self.assertEqual(html_to_text("<p>a &amp; b &lt;1500 m</p>"), "a & b <1500 m")

    def test_mise_en_forme_ignoree(self):
        self.assertEqual(html_to_text("<p><strong>Gras</strong> et <em>italique</em></p>"), "Gras et italique")

    def test_vide(self):
        self.assertEqual(html_to_text(""), "")
        self.assertEqual(html_to_text(None), "")


class ConduiteATenirSaveTests(SimpleTestCase):
    def test_save_assainit_les_recommandations(self):
        conduite = ConduiteATenir(
            code="X",
            recommandation_fr="<p>ok</p><script>alert(1)</script>",
            recommandation_en="Plain text <1500 m",
        )
        with mock.patch.object(models.Model, "save"):
            conduite.save()
        self.assertEqual(conduite.recommandation_fr, "<p>ok</p>")
        self.assertEqual(conduite.recommandation_en, "<p>Plain text &lt;1500 m</p>")


class RichTextWidgetTests(SimpleTestCase):
    def test_valeur_reinjectee_assainie(self):
        rendu = RichTextWidget().render(
            "recommandation_fr",
            "<b>ok</b><img src=x onerror=alert(1)><script>alert(2)</script>",
            attrs={"id": "id_recommandation_fr"},
        )
        self.assertIn("<b>ok</b>", rendu)
        self.assertNotIn("onerror", rendu)
        self.assertNotIn("alert(2)", rendu)

    def test_contient_le_champ_et_la_barre_d_outils(self):
        rendu = RichTextWidget().render("recommandation_fr", "", attrs={"id": "id_recommandation_fr"})
        self.assertIn('name="recommandation_fr"', rendu)
        self.assertIn('data-cmd="link"', rendu)
