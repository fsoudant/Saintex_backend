from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from clients.management.commands.apercu_notification import estimer_segments_sms
from risks.models import ConduiteATenir, Risque


class ApercuNotificationCommandTests(TestCase):
    def setUp(self):
        risque = Risque.objects.create(
            code="PAL",
            libelle_fr="Paludisme",
            libelle_en="Malaria",
            nature_du_risque_fr="Transmission par moustique.",
            nature_du_risque_en="...",
        )
        ConduiteATenir.objects.create(
            code="PAL_T1",
            risque=risque,
            nature_du_risque_fr="...",
            nature_du_risque_en="...",
            recommandation_fr=(
                '<p><strong>Protégez-vous.</strong> Voir <a href="https://www.who.int/fr">l\'OMS</a>.</p>'
                "<ul><li>Un<ul><li>Un-a</li></ul></li></ul>"
            ),
        )

    def _appeler(self, *args):
        sortie = StringIO()
        call_command("apercu_notification", *args, stdout=sortie)
        return sortie.getvalue()

    def test_liste_les_conduites_sans_argument(self):
        self.assertIn("PAL_T1 — Paludisme", self._appeler())

    def test_affiche_texte_brut_et_html(self):
        sortie = self._appeler("PAL_T1")
        self.assertIn("Vous entrez dans une zone à risque : Paludisme.", sortie)
        self.assertIn("l'OMS (https://www.who.int/fr)", sortie)
        self.assertIn("  - Un-a", sortie)
        self.assertIn("segment(s) SMS", sortie)
        self.assertIn("<strong>Protégez-vous.</strong>", sortie)

    def test_option_rappel(self):
        self.assertIn("[Rappel]", self._appeler("PAL_T1", "--rappel"))

    def test_ecrit_la_page_html(self):
        with TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "apercu.html"
            self._appeler("PAL_T1", "--html-fichier", str(chemin))
            contenu = chemin.read_text(encoding="utf-8")
        self.assertIn('href="https://www.who.int/fr"', contenu)

    def test_code_inconnu(self):
        with self.assertRaises(CommandError):
            self._appeler("INCONNU")

    def test_n_ecrit_rien_en_base(self):
        from clients.models import NotificationLog

        self._appeler("PAL_T1")
        self.assertEqual(NotificationLog.objects.count(), 0)


class EstimerSegmentsSmsTests(SimpleTestCase):
    def test_court_en_gsm7(self):
        self.assertEqual(estimer_segments_sms("Bonjour é à"), ("GSM-7", 11, 1))

    def test_decoupe_en_segments_de_153(self):
        self.assertEqual(estimer_segments_sms("a" * 161), ("GSM-7", 161, 2))
        self.assertEqual(estimer_segments_sms("a" * 306), ("GSM-7", 306, 2))
        self.assertEqual(estimer_segments_sms("a" * 307), ("GSM-7", 307, 3))

    def test_caractere_etendu_compte_double(self):
        self.assertEqual(estimer_segments_sms("[x]"), ("GSM-7", 5, 1))

    def test_caractere_hors_gsm_passe_en_ucs2(self):
        self.assertEqual(estimer_segments_sms("l’OMS"), ("UCS-2", 5, 1))
        self.assertEqual(estimer_segments_sms("a" * 70 + "’"), ("UCS-2", 71, 2))
