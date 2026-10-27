"""Tests des messages envoyés par le serveur (cf. clients.notifications).

Les alertes et rappels de zone sont désormais affichés par le téléphone (cf.
saintex-spec-technique.md §4/§5) : leur envoi côté serveur n'existe plus. Les
SMS d'alerte rapportée et les avertissements de protection dégradée sont
testés dans test_rapports.py ; ce fichier couvre les canaux et la composition.
"""

from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from clients.models import NotificationLog, PushToken, Utilisateur
from clients.notifications import (
    SEUIL_RETARD_SMS_ALERTE,
    composer_sms_alerte,
    envoyer_relance_silence,
)


class CanauxActifsTests(TestCase):
    """Les canaux sont communs à tous les messages du serveur ; la relance
    "appli silencieuse" les utilise tous (SMS, email, push)."""

    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.utilisateur.last_contact_at = timezone.now() - timedelta(hours=8)
        self.utilisateur.save()

    def _canaux(self):
        return {log.canal for log in envoyer_relance_silence(self.utilisateur)}

    def test_sms_toujours_envoye(self):
        self.assertIn(NotificationLog.Canal.SMS, self._canaux())

    def test_email_envoye_si_actif(self):
        self.utilisateur.email_active = True
        self.utilisateur.push_active = False
        self.utilisateur.save()

        self.assertIn(NotificationLog.Canal.EMAIL, self._canaux())

    def test_email_absent_si_desactive(self):
        self.utilisateur.email_active = False
        self.utilisateur.save()

        self.assertNotIn(NotificationLog.Canal.EMAIL, self._canaux())

    def test_push_absent_sans_device_enregistre(self):
        self.utilisateur.push_active = True
        self.utilisateur.save()

        self.assertNotIn(NotificationLog.Canal.PUSH, self._canaux())

    def test_push_envoye_si_actif_et_device_enregistre(self):
        self.utilisateur.push_active = True
        self.utilisateur.save()
        PushToken.objects.create(
            utilisateur=self.utilisateur, plateforme=PushToken.Plateforme.IOS, token="tok-1"
        )

        self.assertIn(NotificationLog.Canal.PUSH, self._canaux())

    def test_logs_figent_le_message_et_le_destinataire(self):
        logs = envoyer_relance_silence(self.utilisateur)

        for log in logs:
            self.assertEqual(log.type_notification, NotificationLog.TypeNotification.RELANCE_SILENCE)
            self.assertEqual(log.statut, NotificationLog.Statut.ENVOYE)
            self.assertIn("8 h", log.message)
        self.assertEqual(
            {log.destinataire for log in logs}, {"+33600000000", "a@example.com"}
        )


class ComposerSmsAlerteTests(SimpleTestCase):
    """Texte du SMS court de sauvegarde (option B du §8)."""

    MOMENT = timezone.now()

    def _rapport(self, retard, libelle="Paludisme"):
        endemie = (
            SimpleNamespace(conduite_a_tenir=SimpleNamespace(risque=SimpleNamespace(libelle_fr=libelle)))
            if libelle
            else None
        )
        return SimpleNamespace(endemie=endemie, affichee_le=self.MOMENT - retard)

    def test_alerte_recente(self):
        texte = composer_sms_alerte(self._rapport(timedelta(minutes=5)), self.MOMENT)
        self.assertEqual(
            texte,
            "Saintex : vous entrez dans une zone à risque (Paludisme). "
            "Consultez l'application pour la conduite à tenir.",
        )

    def test_alerte_en_retard_en_heures(self):
        texte = composer_sms_alerte(self._rapport(timedelta(hours=5, minutes=30)), self.MOMENT)
        self.assertTrue(texte.startswith("Saintex : il y a 5 h, vous êtes entré(e) dans une zone à risque (Paludisme)."))

    def test_alerte_en_retard_en_jours(self):
        texte = composer_sms_alerte(self._rapport(timedelta(days=3)), self.MOMENT)
        self.assertIn("il y a 3 j,", texte)

    def test_seuil_de_retard(self):
        juste_avant = composer_sms_alerte(self._rapport(SEUIL_RETARD_SMS_ALERTE - timedelta(seconds=1)), self.MOMENT)
        juste_apres = composer_sms_alerte(self._rapport(SEUIL_RETARD_SMS_ALERTE), self.MOMENT)
        self.assertNotIn("il y a", juste_avant)
        self.assertIn("il y a 1 h,", juste_apres)

    def test_horloge_du_telephone_en_avance_n_affiche_pas_de_duree(self):
        texte = composer_sms_alerte(self._rapport(timedelta(hours=-2)), self.MOMENT)
        self.assertNotIn("il y a", texte)

    def test_endemie_inconnue(self):
        texte = composer_sms_alerte(self._rapport(timedelta(0), libelle=None), self.MOMENT)
        self.assertTrue(texte.startswith("Saintex : vous entrez dans une zone à risque."))
