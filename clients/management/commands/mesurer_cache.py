"""
Mesure la taille réelle du cache hors ligne (cf. saintex-spec-technique.md §5)
pour quelques positions représentatives, afin de décider du rayon de portée
(ParametreContrat.cache_rayon_km, 500 km par défaut) sur les données de
production plutôt qu'à l'estime. N'écrit rien en base.

Usage :
    python manage.py mesurer_cache                      # points d'exemple, rayon du paramétrage
    python manage.py mesurer_cache --rayon 300          # autre rayon
    python manage.py mesurer_cache --lat 12.6 --lon -8  # un point précis (ici : Bamako)
"""

import gzip
import json

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from clients.models import ParametreContrat
from risks.cache import construire_cache

# (nom, latitude, longitude) : zones endémiques variées, dont le cas
# antiméridien (Fidji) qui produit des géométries découpées.
POINTS_EXEMPLES = [
    ("Paris", 48.86, 2.35),
    ("Dakar", 14.69, -17.45),
    ("Bamako", 12.64, -8.00),
    ("Abidjan", 5.35, -4.02),
    ("Kinshasa", -4.32, 15.31),
    ("Nairobi", -1.29, 36.82),
    ("Antananarivo", -18.88, 47.51),
    ("Mumbai", 19.08, 72.88),
    ("Bangkok", 13.76, 100.50),
    ("Hanoï", 21.03, 105.85),
    ("Manaus", -3.12, -60.02),
    ("Cayenne", 4.92, -52.31),
    ("Lima", -12.05, -77.04),
    ("Suva (Fidji)", -18.14, 178.44),
]


def _ko(octets):
    return octets / 1024


class Command(BaseCommand):
    help = "Mesure la taille du cache hors ligne pour quelques positions (sans rien écrire en base)."

    def add_arguments(self, parser):
        parser.add_argument("--rayon", type=int, help="Rayon en km (défaut : paramétrage du serveur).")
        parser.add_argument("--lat", type=float, help="Latitude d'un point précis à mesurer.")
        parser.add_argument("--lon", type=float, help="Longitude d'un point précis à mesurer.")

    def handle(self, *args, **options):
        rayon = options["rayon"] or ParametreContrat.get_solo().cache_rayon_km

        if (options["lat"] is None) != (options["lon"] is None):
            self.stderr.write("--lat et --lon doivent être fournis ensemble.")
            return
        if options["lat"] is not None:
            points = [("Point demandé", options["lat"], options["lon"])]
        else:
            points = POINTS_EXEMPLES

        self.stdout.write(f"Rayon : {rayon} km\n")
        self.stdout.write(f"{'Position':<16}{'Endémies':>10}{'Géométries':>12}{'JSON (Ko)':>12}{'gzip (Ko)':>12}")

        pire = ("", 0)
        for nom, lat, lon in points:
            cache = construire_cache(Point(lon, lat, srid=4326), rayon_km=rayon)
            brut = json.dumps(cache, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            compresse = gzip.compress(brut)
            self.stdout.write(
                f"{nom:<16}{len(cache['endemies']):>10}{len(cache['geometries']):>12}"
                f"{_ko(len(brut)):>12.0f}{_ko(len(compresse)):>12.0f}"
            )
            if len(compresse) > pire[1]:
                pire = (nom, len(compresse))

        self.stdout.write(
            f"\nPlus gros cache compressé : {pire[0]} ({_ko(pire[1]):.0f} Ko). "
            "Repère : quelques centaines de Ko restent raisonnables pour un téléchargement "
            "toutes les 6 h ; au-delà de quelques Mo, réduire le rayon ou la précision."
        )
