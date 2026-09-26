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
    VaccinationRisque,
)
from clients.notifications import envoyer_alerte_entree, envoyer_rappel_si_echeance
from risks.models import ConduiteATenir, Endemie, Risque, Zone


class _EndemieFixtureMixin:
    def _endemie(
        self,
        recommandation_non_protege_fr="Prenez un traitement préventif.",
        recommandation_protege_fr="",
    ):
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
            recommandation_non_protege_fr=recommandation_non_protege_fr,
            recommandation_protege_fr=recommandation_protege_fr,
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

    def test_message_contient_la_recommandation_non_protege_par_defaut(self):
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        self.assertIn("Prenez un traitement préventif.", logs[0].message)

    def test_message_utilise_la_recommandation_protege_si_vaccine(self):
        # Cf. §8, décision réunion médicale : deux messages distincts par
        # conduite à tenir selon la couverture vaccinale déclarée.
        endemie = self._endemie(
            recommandation_non_protege_fr="Prenez un traitement préventif.",
            recommandation_protege_fr="Restez vigilant malgré la vaccination.",
        )
        statut = UserRiskZoneStatus.objects.create(utilisateur=self.utilisateur, endemie=endemie)
        risque = endemie.conduite_a_tenir.risque
        risque.vaccin_disponible = True
        risque.save(update_fields=["vaccin_disponible"])
        VaccinationRisque.objects.create(utilisateur=self.utilisateur, risque=risque, vaccine=True)

        logs = envoyer_alerte_entree(self.utilisateur, statut, self.point)
        self.assertIn("Restez vigilant malgré la vaccination.", logs[0].message)
        self.assertNotIn("Prenez un traitement préventif.", logs[0].message)

    def test_message_retombe_sur_non_protege_si_texte_protege_absent(self):
        # recommandation_protege_fr pas encore rédigée par l'équipe médicale
        # (défaut de self._endemie()) : jamais de texte vide envoyé.
        risque = self.endemie.conduite_a_tenir.risque
        risque.vaccin_disponible = True
        risque.save(update_fields=["vaccin_disponible"])
        VaccinationRisque.objects.create(
            utilisateur=self.utilisateur, risque=risque, vaccine=True
        )

        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        self.assertIn("Prenez un traitement préventif.", logs[0].message)

    def test_message_non_module_si_non_vaccine(self):
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        self.assertIn("Prenez un traitement préventif.", logs[0].message)


class EnvoyerAlerteEntreeFamilleTests(_EndemieFixtureMixin, TestCase):
    """Cf. §8, décision réunion médicale : voyageur en famille — message
    composite tant que "tous protégés" n'est pas déclaré, message protégé
    simple sinon (cf. clients.notifications._composer_recommandation)."""

    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(
            email="a@example.com", phone="+33600000000", voyage_en_famille=True
        )
        self.endemie = self._endemie(
            recommandation_non_protege_fr="Prenez un traitement préventif.",
            recommandation_protege_fr="Restez vigilant malgré la vaccination.",
        )
        self.statut = UserRiskZoneStatus.objects.create(
            utilisateur=self.utilisateur, endemie=self.endemie
        )
        self.point = Point(2.35, 48.85, srid=4326)
        self.risque = self.endemie.conduite_a_tenir.risque
        self.risque.vaccin_disponible = True
        self.risque.save(update_fields=["vaccin_disponible"])

    def test_message_composite_si_pas_tous_proteges(self):
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        message = logs[0].message
        self.assertIn("Pour les membres non protégés contre Paludisme,", message)
        self.assertIn("Prenez un traitement préventif.", message)
        self.assertIn("Pour les membres protégés,", message)
        self.assertIn("Restez vigilant malgré la vaccination.", message)

    def test_message_protege_simple_si_tous_proteges_declare(self):
        VaccinationRisque.objects.create(
            utilisateur=self.utilisateur, risque=self.risque, vaccine=True
        )
        logs = envoyer_alerte_entree(self.utilisateur, self.statut, self.point)
        message = logs[0].message
        self.assertIn("Restez vigilant malgré la vaccination.", message)
        self.assertNotIn("Pour les membres non protégés", message)


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
