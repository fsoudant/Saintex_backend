"""Tests des fiches Conseil (risks.models.Conseil, admin et widget) — fiches partagées
entre risques, reliées depuis une recommandation par un lien `conseil:<code>`
(cf. risks.richtext)."""

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.forms import modelform_factory
from django.test import RequestFactory, TestCase

from risks.admin import ConseilAdmin, ConseilAdminForm, RisqueAdminForm
from risks.models import Conseil, Risque
from risks.widgets import RichTextWidget

LIEN_MOUSTIQUES = '<p>Évitez les <a href="conseil:moustiques">piqûres de moustiques</a>.</p>'


def _conseil(code="moustiques", **kwargs):
    defaults = dict(titre_fr="Moustiques", titre_en="Mosquitoes", contenu_fr="<p>Répulsif.</p>")
    defaults.update(kwargs)
    return Conseil.objects.create(code=code, **defaults)


def _risque(code="CHI", **kwargs):
    defaults = dict(
        libelle_fr="Chikungunya", libelle_en="Chikungunya",
        nature_du_risque_fr="Transmission par moustique.", nature_du_risque_en="Mosquito-borne.",
    )
    defaults.update(kwargs)
    return Risque.objects.create(code=code, **defaults)


class ConseilModelTests(TestCase):
    def test_contenu_assaini_a_l_enregistrement(self):
        conseil = _conseil(contenu_fr="<p>Ok</p><script>alert(1)</script>", contenu_en="Texte brut")

        conseil.refresh_from_db()

        self.assertEqual(conseil.contenu_fr, "<p>Ok</p>")
        self.assertEqual(conseil.contenu_en, "<p>Texte brut</p>")

    def test_risques_utilisateurs(self):
        conseil = _conseil()
        _risque("CHI", recommandation_fr=LIEN_MOUSTIQUES)
        _risque("DEN", libelle_fr="Dengue", libelle_en="Dengue",
                recommandation_en='<p><a href="conseil:moustiques">mosquitoes</a></p>')
        _risque("PAL", libelle_fr="Paludisme", libelle_en="Malaria", recommandation_fr="<p>Sans lien.</p>")

        self.assertEqual(sorted(r.code for r in conseil.risques_utilisateurs()), ["CHI", "DEN"])

    def test_un_code_ne_masque_pas_un_autre_plus_long(self):
        # « moustiques » ne doit pas être vu comme utilisé par un lien vers « moustiques-tigres ».
        conseil = _conseil()
        _risque("CHI", recommandation_fr='<p><a href="conseil:moustiques-tigres">x</a></p>')

        self.assertFalse(conseil.risques_utilisateurs().exists())


class RisqueAdminFormTests(TestCase):
    Formulaire = modelform_factory(Risque, form=RisqueAdminForm, fields="__all__")

    def _donnees(self, **kwargs):
        donnees = dict(
            code="CHI", libelle_fr="Chikungunya", libelle_en="Chikungunya",
            nature_du_risque_fr="x", nature_du_risque_en="x",
            recommandation_fr="", recommandation_en="",
        )
        donnees.update(kwargs)
        return donnees

    def test_lien_vers_une_fiche_existante_accepte(self):
        _conseil()

        formulaire = self.Formulaire(self._donnees(recommandation_fr=LIEN_MOUSTIQUES))

        self.assertTrue(formulaire.is_valid(), formulaire.errors)

    def test_lien_vers_une_fiche_inconnue_refuse(self):
        formulaire = self.Formulaire(self._donnees(recommandation_fr=LIEN_MOUSTIQUES))

        self.assertFalse(formulaire.is_valid())
        self.assertIn("moustiques", formulaire.errors["recommandation_fr"][0])

    def test_verifie_aussi_la_version_anglaise(self):
        formulaire = self.Formulaire(self._donnees(recommandation_en='<p><a href="conseil:fantome">x</a></p>'))

        self.assertFalse(formulaire.is_valid())
        self.assertIn("recommandation_en", formulaire.errors)

    def test_code_mal_forme_refuse(self):
        formulaire = self.Formulaire(self._donnees(recommandation_fr='<p><a href="conseil:Mauvais code">x</a></p>'))

        self.assertFalse(formulaire.is_valid())

    def test_recommandation_sans_lien_conseil_inchangee(self):
        formulaire = self.Formulaire(
            self._donnees(recommandation_fr='<p>Voir <a href="https://www.who.int">l\'OMS</a>.</p>')
        )

        self.assertTrue(formulaire.is_valid(), formulaire.errors)


