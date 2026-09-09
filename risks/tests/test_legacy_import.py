"""Tests unitaires du script d'import des données historiques
(risks.management.commands.migrate_legacy_data).
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.contrib.gis.geos import MultiPolygon
from django.test import SimpleTestCase

from risks.management.commands.migrate_legacy_data import (
    Command,
    DEFAULT_EXCLUSION_RADIUS_KM,
    build_zone_geom,
    buffer_point_km,
    parse_coords,
)


class ParseCoordsTests(SimpleTestCase):
    def test_coords_absentes(self):
        points, note = parse_coords(None)
        self.assertIsNone(points)
        self.assertIn("coords absentes", note)

    def test_geometrie_tronquee(self):
        points, note = parse_coords("[1,2,")
        self.assertIsNone(points)
        self.assertIn("tronquée", note)

    def test_trop_peu_de_points(self):
        points, note = parse_coords("[[0,0],[1,0],[0,1]]")
        self.assertIsNone(points)
        self.assertIn("trop courte", note)

    def test_anneau_deja_ferme(self):
        points, note = parse_coords("[[0,0],[1,0],[1,1],[0,0]]")
        self.assertIsNone(note)
        self.assertEqual(len(points), 4)
        self.assertEqual(points[-1], points[0])

    def test_anneau_ferme_automatiquement(self):
        # 4 points non fermés : le dernier (== premier) est ajouté.
        points, note = parse_coords("[[0,0],[1,0],[1,1],[0,1]]")
        self.assertIsNone(note)
        self.assertEqual(len(points), 5)
        self.assertEqual(points[-1], points[0])

    def test_decimale_sans_chiffre_apres_le_point(self):
        # L'export MariaDB contient "11." sans décimale -> "11.0".
        points, note = parse_coords("[[11.,0],[12,0],[12,1],[11,0.]]")
        self.assertIsNone(note)
        self.assertEqual(points[0], [11.0, 0.0])
        self.assertEqual(points[3], [11.0, 0.0])


class BuildZoneGeomTests(SimpleTestCase):
    def test_polygone_simple(self):
        points = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
        geom, note = build_zone_geom(points)
        self.assertEqual(note, "")
        # NB : le SRID n'est pas propagé par les conversions GEOS (fix_polygon
        # puis MultiPolygon(...)) — la colonne PostGIS l'applique à l'écriture.
        self.assertEqual(geom.geom_type, "MultiPolygon")
        self.assertTrue(geom.valid)
        self.assertAlmostEqual(geom.area, 100.0, places=4)

    def test_zone_a_cheval_sur_lantimeridien(self):
        # 170°E -> 190°(=-170°): doit être découpée proprement des deux
        # côtés de ±180° sans traverser le méridien de Greenwich.
        points = [[170, 0], [190, 0], [190, 10], [170, 10], [170, 0]]
        geom, note = build_zone_geom(points)
        self.assertEqual(note, "")
        self.assertEqual(geom.geom_type, "MultiPolygon")
        self.assertTrue(geom.valid)
        # Surface conservée au découpage (bande de 20° x 10°) — petite
        # tolérance : le découpage antiméridien peut légèrement arrondir.
        self.assertAlmostEqual(geom.area, 200.0, delta=5.0)

    def test_auto_intersection_reparnee_signalee(self):
        # "Bowtie" : segments qui se croisent (données sources corrompues).
        points = [[0, 0], [3, 3], [0, 3], [3, 0], [0, 0]]
        geom, note = build_zone_geom(points)
        self.assertTrue(geom.valid, "la géométrie doit sortir valide (buffer(0))")
        self.assertTrue(note, "une réparation doit être signalée dans note")


class BufferPointKmTests(SimpleTestCase):
    def test_retourne_un_polygone_de_taille_attendue(self):
        geom = buffer_point_km(10.0, 20.0, DEFAULT_EXCLUSION_RADIUS_KM)
        self.assertEqual(geom.geom_type, "Polygon")
        self.assertTrue(geom.valid)
        # Aire d'un cercle de rayon r_deg = 20/111 ° : pi * r^2 ~ 0.102 deg².
        self.assertGreater(geom.area, 0.09)
        self.assertLess(geom.area, 0.12)

    def test_centrage_sur_le_point(self):
        geom = buffer_point_km(10.0, 20.0, 20)
        self.assertAlmostEqual(geom.centroid.x, 10.0, places=2)
        self.assertAlmostEqual(geom.centroid.y, 20.0, places=2)


class ApplyZoneExclusionsTests(SimpleTestCase):
    def _write_zonesaine(self, items):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump({"zonesaine": items}, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def _ok_item(self, **overrides):
        item = {
            "endemie_cat_code": "P_T3_A",
            "endemie_zone_id": 42,
            "lat": 12.5,
            "long": -17.5,
        }
        item.update(overrides)
        return item

    def test_application_sur_la_bonne_endemie(self):
        path = self._write_zonesaine([self._ok_item()])
        with mock.patch(
            "risks.management.commands.migrate_legacy_data.Endemie.objects"
        ) as objects:
            objects.filter.return_value.exists.return_value = True
            objects.filter.return_value.update.return_value = 1
            applied, skipped = Command().apply_zone_exclusions(path)

        self.assertEqual((applied, skipped), (1, 0))
        # Le filtre cible bien le couple (zone, conduite), pas la zone entière.
        objects.filter.assert_called_once_with(
            zone__source_id=42, conduite_a_tenir__code="P_T3_A"
        )
        _, kwargs = objects.filter.return_value.update.call_args
        exclusion = kwargs["zone_exclue"]
        self.assertEqual(exclusion.geom_type, "MultiPolygon")
        self.assertTrue(exclusion.valid)
        # NB : le SRID n'est pas propagé par Point.buffer() ni MultiPolygon(...) —
        # la colonne PostGIS l'applique à l'écriture.

    def test_lignes_incompletes_ignorees(self):
        items = [
            self._ok_item(endemie_cat_code=None),
            self._ok_item(endemie_zone_id=None),
            self._ok_item(lat=None),
            self._ok_item(long=None),
        ]
        path = self._write_zonesaine(items)
        with mock.patch(
            "risks.management.commands.migrate_legacy_data.Endemie.objects"
        ) as objects:
            applied, skipped = Command().apply_zone_exclusions(path)

        self.assertEqual((applied, skipped), (0, 4))
        objects.filter.assert_not_called()

    def test_endemie_introuvable_ignoree(self):
        path = self._write_zonesaine([self._ok_item()])
        with mock.patch(
            "risks.management.commands.migrate_legacy_data.Endemie.objects"
        ) as objects:
            objects.filter.return_value.exists.return_value = False
            applied, skipped = Command().apply_zone_exclusions(path)

        self.assertEqual((applied, skipped), (0, 1))
        objects.filter.return_value.update.assert_not_called()

    @unittest.expectedFailure
    def test_deux_points_de_la_meme_endemie_devraient_etre_fusionnes(self):
        """Bug connu : deux points `zonesaine` du même couple (zone, conduite)
        font chacun `Endemie.objects.filter(...).update(zone_exclue=...)` —
        la seconde exclusion écrase la première au lieu de fusionner les
        polygones (union). Aucun cas de ce type n'existe dans les données
        actuelles, mais le jour où cela arrivera, on perdra une exclusion.

        Ce test documente le comportement attendu (une exclusion fusionnée
        par couple) et échoue tant que le bug n'est pas corrigé.
        """
        path = self._write_zonesaine([
            self._ok_item(lat=12.5, long=-17.5),
            self._ok_item(lat=12.6, long=-17.6),  # même couple, point distinct
        ])
        exclusions_appliquees = []

        def fake_update(**kwargs):
            exclusions_appliquees.append(kwargs["zone_exclue"])
            return 1

        with mock.patch(
            "risks.management.commands.migrate_legacy_data.Endemie.objects"
        ) as objects:
            objects.filter.return_value.exists.return_value = True
            objects.filter.return_value.update.side_effect = fake_update
            Command().apply_zone_exclusions(path)

        # Attendu : une seule exclusion fusionnée (union des deux buffers).
        self.assertEqual(len(exclusions_appliquees), 1)