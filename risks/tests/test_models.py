"""Tests unitaires des règles métier portées par les modèles (risks.models).

Aucune base de données n'est requise : les tests construisent des instances
en mémoire et n'appellent jamais .save().
"""

import datetime

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from risks.models import ConduiteATenir

# Mois utilisés dans les tests, alignés sur MOIS_CHOICES (1..12).
JANVIER, FEVRIER, MARS, AVRIL = 1, 2, 3, 4
OCTOBRE, DECEMBRE = 10, 12


class IsInSeasonTests(SimpleTestCase):
    """Saisonnalité intra-annuelle des ConduiteATenir."""

    def _conduite(self, debut, fin):
        return ConduiteATenir(
            code="TEST",
            saison_mois_debut=debut,
            saison_mois_fin=fin,
        )

    def test_risque_non_saisonnier_toujours_actif(self):
        c = self._conduite(None, None)
        self.assertTrue(c.is_in_season(datetime.datetime(2026, JANVIER, 1)))
        self.assertTrue(c.is_in_season(datetime.datetime(2026, DECEMBRE, 31)))

    def test_periode_interne_a_une_annee(self):
        c = self._conduite(JANVIER, MARS)
        self.assertTrue(c.is_in_season(datetime.datetime(2026, JANVIER, 15)))
        self.assertTrue(c.is_in_season(datetime.datetime(2026, MARS, 31)))
        self.assertFalse(c.is_in_season(datetime.datetime(2026, AVRIL, 1)))
        self.assertFalse(c.is_in_season(datetime.datetime(2026, DECEMBRE, 25)))

    def test_periode_chevauchant_le_nouvel_an(self):
        # "d'octobre à février" : 10 -> 2, fin < début.
        c = self._conduite(OCTOBRE, FEVRIER)
        self.assertTrue(c.is_in_season(datetime.datetime(2026, OCTOBRE, 1)))
        self.assertTrue(c.is_in_season(datetime.datetime(2026, DECEMBRE, 20)))
        self.assertTrue(c.is_in_season(datetime.datetime(2026, FEVRIER, 28)))
        self.assertTrue(c.is_in_season(datetime.datetime(2026, JANVIER, 10)))
        self.assertFalse(c.is_in_season(datetime.datetime(2026, MARS, 1)))
        # Et l'année après ne compte pas : mêmes mois, à cheval sur 2027/2026.
        self.assertTrue(c.is_in_season(datetime.datetime(2027, JANVIER, 1)))

    def test_compte_la_date_et_pas_le_jour(self):
        # Le test se fait sur le mois uniquement, pas sur le jour.
        c = self._conduite(JANVIER, JANVIER)
        self.assertTrue(c.is_in_season(datetime.datetime(2026, JANVIER, 1)))
        self.assertTrue(c.is_in_season(datetime.datetime(2026, JANVIER, 31)))

    def test_periode_dun_seul_mois(self):
        c = self._conduite(JANVIER, JANVIER)
        self.assertTrue(c.is_in_season(datetime.datetime(2026, JANVIER, 10)))
        self.assertFalse(c.is_in_season(datetime.datetime(2026, FEVRIER, 10)))


class ConduiteATenirCleanTests(SimpleTestCase):
    def test_aucune_saison_valide(self):
        ConduiteATenir(code="C", saison_mois_debut=None, saison_mois_fin=None).clean()

    def test_saison_complete_valide(self):
        ConduiteATenir(code="C", saison_mois_debut=OCTOBRE, saison_mois_fin=FEVRIER).clean()

    def test_debut_seul_invalide(self):
        c = ConduiteATenir(code="C", saison_mois_debut=OCTOBRE, saison_mois_fin=None)
        with self.assertRaises(ValidationError):
            c.clean()

    def test_fin_seule_invalide(self):
        c = ConduiteATenir(code="C", saison_mois_debut=None, saison_mois_fin=FEVRIER)
        with self.assertRaises(ValidationError):
            c.clean()

    def test_contrainte_en_base_declaree(self):
        # La même règle doit aussi être appliquée par un CheckConstraint :
        # l'application seule ne suffit pas s'il existe des écritures en masse.
        names = {c.name for c in ConduiteATenir._meta.constraints}
        self.assertIn("conduiteatenir_saison_mois_ensemble", names)