class ConseilAdminFormTests(TestCase):
    Formulaire = modelform_factory(Conseil, form=ConseilAdminForm, fields="__all__")

    def _donnees(self, **kwargs):
        donnees = dict(code="diarrhee", titre_fr="Diarrhée", titre_en="Diarrhoea", contenu_fr="", contenu_en="")
        donnees.update(kwargs)
        return donnees

    def test_fiche_simple_acceptee(self):
        formulaire = self.Formulaire(self._donnees(contenu_fr="<p>Buvez de l'eau traitée.</p>"))

        self.assertTrue(formulaire.is_valid(), formulaire.errors)

    def test_renvoi_vers_une_autre_fiche_refuse(self):
        _conseil()

        formulaire = self.Formulaire(self._donnees(contenu_fr=LIEN_MOUSTIQUES))

        self.assertFalse(formulaire.is_valid())
        self.assertIn("contenu_fr", formulaire.errors)

    def test_code_avec_espace_refuse(self):
        formulaire = self.Formulaire(self._donnees(code="eau potable"))

        self.assertFalse(formulaire.is_valid())
        self.assertIn("code", formulaire.errors)


class ConseilAdminTests(TestCase):
    def setUp(self):
        self.admin = ConseilAdmin(Conseil, AdminSite())
        self.requete = RequestFactory().get("/")
        self.requete.user = get_user_model().objects.create_superuser("admin", "admin@example.org", "x")

    def test_code_fige_apres_creation(self):
        conseil = _conseil()

        self.assertIn("code", self.admin.get_readonly_fields(self.requete, conseil))
        self.assertNotIn("code", self.admin.get_readonly_fields(self.requete, None))

    def test_suppression_interdite_tant_que_la_fiche_est_utilisee(self):
        conseil = _conseil()
        risque = _risque("CHI", recommandation_fr=LIEN_MOUSTIQUES)

        self.assertFalse(self.admin.has_delete_permission(self.requete, conseil))

        risque.recommandation_fr = "<p>Plus de lien.</p>"
        risque.save()

        self.assertTrue(self.admin.has_delete_permission(self.requete, conseil))

    def test_colonne_utilisee_par(self):
        conseil = _conseil()
        _risque("CHI", recommandation_fr=LIEN_MOUSTIQUES)

        self.assertEqual(self.admin.utilisee_par(conseil), "CHI")
        self.assertEqual(self.admin.utilisee_par(_conseil("diarrhee", titre_fr="Diarrhée")), "—")


class RichTextWidgetConseilsTests(TestCase):
    def test_bouton_et_liste_des_fiches(self):
        _conseil("moustiques", titre_fr="Protection contre les moustiques")
        _conseil("diarrhee", titre_fr="Diarrhée du voyageur")

        rendu = RichTextWidget(avec_conseils=True).render(
            "recommandation_fr", "", attrs={"id": "id_recommandation_fr"}
        )

        self.assertIn('data-cmd="conseil"', rendu)
        self.assertIn('<option value="moustiques">Protection contre les moustiques</option>', rendu)
        self.assertIn('<option value="diarrhee">Diarrhée du voyageur</option>', rendu)

    def test_titre_echappe(self):
        _conseil("x", titre_fr="<script>alert(1)</script>")

        rendu = RichTextWidget(avec_conseils=True).render("recommandation_fr", "", attrs={"id": "id_r"})

        self.assertNotIn("<script>alert(1)</script>", rendu)

    def test_bouton_present_meme_sans_fiche(self):
        # Le bouton explique alors qu'il faut d'abord créer une fiche.
        rendu = RichTextWidget(avec_conseils=True).render("recommandation_fr", "", attrs={"id": "id_r"})

        self.assertIn('data-cmd="conseil"', rendu)
