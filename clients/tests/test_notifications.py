"""Tests du moteur de décision/envoi (Phase 3, cf. clients.notifications)."""

from datetime import timedelta

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from clients.models import (
    NotificationLog,
    PushToken,
    Utilisateur,
    UserRiskZoneStatus,
)
from clients.notifications import envoyer_alerte_entree, envoyer_rappel_si_echeance
from risks.models import ConduiteATenir, Endemie, Risque, Zone


class _EndemieFixtureMixin:
    def _endemie(self, recommandation_fr="Prenez un traitement préventif."):
        zone = Zone.objects.create(source_id=1, nom="Zone test")
        risque = Risque.objects.create(
            code="PAL",
            libelle_fr="Paludisme",
            libelle_en="Malaria",
            nature_du_risque_fr="Transmission par moustique.",
            nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1",
            risque=risque,
            nature_du_risque_fr="...",
            nature_du_risque_en="...",
            recommandation_fr=recommandation_fr,
        )
        return Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)


class EnvoyerAlerteEntreeTests(_EndemieFixtureMixin, TestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.endemie = self._endemie()
        self.statut = UserRiskZoneStatus.objects.create(
            utilisateur=self.utilisateur, endemie=self.endemie
        )
        self.point = Point(2.35, 48.85, srid=4326)

    def test_sms_toujours_envoye(self):
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        canaux = {log.canal for log in logs}
        self.assertIn(NotificationLog.Canal.SMS, canaux)

    def test_email_envoye_si_actif(self):
        self.utilisateur.email_active = True
        self.utilisateur.push_active = False
        self.utilisateur.save()

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        canaux = {log.canal for log in logs}
        self.assertIn(NotificationLog.Canal.EMAIL, canaux)

    def test_email_absent_si_desactive(self):
        self.utilisateur.email_active = False
        self.utilisateur.save()

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        canaux = {log.canal for log in logs}
        self.assertNotIn(NotificationLog.Canal.EMAIL, canaux)

    def test_push_absent_sans_device_enregistre(self):
        self.utilisateur.push_active = True
        self.utilisateur.save()

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        canaux = {log.canal for log in logs}
        self.assertNotIn(NotificationLog.Canal.PUSH, canaux)

    def test_push_envoye_si_actif_et_device_enregistre(self):
        self.utilisateur.push_active = True
        self.utilisateur.save()
        PushToken.objects.create(
            utilisateur=self.utilisateur, plateforme=PushToken.Plateforme.IOS, token="tok-1"
        )

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        canaux = {log.canal for log in logs}
        self.assertIn(NotificationLog.Canal.PUSH, canaux)

    def test_logs_portent_le_bon_type_et_la_position(self):
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        for log in logs:
            self.assertEqual(log.type_notification, NotificationLog.TypeNotification.ALERTE_ZONE)
            self.assertEqual(log.endemie, self.endemie)
            self.assertEqual(log.position, self.point)
            self.assertEqual(log.statut, NotificationLog.Statut.ENVOYE)

    def test_message_contient_la_recommandation(self):
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        self.assertIn("Prenez un traitement préventif.", logs[0].message)

    def test_message_identique_pour_tous_les_voyageurs(self):
        # Cf. §8, décision d'octobre 2026 : plus de modulation selon une
        # couverture vaccinale déclarée, un seul texte pour tout le monde.
        autre = Utilisateur.objects.create(email="b@example.com", phone="+33600000001")
        statut_autre = UserRiskZoneStatus.objects.create(
            utilisateur=autre, endemie=self.endemie
        )
        logs_a = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        logs_b = envoyer_alerte_entree(autre, statut_autre, self.point)
        self.assertEqual(logs_a[0].message, logs_b[0].message)

    def test_message_retombe_sur_la_nature_du_risque_si_recommandation_vide(self):
        # Jamais de texte vide envoyé tant que l'équipe médicale n'a pas
        # rédigé la recommandation.
        conduite = self.endemie.conduite_a_tenir
        conduite.recommandation_fr = ""
        conduite.save(update_fields=["recommandation_fr"])

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        self.assertIn("Transmission par moustique.", logs[0].message)

    def test_email_porte_le_html_et_le_sms_le_texte_brut(self):
        # Cf. §8, texte enrichi : seul l'email affiche la mise en forme, SMS et
        # push reçoivent une version texte brut (lien -> "texte (url)").
        conduite = self.endemie.conduite_a_tenir
        conduite.recommandation_fr = (
            '<p><strong>Protégez-vous.</strong> Voir <a href="https://www.who.int/fr">l\'OMS</a>.</p>'
        )
        conduite.save()

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        par_canal = {log.canal: log for log in logs}

        email = par_canal[NotificationLog.Canal.EMAIL]
        self.assertIn("<strong>Protégez-vous.</strong>", email.message_html)
        self.assertIn('href="https://www.who.int/fr"', email.message_html)

        sms = par_canal[NotificationLog.Canal.SMS]
        self.assertEqual(sms.message_html, "")
        self.assertNotIn("<", sms.message)
        self.assertIn("Protégez-vous. Voir l'OMS (https://www.who.int/fr).", sms.message)

    def test_recommandation_non_rediges_donne_aussi_un_email_html(self):
        conduite = self.endemie.conduite_a_tenir
        conduite.recommandation_fr = ""
        conduite.save()

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        email = next(log for log in logs if log.canal == NotificationLog.Canal.EMAIL)
        self.assertIn("<p>Transmission par moustique.</p>", email.message_html)

    def test_message_ne_contient_plus_de_mention_non_protege(self):
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        self.assertNotIn("NON PROTÉGÉ", logs[0].message.upper())


class EnvoyerRappelSiEcheanceTests(_EndemieFixtureMixin, TestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(
            email="a@example.com",
            phone="+33600000000",
            reminder_delay=Utilisateur.DelaiRappel.QUOTIDIEN,
        )
        self.endemie = self._endemie()
        self.statut = UserRiskZoneStatus.objects.create(
            utilisateur=self.utilisateur, endemie=self.endemie
        )
        self.point = Point(2.35, 48.85, srid=4326)

    def test_aucun_rappel_avant_echeance(self):
        moment = self.statut.entered_at + timedelta(hours=1)
        logs = envoyer_rappel_si_echeance(self.utilisateur, self.statut, self.point, moment=moment)
        self.assertEqual(logs, [])

    def test_rappel_envoye_apres_echeance(self):
        moment = self.statut.entered_at + timedelta(days=1, minutes=1)
        logs = envoyer_rappel_si_echeance(self.utilisateur, self.statut, self.point, moment=moment)

        self.assertTrue(len(logs) > 0)
        self.assertTrue(
            all(
                log.type_notification == NotificationLog.TypeNotification.RAPPEL_ZONE
                for log in logs
            )
        )
        self.statut.refresh_from_db()
        self.assertEqual(self.statut.last_reminded_at, moment)

    def test_aucun_rappel_si_delai_une_fois(self):
        self.utilisateur.reminder_delay = Utilisateur.DelaiRappel.UNE_FOIS
        self.utilisateur.save()
        moment = self.statut.entered_at + timedelta(days=30)

        logs = envoyer_rappel_si_echeance(self.utilisateur, self.statut, self.point, moment=moment)
        self.assertEqual(logs, [])

    def test_pas_de_second_rappel_avant_nouvelle_echeance(self):
        premier_moment = self.statut.entered_at + timedelta(days=1, minutes=1)
        envoyer_rappel_si_echeance(self.utilisateur, self.statut, self.point, moment=premier_moment)
        self.statut.refresh_from_db()

        second_moment = premier_moment + timedelta(hours=1)
        logs = envoyer_rappel_si_echeance(
            self.utilisateur, self.statut, self.point, moment=second_moment
        )
        self.assertEqual(logs, [])

    def test_moment_par_defaut_est_maintenant(self):
        self.statut.entered_at = timezone.now() - timedelta(days=2)
        self.statut.save(update_fields=["entered_at"])

        logs = envoyer_rappel_si_echeance(self.utilisateur, self.statut, self.point)
        self.assertTrue(len(logs) > 0)
