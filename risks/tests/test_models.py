"""Tests unitaires des règles métier portées par les modèles (risks.models).

Aucune base de données n'est requise : les tests construisent des instances
en mémoire et n'appellent jamais .save().
"""

import datetime

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from risks.models import Endemie, Modulation

# Mois utilisés dans les tests, alignés sur MOIS_CHOICES (1..12).
JANVIER, FEVRIER, MARS, AVRIL = 1, 2, 3, 4
OCTOBRE, DECEMBRE = 10, 12


class IsInSeasonTests(SimpleTestCase):
    """Période de l'année (saisonnalité intra-annuelle) des Modulation."""

    def _modulation(self, debut, fin):
        return Modulation(
            code="TEST",
            saison_mois_debut=debut,
            saison_mois_fin=fin,
        )

    def test_risque_non_saisonnier_toujours_actif(self):
        m = self._modulation(None, None)
        self.assertTrue(m.is_in_season(datetime.datetime(2026, JANVIER, 1)))
        self.assertTrue(m.is_in_season(datetime.datetime(2026, DECEMBRE, 31)))

    def test_periode_interne_a_une_annee(self):
        m = self._modulation(JANVIER, MARS)
        self.assertTrue(m.is_in_season(datetime.datetime(2026, JANVIER, 15)))
        self.assertTrue(m.is_in_season(datetime.datetime(2026, MARS, 31)))
        self.assertFalse(m.is_in_season(datetime.datetime(2026, AVRIL, 1)))
        self.assertFalse(m.is_in_season(datetime.datetime(2026, DECEMBRE, 25)))

    def test_periode_chevauchant_le_nouvel_an(self):
        # "d'octobre à février" : 10 -> 2, fin < début.
        m = self._modulation(OCTOBRE, FEVRIER)
        self.assertTrue(m.is_in_season(datetime.datetime(2026, OCTOBRE, 1)))
        self.assertTrue(m.is_in_season(datetime.datetime(2026, DECEMBRE, 20)))
        self.assertTrue(m.is_in_season(datetime.datetime(2026, FEVRIER, 28)))
        self.assertTrue(m.is_in_season(datetime.datetime(2026, JANVIER, 10)))
        self.assertFalse(m.is_in_season(datetime.datetime(2026, MARS, 1)))
        # Et l'année après ne compte pas : mêmes mois, à cheval sur 2027/2026.
        self.assertTrue(m.is_in_season(datetime.datetime(2027, JANVIER, 1)))

    def test_compte_la_date_et_pas_le_jour(self):
        # Le test se fait sur le mois uniquement, pas sur le jour.
        m = self._modulation(JANVIER, JANVIER)
        self.assertTrue(m.is_in_season(datetime.datetime(2026, JANVIER, 1)))
        self.assertTrue(m.is_in_season(datetime.datetime(2026, JANVIER, 31)))

    def test_periode_dun_seul_mois(self):
        m = self._modulation(JANVIER, JANVIER)
        self.assertTrue(m.is_in_season(datetime.datetime(2026, JANVIER, 10)))
        self.assertFalse(m.is_in_season(datetime.datetime(2026, FEVRIER, 10)))


class ModulationCleanTests(SimpleTestCase):
    def test_aucune_saison_valide(self):
        Modulation(code="C", saison_mois_debut=None, saison_mois_fin=None).clean()

    def test_saison_complete_valide(self):
        Modulation(code="C", saison_mois_debut=OCTOBRE, saison_mois_fin=FEVRIER).clean()

    def test_debut_seul_invalide(self):
        m = Modulation(code="C", saison_mois_debut=OCTOBRE, saison_mois_fin=None)
        with self.assertRaises(ValidationError):
            m.clean()

    def test_fin_seule_invalide(self):
        m = Modulation(code="C", saison_mois_debut=None, saison_mois_fin=FEVRIER)
        with self.assertRaises(ValidationError):
            m.clean()

    def test_contrainte_en_base_declaree(self):
        # La même règle doit aussi être appliquée par un CheckConstraint :
        # l'application seule ne suffit pas s'il existe des écritures en masse.
        names = {c.name for c in Modulation._meta.constraints}
        self.assertIn("modulation_saison_mois_ensemble", names)


class EndemieModulationFacultativeTests(SimpleTestCase):
    def test_modulation_facultative(self):
        # Une endémie peut n'avoir aucune modulation (risque actif toute l'année,
        # sans précision) ; le risque, lui, est obligatoire.
        self.assertTrue(Endemie._meta.get_field("modulation").null)
        self.assertFalse(Endemie._meta.get_field("risque").null)
