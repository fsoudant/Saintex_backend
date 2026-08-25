"""
Importe les données historiques (zone, risque, conduiteatenir, endemie)
depuis les 4 exports JSON de la base MariaDB existante.

Usage :
    python manage.py migrate_legacy_data /chemin/vers/dossier/exports/

Le dossier doit contenir :
    _zone__202608221002.json
    risque_202608222244.json
    conduiteatenir_202608222244.json
    endemie_202608222243.json

Idempotent sur Zone/Risque/ConduiteATenir (update_or_create sur la clé
naturelle). Endemie n'a pas de clé naturelle fiable dans l'export : la table
est vidée puis entièrement recréée à chaque exécution.
"""

import json
import re
from pathlib import Path

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from risks.models import ConduiteATenir, Endemie, Pays, Risque, Zone, ZoneSaine

# Corrige le défaut de format observé dans l'export ("11." sans décimale
# après le point, ex. Amerique_2_FJ) avant le parsing JSON strict.
BARE_DECIMAL_RE = re.compile(r"(\d)\.(?=[,\]])")


def parse_coords(raw):
    """Parse le champ texte 'coords' en liste de points [lon, lat].

    Retourne (points, note). points est None si la géométrie n'est pas
    exploitable (absente ou tronquée à l'export) — la ligne est alors
    importée quand même, avec geom=None et la note explicative.
    """
    if raw is None:
        return None, "coords absentes à l'export (ex. zone_XX / codes pays ISO)"

    fixed = BARE_DECIMAL_RE.sub(r"\1.0", raw)
    try:
        points = json.loads(fixed)
    except json.JSONDecodeError:
        return None, "géométrie tronquée à l'export MariaDB (>32767 caractères) — à ré-exporter"

    if not points or len(points) < 4:
        return None, f"géométrie trop courte ({len(points) if points else 0} points) pour former un polygone"

    if points[0] != points[-1]:
        points = points + [points[0]]

    return points, None


