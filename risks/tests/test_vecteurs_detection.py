"""Tests du jeu de cas partagé de la détection locale (risks.vecteurs_detection).

Le jeu partagé n'est utile aux modules natifs que s'il (1) est à jour par
rapport à la référence Python, (2) exprime bien ce que ses cas prétendent
tester, et (3) a le même format que le cache réellement produit par le
serveur.
"""

import json
from datetime import datetime

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import SimpleTestCase, TestCase

from risks.cache import construire_cache, endemies_actives_dans_cache
from risks.models import ConduiteATenir, Endemie, Risque, Zone
from risks.vecteurs_detection import CACHE_TEST, CAS, chemin_fichier, generer, serialiser


class FichierPartageTests(SimpleTestCase):
    def test_le_fichier_partage_est_a_jour(self):
        chemin = chemin_fichier()
        self.assertTrue(
            chemin.exists(),
            f"{chemin} est absent : lancer `python manage.py generer_vecteurs_detection`.",
        )
        self.assertEqual(
            chemin.read_text(encoding="utf-8"),
            serialiser(generer()),
            f"{chemin} n'est plus à jour par rapport à la détection de référence : "
            "lancer `python manage.py generer_vecteurs_detection` (et mettre à jour les "
            "tests Swift/Kotlin si le comportement a volontairement changé).",
        )

    def test_le_fichier_est_du_json_valide_avec_les_sections_attendues(self):
        contenu = json.loads(chemin_fichier().read_text(encoding="utf-8"))
        self.assertEqual(set(contenu), {"format", "description", "regles", "cache", "cas"})
        self.assertEqual(contenu["format"], 1)


class CoherenceInterneTests(SimpleTestCase):
    def test_references_du_cache_de_test_valides(self):
        for endemie in CACHE_TEST["endemies"]:
            self.assertIn(endemie["conduite"], CACHE_TEST["conduites"])
            self.assertIn(endemie["geometrie"], CACHE_TEST["geometries"])

    def test_identifiants_d_endemies_uniques_et_ordonnes(self):
        ids = [e["id"] for e in CACHE_TEST["endemies"]]
        self.assertEqual(ids, sorted(set(ids)))

    def test_les_attendus_sont_dans_l_ordre_croissant(self):
        for cas in generer()["cas"]:
            self.assertEqual(cas["attendu"], sorted(cas["attendu"]), cas["nom"])

    def test_le_jeu_couvre_des_cas_positifs_et_negatifs(self):
        cas = generer()["cas"]
        self.assertGreaterEqual(sum(1 for c in cas if c["attendu"]), 12)
        self.assertGreaterEqual(sum(1 for c in cas if not c["attendu"]), 8)
        self.assertEqual(len({c["nom"] for c in cas}), len(cas), "noms de cas en double")


class AttendusIndependantsDeLaReferenceTests(SimpleTestCase):
    """Les résultats du fichier sont CALCULÉS par la référence : si elle avait
    un défaut, le jeu partagé le reproduirait fidèlement. On fige donc ici, à la
    main, ce que les cas clés doivent donner d'après leur énoncé."""

    ATTENDUS = {
        "z1 : centre, en janvier (une seule endémie, toute l'année)": [1],
        "z1 : centre, en juillet (deux endémies sur la même zone)": [1, 6],
        "hors de toute zone": [],
        "z1 : sur le bord ouest": [1],
        "z1 : sur un coin": [1],
        "z1 : juste à l'extérieur du bord ouest": [],
        "z2 : dans la couronne, en saison": [2],
        "z2 : dans le trou, en saison": [],
        "z2 : dans la couronne, hors saison": [],
        "z3 : antiméridien, partie est": [3],
        "z3 : antiméridien, partie ouest": [3],
        "z3 : juste en dehors de la partie est": [],
        "z4 : branche basse du L, en saison (décembre)": [4],
        "z4 : encoche du L, en saison": [],
        "z4 : branche haute du L, en saison": [4],
        "z4 : branche haute du L, hors saison (juillet)": [],
        "z4 : saison à cheval sur le nouvel an (janvier)": [4],
        "z4 : premier jour de la saison (1er novembre)": [4],
        "z4 : dernier jour de la saison (fin février)": [4],
        "z4 : premier jour hors saison (1er mars)": [],
        "z5 : avant le début de validité": [],
        "z5 : borne de début incluse": [5],
        "z5 : pendant la validité, premier morceau": [5],
        "z5 : pendant la validité, second morceau": [5],
        "z5 : entre les deux morceaux": [],
        "z5 : borne de fin incluse": [5],
        "z5 : après la fin de validité": [],
        "mois évalué en UTC : 31 mai 23h30 à UTC-5 est le 1er juin en UTC (saison d'été active)": [1, 6],
        "mois évalué en UTC : 30 septembre 20h à UTC-5 est le 1er octobre en UTC (saison d'été terminée)": [1],
        "mois évalué en UTC : 31 octobre 20h à UTC-5 est le 1er novembre en UTC (saison d'hiver commencée)": [4],
    }

    def test_les_attendus_du_jeu_sont_ceux_de_l_enonce(self):
        obtenus = {c["nom"]: c["attendu"] for c in generer()["cas"]}
        self.assertEqual(set(obtenus), set(self.ATTENDUS), "cas ajoutés ou retirés : mettre à jour ce test")
        for nom, attendu in self.ATTENDUS.items():
            self.assertEqual(obtenus[nom], attendu, nom)

    def test_cas_marques_bord(self):
        bords = {c["nom"] for c in generer()["cas"] if c.get("bord")}
        self.assertEqual(bords, {"z1 : sur le bord ouest", "z1 : sur un coin"})


