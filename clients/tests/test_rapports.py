import uuid
from datetime import timedelta

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from clients.management.commands.apercu_notification import estimer_segments_sms
from clients.models import AlertReport, NotificationLog, Utilisateur
from risks.models import ConduiteATenir, Endemie, Risque, Zone


def _rect(lon_min, lat_min, lon_max, lat_max):
    return MultiPolygon(Polygon((
        (lon_min, lat_min), (lon_max, lat_min), (lon_max, lat_max),
        (lon_min, lat_max), (lon_min, lat_min),
    )))


class _ContactFixtures(APITestCase):
    """Utilisateur au contrat en cours + une endémie, et un helper de contact."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        aujourdhui = timezone.localdate()
        self.utilisateur = Utilisateur.objects.create(
            email="a@example.com", phone="+33600000000",
            contract_start_date=aujourdhui - timedelta(days=1), contract_duration=3,
        )
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        self.zone = Zone.objects.create(source_id=1, nom="Zone A", geom=_rect(9, 9, 11, 11))
        self.endemie = Endemie.objects.create(zone=self.zone, conduite_a_tenir=conduite)
        self.url = reverse("cache")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.utilisateur.api_token}")

    def _contact(self, **donnees):
        return self.client.post(self.url, donnees, format="json")

    def _rapport(self, **surcharges):
        rapport = {
            "id": str(uuid.uuid4()),
            "endemie": self.endemie.pk,
            "type": "entree",
            "affichee_le": timezone.now().isoformat(),
        }
        rapport.update(surcharges)
        return rapport


class RapportsAlerteTests(_ContactFixtures):
    def test_enregistre_un_rapport_d_entree_et_l_acquitte(self):
        rapport = self._rapport()

        reponse = self._contact(rapports=[rapport])

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()["rapports_recus"], [rapport["id"]])
        enregistre = AlertReport.objects.get()
        self.assertEqual(enregistre.utilisateur, self.utilisateur)
        self.assertEqual(enregistre.type_alerte, AlertReport.Type.ENTREE)
        self.assertEqual(enregistre.endemie, self.endemie)
        self.assertEqual(str(enregistre.identifiant_client), rapport["id"])

    def test_zone_et_risque_recopies_en_texte(self):
        self._contact(rapports=[self._rapport()])

        enregistre = AlertReport.objects.get()
        self.assertEqual(enregistre.zone_nom, "Zone A")
        self.assertEqual(enregistre.risque_code, "PAL")

    def test_alerte_d_entree_declenche_un_sms_court_seulement(self):
        self._contact(rapports=[self._rapport()])

        logs = NotificationLog.objects.all()
        self.assertEqual(logs.count(), 1)
        sms = logs.get()
        self.assertEqual(sms.canal, NotificationLog.Canal.SMS)
        self.assertEqual(sms.type_notification, NotificationLog.TypeNotification.ALERTE_ZONE)
        self.assertEqual(sms.destinataire, "+33600000000")
        self.assertEqual(sms.endemie, self.endemie)
        self.assertIn("vous entrez dans une zone à risque (Paludisme)", sms.message)
        self.assertEqual(sms.message_html, "")

    def test_le_sms_tient_dans_l_alphabet_sms_standard(self):
        self._contact(rapports=[self._rapport()])

        encodage, _longueur, segments = estimer_segments_sms(NotificationLog.objects.get().message)

        self.assertEqual((encodage, segments), ("GSM-7", 1))

    def test_un_rappel_est_enregistre_sans_sms(self):
        self._contact(rapports=[self._rapport(type="rappel")])

        self.assertEqual(AlertReport.objects.get().type_alerte, AlertReport.Type.RAPPEL)
        self.assertFalse(NotificationLog.objects.exists())

    def test_rapport_renvoye_sans_doublon_ni_second_sms(self):
        rapport = self._rapport()
        self._contact(rapports=[rapport])

        reponse = self._contact(rapports=[rapport])

        self.assertEqual(reponse.json()["rapports_recus"], [rapport["id"]])
        self.assertEqual(AlertReport.objects.count(), 1)
        self.assertEqual(NotificationLog.objects.count(), 1)

    def test_rapport_renvoye_met_a_jour_l_ouverture(self):
        rapport = self._rapport()
        self._contact(rapports=[rapport])
        self.assertIsNone(AlertReport.objects.get().ouverte_le)

        ouverte = timezone.now().isoformat()
        self._contact(rapports=[{**rapport, "ouverte_le": ouverte}])

        self.assertIsNotNone(AlertReport.objects.get().ouverte_le)
        self.assertEqual(AlertReport.objects.count(), 1)

    def test_rapport_en_retard_precise_depuis_combien_de_temps(self):
        affichee = (timezone.now() - timedelta(hours=5, minutes=10)).isoformat()

        self._contact(rapports=[self._rapport(affichee_le=affichee)])

        self.assertIn("il y a 5 h, vous êtes entré(e) dans une zone à risque (Paludisme)", NotificationLog.objects.get().message)

    def test_rapport_recent_ne_mentionne_pas_de_duree(self):
        affichee = (timezone.now() - timedelta(minutes=10)).isoformat()

        self._contact(rapports=[self._rapport(affichee_le=affichee)])

        self.assertNotIn("il y a", NotificationLog.objects.get().message)

    def test_endemie_inconnue_enregistree_quand_meme(self):
        self._contact(rapports=[self._rapport(endemie=999999)])

        enregistre = AlertReport.objects.get()
        self.assertIsNone(enregistre.endemie)
        self.assertEqual(enregistre.zone_nom, "")
        self.assertIn("vous entrez dans une zone à risque.", NotificationLog.objects.get().message)

    def test_plusieurs_rapports_dans_un_contact(self):
        a, b = self._rapport(), self._rapport(type="rappel")

        reponse = self._contact(rapports=[a, b])

        self.assertEqual(reponse.json()["rapports_recus"], [a["id"], b["id"]])
        self.assertEqual(AlertReport.objects.count(), 2)

    def test_type_invalide_refuse(self):
        self.assertEqual(self._contact(rapports=[self._rapport(type="autre")]).status_code, 400)
        self.assertFalse(AlertReport.objects.exists())

    def test_trop_de_rapports_refuse(self):
        rapports = [self._rapport() for _ in range(101)]
        self.assertEqual(self._contact(rapports=rapports).status_code, 400)

    def test_aucune_position_dans_le_rapport(self):
        champs = {f.name for f in AlertReport._meta.get_fields()}
        self.assertFalse({"position", "lat", "lon", "latitude", "longitude"} & champs)

    def test_rapport_ignore_les_champs_inconnus(self):
        # Une position glissée par erreur dans un rapport n'est jamais conservée.
        self._contact(rapports=[self._rapport(lat=10.5, lon=10.5)])
        self.assertEqual(AlertReport.objects.count(), 1)


class ProtectionDegradeeTests(_ContactFixtures):
    SANTE_KO_LOCALISATION = {"localisation_toujours": False, "notifications_autorisees": True}
    SANTE_KO_NOTIFICATIONS = {"localisation_toujours": True, "notifications_autorisees": False}
    SANTE_OK = {"localisation_toujours": True, "notifications_autorisees": True}

    def _avertissements(self):
        return NotificationLog.objects.filter(
            type_notification=NotificationLog.TypeNotification.PROTECTION_DEGRADEE
        )

    def test_enregistre_l_etat_de_sante(self):
        self._contact(sante=self.SANTE_KO_NOTIFICATIONS)

        self.utilisateur.refresh_from_db()
        self.assertTrue(self.utilisateur.localisation_toujours)
        self.assertFalse(self.utilisateur.notifications_autorisees)
        self.assertIsNotNone(self.utilisateur.sante_declaree_le)

    def test_sans_etat_de_sante_rien_n_est_modifie(self):
        self._contact()

        self.utilisateur.refresh_from_db()
        self.assertIsNone(self.utilisateur.localisation_toujours)
        self.assertIsNone(self.utilisateur.sante_declaree_le)
        self.assertFalse(NotificationLog.objects.exists())

    def test_etat_correct_ne_declenche_rien(self):
        self._contact(sante=self.SANTE_OK)
        self.assertFalse(NotificationLog.objects.exists())

    def test_localisation_retiree_previent_par_sms_et_email(self):
        self._contact(sante=self.SANTE_KO_LOCALISATION)

        logs = self._avertissements()
        self.assertEqual(
            {log.canal for log in logs}, {NotificationLog.Canal.SMS, NotificationLog.Canal.EMAIL}
        )
        message = logs.first().message
        self.assertIn("ne peut plus vous alerter", message)
        self.assertIn("localisation en arrière-plan désactivée", message)
        self.assertNotIn("notifications désactivées", message)

    def test_notifications_refusees_previent_aussi(self):
        self._contact(sante=self.SANTE_KO_NOTIFICATIONS)

        self.assertIn("notifications désactivées", self._avertissements().first().message)

    def test_les_deux_causes_sont_citees(self):
        self._contact(sante={"localisation_toujours": False, "notifications_autorisees": False})

        message = self._avertissements().first().message
        self.assertIn("localisation en arrière-plan désactivée et notifications désactivées", message)

    def test_le_message_tient_dans_l_alphabet_sms_standard(self):
        self._contact(sante={"localisation_toujours": False, "notifications_autorisees": False})

        encodage, _longueur, _segments = estimer_segments_sms(self._avertissements().first().message)

        self.assertEqual(encodage, "GSM-7")

    def test_au_plus_un_avertissement_par_jour(self):
        self._contact(sante=self.SANTE_KO_LOCALISATION)
        premier_total = self._avertissements().count()

        self._contact(sante=self.SANTE_KO_LOCALISATION)

        self.assertEqual(self._avertissements().count(), premier_total)

    def test_nouvel_avertissement_apres_un_jour(self):
        self._contact(sante=self.SANTE_KO_LOCALISATION)
        premier_total = self._avertissements().count()
        self._avertissements().update(sent_at=timezone.now() - timedelta(hours=25))

        self._contact(sante=self.SANTE_KO_LOCALISATION)

        self.assertEqual(self._avertissements().count(), premier_total * 2)

    def test_pas_d_avertissement_avant_le_debut_du_contrat(self):
        self.utilisateur.contract_start_date = timezone.localdate() + timedelta(days=30)
        self.utilisateur.save()

        self._contact(sante=self.SANTE_KO_LOCALISATION)

        self.assertFalse(NotificationLog.objects.exists())

    def test_pas_d_avertissement_sans_date_de_debut(self):
        self.utilisateur.contract_start_date = None
        self.utilisateur.save()

        self._contact(sante=self.SANTE_KO_LOCALISATION)

        self.assertFalse(NotificationLog.objects.exists())

    def test_pas_d_avertissement_apres_expiration(self):
        self.utilisateur.contract_start_date = timezone.localdate() - timedelta(days=200)
        self.utilisateur.contract_duration = 1
        self.utilisateur.save()

        self._contact(sante=self.SANTE_KO_LOCALISATION)

        self.assertFalse(NotificationLog.objects.exists())

    def test_email_desactive_seul_le_sms_part(self):
        self.utilisateur.email_active = False
        self.utilisateur.save()

        self._contact(sante=self.SANTE_KO_LOCALISATION)

        self.assertEqual(
            {log.canal for log in self._avertissements()}, {NotificationLog.Canal.SMS}
        )