class Command(BaseCommand):
    help = "Importe zone/risque/conduiteatenir/endemie depuis les exports JSON MariaDB."

    def add_arguments(self, parser):
        parser.add_argument(
            "export_dir",
            type=str,
            help="Répertoire contenant les 4 fichiers d'export JSON",
        )

    def handle(self, *args, **options):
        export_dir = Path(options["export_dir"])

        zone_file = export_dir / "_zone__202608221002.json"
        risque_file = export_dir / "risque_202608222244.json"
        ca_file = export_dir / "conduiteatenir_202608222244.json"
        endemie_file = export_dir / "endemie_202608222243.json"
        zonesaine_file = export_dir / "zonesaine_202608241320.json"
        pays_file = export_dir / "pays_202608241323.json"

        for f in (zone_file, risque_file, ca_file, endemie_file, zonesaine_file, pays_file):
            if not f.exists():
                raise CommandError(f"Fichier introuvable : {f}")

        with transaction.atomic():
            n_zones, zone_issues = self.import_zones(zone_file)
            n_risques = self.import_risques(risque_file)
            n_ca, ca_skipped = self.import_conduites(ca_file)
            n_endemies, endemie_skipped = self.import_endemies(endemie_file)
            n_pays = self.import_pays(pays_file)
            n_zs, zs_skipped = self.import_zones_saines(zonesaine_file)

        self.stdout.write(self.style.SUCCESS(
            f"\nImport terminé : {n_zones} zones, {n_risques} risques, "
            f"{n_ca} conduites à tenir, {n_endemies} endémies, {n_pays} pays, "
            f"{n_zs} zones saines."
        ))

        if zone_issues:
            self.stdout.write(self.style.WARNING(
                f"\n{len(zone_issues)} zones importées avec geom=NULL :"
            ))
            for source_id, nom, note in zone_issues[:20]:
                self.stdout.write(f"  - id={source_id} nom={nom}: {note}")
            if len(zone_issues) > 20:
                self.stdout.write(f"  ... et {len(zone_issues) - 20} de plus")

        if ca_skipped:
            self.stdout.write(self.style.WARNING(
                f"{ca_skipped} conduites à tenir ignorées (risque_uid inconnu)."
            ))
        if endemie_skipped:
            self.stdout.write(self.style.WARNING(
                f"{endemie_skipped} lignes endemie ignorées (zone ou conduite introuvable)."
            ))
        if zs_skipped:
            self.stdout.write(self.style.WARNING(
                f"{zs_skipped} zones saines ignorées (coordonnées manquantes)."
            ))

    def import_zones(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        issues = []
        count = 0
        for z in data["zone"]:
            points, note = parse_coords(z["coords"])
            geom = None
            if points is not None:
                try:
                    geom = MultiPolygon(Polygon(points))
                except Exception as exc:
                    note = f"géométrie invalide après parsing : {exc}"
            Zone.objects.update_or_create(
                source_id=z["id"],
                defaults={"nom": z["nom"], "geom": geom, "note": note or ""},
            )
            count += 1
            if note:
                issues.append((z["id"], z["nom"], note))
        return count, issues

    def import_risques(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for r in data["risque"]:
            Risque.objects.update_or_create(
                code=r["id"],
                defaults=dict(
                    libelle_fr=r["libelle_fr"] or "",
                    libelle_en=r["libelle_en"] or "",
                    nature_du_risque_fr=r["naturedurisque_fr"] or "",
                    nature_du_risque_en=r["naturedurisque_en"] or "",
                    lien_fr=r["lien_fr"],
                    lien_en=r["lien_en"],
                    ordre=r["ordre"],
                    cat_zones_saines_fr=r["catzonessaines_fr"] or "",
                    cat_zones_saines_en=r["catzonessaines_en"] or "",
                    legende_zones_saines_fr=r["legendezonessaines_fr"] or "",
                    legende_zones_saines_en=r["legendezonessaines_en"] or "",
                    couleur_legende=r["couleurlegende"],
                    legende_fr=r["legende_fr"] or "",
                    legende_en=r["legende_en"] or "",
                ),
            )
            count += 1
        return count

    def import_conduites(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        skipped = 0
        for c in data["conduiteatenir"]:
            try:
                risque = Risque.objects.get(code=c["risque_uid"])
            except Risque.DoesNotExist:
                skipped += 1
                continue
            ConduiteATenir.objects.update_or_create(
                code=c["code"],
                defaults=dict(
                    risque=risque,
                    nature_du_risque_fr=c["naturedurisque_fr"] or "",
                    nature_du_risque_en=c["naturedurisque_en"] or "",
                    recommandation_fr=c["recommandation_fr"] or "",
                    recommandation_en=c["recommandation_en"] or "",
                    legende_fr=c["legende_fr"] or "",
                    legende_en=c["legende_en"] or "",
                    couleur=c["couleur"],
                ),
            )
            count += 1
        return count, skipped

    def import_endemies(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        skipped = 0
        Endemie.objects.all().delete()  # pas de clé naturelle fiable -> réimport complet
        to_create = []
        for e in data["endemie"]:
            try:
                zone = Zone.objects.get(source_id=e["zone_id"])
                conduite = ConduiteATenir.objects.get(code=e["conduiteatenir_code"])
            except (Zone.DoesNotExist, ConduiteATenir.DoesNotExist):
                skipped += 1
                continue
            to_create.append(Endemie(
                zone=zone,
                conduite_a_tenir=conduite,
                date_debut=e["datedeb"],
                date_fin=e["datefin"],
            ))
        Endemie.objects.bulk_create(to_create, batch_size=500)
        return len(to_create), skipped

    def import_pays(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        # Champs déjà modélisés explicitement -> exclus du blob JSON restant
        known_fields = {
            "uid", "code", "libelle_fr", "libelle_en",
            "box_so_lat", "box_so_long", "box_ne_lat", "box_ne_long",
            "center_lat", "center_long", "flash_fr", "flash_en",
        }
        count = 0
        for p in data["pays"]:
            center = None
            if p["center_lat"] is not None and p["center_long"] is not None:
                center = Point(p["center_long"], p["center_lat"], srid=4326)

            synthese = {k: v for k, v in p.items() if k not in known_fields}

            Pays.objects.update_or_create(
                source_id=p["uid"],
                defaults=dict(
                    code=p["code"],
                    libelle_fr=p["libelle_fr"] or "",
                    libelle_en=p["libelle_en"] or "",
                    box_so_lat=p["box_so_lat"],
                    box_so_long=p["box_so_long"],
                    box_ne_lat=p["box_ne_lat"],
                    box_ne_long=p["box_ne_long"],
                    center=center,
                    flash_fr=p["flash_fr"],
                    flash_en=p["flash_en"],
                    risques_synthese=synthese,
                ),
            )
            count += 1
        return count

    def import_zones_saines(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        skipped = 0
        for z in data["zonesaine"]:
            if z["lat"] is None or z["long"] is None:
                skipped += 1
                continue

            conduite = None
            code = z["endemie_cat_code"]
            if code:  # exclut None et ""
                conduite = ConduiteATenir.objects.filter(code=code).first()

            zone = None
            if z["endemie_zone_id"] is not None:
                zone = Zone.objects.filter(source_id=z["endemie_zone_id"]).first()

            pays = None
            if z["pays_uid"] is not None:
                pays = Pays.objects.filter(source_id=z["pays_uid"]).first()

            ZoneSaine.objects.update_or_create(
                source_id=z["id"],
                defaults=dict(
                    libelle_fr=z["libelle_fr"] or "",
                    libelle_en=z["libelle_en"],
                    point=Point(z["long"], z["lat"], srid=4326),
                    conduite_a_tenir=conduite,
                    zone=zone,
                    pays=pays,
                ),
            )
            count += 1
        return count, skipped
