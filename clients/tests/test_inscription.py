import datetime
import re
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from clients.inscription import MAX_TENTATIVES
from clients.models import CodeVerification, Utilisateur


def _donnees(**surcharges):
    donnees = {
        "email": "Voyageur@Example.com",
        "phone": "+33 6 12 34 56 78",
        "email_active": True,
        "push_active": False,
        "reminder_delay": "weekly",
        "contract_duration": 3,
        "consent": True,
    }
    donnees.update(surcharges)
    return donnees


class InscriptionBase(APITestCase):
    def setUp(self):
        # Les limites de fréquence (par IP) s'accumulent dans le cache du processus.
        cache.clear()
        self.addCleanup(cache.clear)
        self.aujourdhui = timezone.localdate()

    def inscrire(self, **surcharges):
        return self.client.post("/api/inscription/", _donnees(**surcharges), format="json")

    def dernier_code(self):
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


class CreationDeCompteTests(InscriptionBase):
    def test_cree_le_compte_et_remet_le_jeton(self):
        reponse = self.inscrire(contract_start_date=(self.aujourdhui + datetime.timedelta(days=20)).isoformat())

        self.assertEqual(reponse.status_code, 201)
        utilisateur = Utilisateur.objects.get()
        self.assertEqual(reponse.data["api_token"], utilisateur.api_token)
        self.assertEqual(utilisateur.email, "voyageur@example.com")  # normalisé en minuscules
        self.assertEqual(utilisateur.phone, "+33612345678")  # espaces retirés
        self.assertFalse(utilisateur.push_active)
        self.assertEqual(utilisateur.reminder_delay, "weekly")
        self.assertEqual(utilisateur.contract_duration, 3)
        self.assertEqual(utilisateur.contract_start_date, self.aujourdhui + datetime.timedelta(days=20))
        self.assertEqual(utilisateur.subscription_status, "trial")
        self.assertEqual(len(mail.outbox), 0)  # aucun code : compte neuf

    def test_consentement_horodate_cote_serveur(self):
        avant = timezone.now()
        self.inscrire()
        utilisateur = Utilisateur.objects.get()
        self.assertTrue(utilisateur.consent_status)
        self.assertGreaterEqual(utilisateur.consent_date, avant)

    def test_le_jeton_remis_authentifie_l_api(self):
        jeton = self.inscrire().data["api_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {jeton}")
        self.assertEqual(self.client.get("/api/me/").status_code, 200)

    def test_consentement_obligatoire(self):
        reponse = self.inscrire(consent=False)
        self.assertEqual(reponse.status_code, 400)
        self.assertIn("consent", reponse.data)
        self.assertEqual(Utilisateur.objects.count(), 0)

    def test_consentement_absent_refuse(self):
        donnees = _donnees()
        del donnees["consent"]
        reponse = self.client.post("/api/inscription/", donnees, format="json")
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(Utilisateur.objects.count(), 0)

    def test_telephone_hors_format_international_refuse(self):
        reponse = self.inscrire(phone="06 12 34 56 78")
        self.assertEqual(reponse.status_code, 400)
        self.assertIn("phone", reponse.data)

    def test_date_de_depart_dans_le_passe_refusee(self):
        hier = (self.aujourdhui - datetime.timedelta(days=1)).isoformat()
        reponse = self.inscrire(contract_start_date=hier)
        self.assertEqual(reponse.status_code, 400)
        self.assertIn("contract_start_date", reponse.data)
        self.assertEqual(Utilisateur.objects.count(), 0)

    def test_un_jeton_perime_dans_l_en_tete_ne_bloque_pas_l_inscription(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer jeton-inconnu")
        self.assertEqual(self.inscrire().status_code, 201)


class CompteExistantTests(InscriptionBase):
    def setUp(self):
        super().setUp()
        self.existant = Utilisateur.objects.create(email="voyageur@example.com", phone="+33612345678")

    def test_email_existant_envoie_un_code_sans_remettre_le_jeton(self):
        reponse = self.inscrire()

        self.assertEqual(reponse.status_code, 202)
        self.assertTrue(reponse.data["verification_requise"])
        self.assertNotIn("api_token", reponse.data)
        self.assertEqual(reponse.data["email_masque"], "v***@example.com")
        self.assertEqual(Utilisateur.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["voyageur@example.com"])

    def test_telephone_existant_avec_autre_email_envoie_le_code_a_l_email_du_compte(self):
        reponse = self.inscrire(email="autre@example.com")

        self.assertEqual(reponse.status_code, 202)
        self.assertEqual(mail.outbox[0].to, ["voyageur@example.com"])
        self.assertEqual(Utilisateur.objects.count(), 1)

    def test_le_code_n_est_pas_stocke_en_clair(self):
        self.inscrire()
        empreinte = CodeVerification.objects.get().code_hash
        self.assertEqual(len(empreinte), 64)
        self.assertNotEqual(empreinte, self.dernier_code())

    def test_bon_code_remet_un_nouveau_jeton_et_revoque_l_ancien(self):
        ancien_jeton = self.existant.api_token
        reference = self.inscrire().data["reference"]

        reponse = self.client.post(
            "/api/inscription/verifier/", {"reference": reference, "code": self.dernier_code()}, format="json"
        )

        self.assertEqual(reponse.status_code, 200)
        nouveau_jeton = reponse.data["api_token"]
        self.assertNotEqual(nouveau_jeton, ancien_jeton)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {ancien_jeton}")
        self.assertEqual(self.client.get("/api/me/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {nouveau_jeton}")
        self.assertEqual(self.client.get("/api/me/").status_code, 200)

    def test_les_preferences_saisies_ne_modifient_pas_le_compte_existant(self):
        reference = self.inscrire(push_active=False, reminder_delay="weekly").data["reference"]
        self.client.post(
            "/api/inscription/verifier/", {"reference": reference, "code": self.dernier_code()}, format="json"
        )
        self.existant.refresh_from_db()
        self.assertTrue(self.existant.push_active)
        self.assertEqual(self.existant.reminder_delay, "daily")

    def test_un_code_ne_sert_qu_une_fois(self):
        reference = self.inscrire().data["reference"]
        corps = {"reference": reference, "code": self.dernier_code()}

        self.assertEqual(self.client.post("/api/inscription/verifier/", corps, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/inscription/verifier/", corps, format="json").status_code, 400)

    def test_mauvais_code_refuse(self):
        reference = self.inscrire().data["reference"]
        faux = "000000" if self.dernier_code() != "000000" else "111111"

        reponse = self.client.post("/api/inscription/verifier/", {"reference": reference, "code": faux}, format="json")

        self.assertEqual(reponse.status_code, 400)
        self.assertIn("code", reponse.data)

    def test_trop_d_essais_ferment_le_code_meme_avec_le_bon(self):
        reference = self.inscrire().data["reference"]
        bon = self.dernier_code()
        faux = "000000" if bon != "000000" else "111111"
        for _ in range(MAX_TENTATIVES):
            self.client.post("/api/inscription/verifier/", {"reference": reference, "code": faux}, format="json")

        reponse = self.client.post("/api/inscription/verifier/", {"reference": reference, "code": bon}, format="json")

        self.assertEqual(reponse.status_code, 400)

    def test_code_perime_refuse(self):
        reference = self.inscrire().data["reference"]
        CodeVerification.objects.update(expire_le=timezone.now() - datetime.timedelta(minutes=1))

        reponse = self.client.post(
            "/api/inscription/verifier/", {"reference": reference, "code": self.dernier_code()}, format="json"
        )

        self.assertEqual(reponse.status_code, 400)

    def test_reference_inconnue_refusee(self):
        reponse = self.client.post(
            "/api/inscription/verifier/",
            {"reference": "00000000-0000-0000-0000-000000000000", "code": "123456"},
            format="json",
        )
        self.assertEqual(reponse.status_code, 400)

    def test_code_mal_forme_refuse(self):
        reference = self.inscrire().data["reference"]
        reponse = self.client.post(
            "/api/inscription/verifier/", {"reference": reference, "code": "12ab56"}, format="json"
        )
        self.assertEqual(reponse.status_code, 400)

    def test_pas_de_nouvel_email_dans_la_minute(self):
        premiere = self.inscrire().data["reference"]
        seconde = self.inscrire().data["reference"]

        self.assertEqual(premiere, seconde)
        self.assertEqual(len(mail.outbox), 1)

    def test_un_nouveau_code_invalide_le_precedent(self):
        premiere = self.inscrire().data["reference"]
        premier_code = self.dernier_code()
        CodeVerification.objects.update(cree_le=timezone.now() - datetime.timedelta(minutes=2))

        seconde = self.inscrire().data["reference"]

        self.assertNotEqual(premiere, seconde)
        self.assertEqual(len(mail.outbox), 2)
        reponse = self.client.post(
            "/api/inscription/verifier/", {"reference": premiere, "code": premier_code}, format="json"
        )
        self.assertEqual(reponse.status_code, 400)

    def test_envoi_impossible_donne_503_et_un_nouvel_essai_renvoie_un_vrai_code(self):
        with mock.patch("clients.inscription.send_mail", side_effect=OSError("SMTP injoignable")):
            reponse = self.inscrire()
        self.assertEqual(reponse.status_code, 503)

        reponse = self.inscrire()
        self.assertEqual(reponse.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)