class FormatIdentiqueAuCacheReelTests(TestCase):
    """Le cache de test doit avoir exactement la forme du cache que le serveur
    produit, pour que les modules natifs testent le vrai format."""

    def test_memes_cles_que_construire_cache(self):
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
            recommandation_fr="<p>Texte.</p>", saison_mois_debut=6, saison_mois_fin=9,
        )
        zone = Zone.objects.create(
            source_id=1, nom="Zone A",
            geom=MultiPolygon(Polygon(((10, 10), (12, 10), (12, 12), (10, 12), (10, 10)))),
        )
        Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        reel = construire_cache(Point(11, 11, srid=4326))

        self.assertEqual(set(CACHE_TEST), set(reel))
        modele_conduite = CACHE_TEST["conduites"]["SAISON_ETE"]
        reelle_conduite = next(iter(reel["conduites"].values()))
        self.assertEqual(set(modele_conduite), set(reelle_conduite))
        self.assertEqual(set(modele_conduite["risque"]), set(reelle_conduite["risque"]))
        self.assertEqual(set(modele_conduite["saison"]), set(reelle_conduite["saison"]))
        self.assertEqual(set(CACHE_TEST["endemies"][0]), set(reel["endemies"][0]))
        geometrie_modele = next(iter(CACHE_TEST["geometries"].values()))
        geometrie_reelle = next(iter(reel["geometries"].values()))
        self.assertEqual(set(geometrie_modele), set(geometrie_reelle))
        self.assertEqual(geometrie_modele["type"], geometrie_reelle["type"])

    def test_le_cache_reel_se_rejoue_a_l_identique_apres_json(self):
        # Le téléphone reçoit du JSON : la détection doit donner le même résultat
        # sur le cache sérialisé puis relu.
        risque = Risque.objects.create(
            code="PAL", libelle_fr="Paludisme", libelle_en="Malaria",
            nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        conduite = ConduiteATenir.objects.create(
            code="PAL_T1", risque=risque, nature_du_risque_fr="...", nature_du_risque_en="...",
        )
        zone = Zone.objects.create(
            source_id=1, nom="Zone A",
            geom=MultiPolygon(Polygon(((10, 10), (12, 10), (12, 12), (10, 12), (10, 10)))),
        )
        endemie = Endemie.objects.create(zone=zone, conduite_a_tenir=conduite)

        cache = json.loads(json.dumps(construire_cache(tolerance=0)))
        instant = datetime.fromisoformat("2026-07-15T12:00:00+00:00")

        self.assertEqual(endemies_actives_dans_cache(cache, 11, 11, instant), [endemie.pk])
        self.assertEqual(endemies_actives_dans_cache(cache, 5, 5, instant), [])


class VecteursCoherentsAvecLeModuleTests(SimpleTestCase):
    def test_nombre_de_cas(self):
        self.assertEqual(len(generer()["cas"]), len(CAS))
