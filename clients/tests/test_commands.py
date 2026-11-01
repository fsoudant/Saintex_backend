from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from clients.management.commands.apercu_notification import estimer_segments_sms
from clients.models import AlertReport, NotificationLog
from risks.models import Modulation, Risque


class ApercuNotificationCommandTests(TestCase):
    def setUp(self):
        risque = Risque.objects.create(
            code="PAL",
            libelle_fr="Paludisme",
            libelle_en="Malaria",
            nature_du_risque_fr="Transmission par moustique.",
            nature_du_risque_en="...",
            recommandation_fr=(
                '<p><strong>Protégez-vous.</strong> Voir <a href="https://www.who.int/fr">l\'OMS</a>.</p>'
                "<ul><li>Un<ul><li>Un-a</li></ul></li></ul>"
            ),
        )
        Modulation.objects.create(
            code="PAL_RURAL",
            modulation_fr="Le risque est majoré si vous séjournez en milieu rural.",
        )

    def _appeler(self, *args):
        sortie = StringIO()
        call_command("apercu_notification", *args, stdout=sortie)
        return sortie.getvalue()

    def test_liste_les_risques_et_les_modulations_sans_argument(self):
        sortie = self._appeler()
        self.assertIn("PAL — Paludisme", sortie)
        self.assertIn("PAL_RURAL — Le risque est majoré si vous séjournez en milieu rural.", sortie)

    def test_affiche_notification_detail_et_sms(self):
        sortie = self._appeler("PAL")

        # Notification locale du téléphone
        self.assertIn("Zone à risque : Paludisme", sortie)
        self.assertIn("Touchez pour lire la conduite à tenir.", sortie)
        # Écran de détail : HTML tel que transmis dans le cache, puis texte brut
        self.assertIn("<strong>Protégez-vous.</strong>", sortie)
        self.assertIn("l'OMS (https://www.who.int/fr)", sortie)
        self.assertIn("  - Un-a", sortie)
        # SMS de sauvegarde et sa taille
        self.assertIn("Saintex : vous entrez dans une zone à risque (Paludisme).", sortie)
        self.assertIn("GSM-7 → 1 segment(s) SMS", sortie)

    def test_sms_d_une_alerte_rapportee_avec_retard(self):
        sortie = self._appeler("PAL", "--retard-heures", "5")
        self.assertIn("il y a 5 h, vous êtes entré(e) dans une zone à risque (Paludisme)", sortie)

    def test_ecrit_la_page_html(self):
        with TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "apercu.html"
            self._appeler("PAL", "--html-fichier", str(chemin))
            contenu = chemin.read_text(encoding="utf-8")
        self.assertIn('href="https://www.who.int/fr"', contenu)
        self.assertIn("Zone à risque : Paludisme", contenu)

    def test_assemble_alerte_modulation_description_et_recommandation(self):
        sortie = self._appeler("PAL", "--modulation", "PAL_RURAL")

        alerte = sortie.index("Vous vous trouvez actuellement dans une zone où existe un risque de Paludisme.")
        modulation = sortie.index("Le risque est majoré si vous séjournez en milieu rural.")
        description = sortie.index("Transmission par moustique.")
        recommandation = sortie.index("<strong>Protégez-vous.</strong>")
        self.assertLess(alerte, modulation)
        self.assertLess(modulation, description)
        self.assertLess(description, recommandation)

    def test_modulation_inconnue(self):
        with self.assertRaises(CommandError):
            self._appeler("PAL", "--modulation", "INCONNUE")

    def test_code_inconnu(self):
        with self.assertRaises(CommandError):
            self._appeler("INCONNU")

    def test_n_ecrit_rien_en_base(self):
        self._appeler("PAL")
        self.assertEqual(NotificationLog.objects.count(), 0)
        self.assertEqual(AlertReport.objects.count(), 0)


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
