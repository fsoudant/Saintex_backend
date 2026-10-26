"""
Mesure la taille réelle du cache hors ligne (cf. saintex-spec-technique.md §5).
N'écrit rien en base.

Depuis octobre 2026 le cache transmis aux téléphones est MONDIAL (identique
pour tous) : par défaut, la commande mesure ce cache. L'option --rayon permet
de mesurer, pour comparaison, un cache limité à un rayon autour de quelques
positions d'exemple — utile si le cache mondial devenait un jour trop gros.

Usage :
    python manage.py mesurer_cache                      # cache mondial (celui réellement transmis)
    python manage.py mesurer_cache --rayon 500          # cache limité à 500 km, positions d'exemple
    python manage.py mesurer_cache --rayon 500 --lat 12.6 --lon -8   # un point précis (ici : Bamako)
"""

import gzip
import json

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError

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
    help = "Mesure la taille du cache hors ligne (mondial par défaut), sans rien écrire en base."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rayon", type=int,
            help="Mesure un cache limité à ce rayon (km) autour de positions d'exemple, "
                 "au lieu du cache mondial.",
        )
        parser.add_argument("--lat", type=float, help="Avec --rayon : latitude d'un point précis.")
        parser.add_argument("--lon", type=float, help="Avec --rayon : longitude d'un point précis.")

    def handle(self, *args, **options):
        rayon = options["rayon"]
        if (options["lat"] is None) != (options["lon"] is None):
            raise CommandError("--lat et --lon doivent être fournis ensemble.")
        if options["lat"] is not None and rayon is None:
            raise CommandError("--lat/--lon n'ont de sens qu'avec --rayon (le cache normal est mondial).")

        if rayon is None:
            mesures = [("Monde entier", construire_cache())]
            self.stdout.write("Cache mondial (celui transmis aux téléphones)\n")
        else:
            if options["lat"] is not None:
                points = [("Point demandé", options["lat"], options["lon"])]
            else:
                points = POINTS_EXEMPLES
            mesures = [
                (nom, construire_cache(Point(lon, lat, srid=4326), rayon_km=rayon))
                for nom, lat, lon in points
            ]
            self.stdout.write(f"Cache limité à {rayon} km autour de chaque position\n")

        self.stdout.write(f"{'Position':<16}{'Endémies':>10}{'Géométries':>12}{'JSON (Ko)':>12}{'gzip (Ko)':>12}")

        pire = ("", 0)
        for nom, cache in mesures:
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
            "Repère : quelques centaines de Ko restent raisonnables ; au-delà de quelques Mo, "
            "envisager de réduire la précision des géométries ou de limiter le cache à un rayon."
        )
