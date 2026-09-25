import datetime

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from clients.models import (
    CONTRACT_START_DATE_MAX_MONTHS_AHEAD,
    NotificationLog,
    PreferenceChangeLog,
    Utilisateur,
    UserRiskZoneStatus,
    valider_date_debut_contrat,
)
from risks.models import ConduiteATenir, Endemie, Risque, Zone


class UtilisateurTests(TestCase):
    def test_api_token_generated_automatically(self):
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.assertTrue(u.api_token)

    def test_api_token_unique_per_user(self):
        u1 = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        u2 = Utilisateur.objects.create(email="b@example.com", phone="+33600000001")
        self.assertNotEqual(u1.api_token, u2.api_token)

    def test_is_authenticated_always_true(self):
        u = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.assertTrue(u.is_authenticated)


class ContractStartDateTests(TestCase):
    """Cf. saintex-spec-technique.md §6 : date de début de contrat fixée par
    l'utilisateur, modifiable jusqu'à la veille de son arrivée, bornée à
    CONTRACT_START_DATE_MAX_MONTHS_AHEAD (décision réunion médicale)."""

    def setUp(self):
        self.aujourdhui = timezone.localdate()

    def test_date_future_dans_la_borne_est_acceptee(self):
        # Ne lève pas d'exception.
        valider_date_debut_contrat(None, self.aujourdhui + datetime.timedelta(days=30))

    def test_date_dans_le_passe_est_rejetee(self):
        with self.assertRaises(ValidationError):
            valider_date_debut_contrat(None, self.aujourdhui - datetime.timedelta(days=1))

    def test_date_au_dela_de_la_borne_max_est_rejetee(self):
        trop_loin = self.aujourdhui.replace(
            year=self.aujourdhui.year + (CONTRACT_START_DATE_MAX_MONTHS_AHEAD // 12) + 1
        )
        with self.assertRaises(ValidationError):
            valider_date_debut_contrat(None, trop_loin)

    def test_modification_avant_demarrage_est_acceptee(self):
        ancienne = self.aujourdhui + datetime.timedelta(days=10)
        nouvelle = self.aujourdhui + datetime.timedelta(days=20)
        # Ne lève pas d'exception : le contrat n'a pas encore démarré.
        valider_date_debut_contrat(ancienne, nouvelle)

    def test_modification_apres_demarrage_est_rejetee(self):
        deja_demarree = self.aujourdhui - datetime.timedelta(days=1)
        with self.assertRaises(ValidationError):
            valider_date_debut_contrat(deja_demarree, self.aujourdhui + datetime.timedelta(days=5))

    def test_reaffecter_la_meme_date_le_jour_meme_ne_leve_rien(self):
        # Cf. valider_date_debut_contrat : le garde-fou "déjà démarré" ne se
        # déclenche que si la valeur change réellement.
        valider_date_debut_contrat(self.aujourdhui, self.aujourdhui)

    def test_utilisateur_clean_valide_le_changement_de_date(self):
        u = Utilisateur.objects.create(
            email="a@example.com",
            phone="+33600000000",
            contract_start_date=self.aujourdhui - datetime.timedelta(days=1),
        )
        u.contract_start_date = self.aujourdhui + datetime.timedelta(days=5)
        with self.assertRaises(ValidationError):
            u.clean()

    def test_contrat_demarre_property(self):
        u = Utilisateur.objects.create(
            email="a@example.com", phone="+33600000000",
            contract_start_date=self.aujourdhui - datetime.timedelta(days=1),
        )
        self.assertTrue(u.contrat_demarre)

    def test_contrat_pas_encore_demarre_property(self):
        u = Utilisateur.objects.create(
            email="a@example.com", phone="+33600000000",
            contract_start_date=self.aujourdhui + datetime.timedelta(days=1),
        )
        self.assertFalse(u.contrat_demarre)

    def test_contract_expiry_date_calculee(self):
        u = Utilisateur.objects.create(
            email="a@example.com", phone="+33600000000",
            contract_start_date=datetime.date(2026, 1, 15), contract_duration=2,
        )
        self.assertEqual(u.contract_expiry_date, datetime.date(2026, 3, 15))

    def test_contract_expiry_date_none_si_duree_manquante(self):
        u = Utilisateur.objects.create(
            email="a@example.com", phone="+33600000000",
            contract_start_date=self.aujourdhui,
        )
        self.assertIsNone(u.contract_expiry_date)


class PreferenceChangeLogTests(TestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")

    def test_enregistrer_creates_entry_on_change(self):
        entry = PreferenceChangeLog.enregistrer(self.utilisateur, "push_active", "True", "False")
        self.assertIsNotNone(entry)
        self.assertEqual(PreferenceChangeLog.objects.count(), 1)

    def test_enregistrer_is_noop_when_value_unchanged(self):
        entry = PreferenceChangeLog.enregistrer(self.utilisateur, "push_active", "True", "True")
        self.assertIsNone(entry)
        self.assertEqual(PreferenceChangeLog.objects.count(), 0)

    def test_enregistrer_rejects_untracked_field(self):
        with self.assertRaises(ValueError):
            PreferenceChangeLog.enregistrer(self.utilisateur, "email", "a@example.com", "b@example.com")


class _EndemieFixtureMixin:
    """Fabrique une Endemie minimale (Zone + Risque + ConduiteATenir) pour
    les tests de UserRiskZoneStatus/NotificationLog, qui n'ont besoin que
    d'une référence valide, pas d'un scénario médical réaliste.
    """

    def _endemie(self):
        zone = Zone.objects.create(source_id=1, nom="Zone test")
        risque = Risque.objects.create(
            code="PAL",
            libelle_fr="Paludisme",
            libelle_en="Malaria",
            nature_du_risque_fr="...",
            nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="..."
        )
        return Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)


class UserRiskZoneStatusTests(_EndemieFixtureMixin, TestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")
        self.endemie = self._endemie()

    def test_entered_at_set_automatically(self):
        statut = UserRiskZoneStatus.objects.create(utilisateur=self.utilisateur, endemie=self.endemie)
        self.assertIsNotNone(statut.entered_at)
        self.assertIsNone(statut.last_reminded_at)

    def test_un_seul_statut_par_utilisateur_et_endemie(self):
        UserRiskZoneStatus.objects.create(utilisateur=self.utilisateur, endemie=self.endemie)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserRiskZoneStatus.objects.create(utilisateur=self.utilisateur, endemie=self.endemie)


class NotificationLogTests(_EndemieFixtureMixin, TestCase):
    def setUp(self):
        self.utilisateur = Utilisateur.objects.create(email="a@example.com", phone="+33600000000")

    def test_creation_alerte_zone_avec_position(self):
        log = NotificationLog.objects.create(
            utilisateur=self.utilisateur,
            type_notification=NotificationLog.TypeNotification.ALERTE_ZONE,
            endemie=self._endemie(),
            position=Point(2.35, 48.85, srid=4326),
            message="Vous entrez dans une zone à risque de paludisme.",
            destinataire="a@example.com",
            canal=NotificationLog.Canal.EMAIL,
        )
        self.assertEqual(log.statut, NotificationLog.Statut.EN_ATTENTE)

    def test_creation_relance_silence_sans_position_ni_endemie(self):
        # Cf. docstring du modèle : une relance "appli silencieuse" ne porte
        # par définition aucune position ni endemie associée.
        log = NotificationLog.objects.create(
            utilisateur=self.utilisateur,
            type_notification=NotificationLog.TypeNotification.RELANCE_SILENCE,
            message="Nous n'avons plus de nouvelles de votre position depuis 7h.",
            destinataire="+33600000000",
            canal=NotificationLog.Canal.SMS,
        )
        self.assertIsNone(log.endemie)
        self.assertIsNone(log.position)
