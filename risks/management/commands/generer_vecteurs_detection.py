"""
Génère (ou vérifie) le jeu de cas de test PARTAGÉ de la détection locale, pour
les modules natifs Swift et Kotlin (cf. risks.vecteurs_detection et
saintex-spec-technique.md §5).

Usage :
    python manage.py generer_vecteurs_detection             # (ré)écrit tests_partages/detection_cache.json
    python manage.py generer_vecteurs_detection --verifier  # échoue si le fichier n'est pas à jour
"""

from django.core.management.base import BaseCommand, CommandError

from risks.vecteurs_detection import chemin_fichier, generer, serialiser


class Command(BaseCommand):
    help = "Génère le jeu de cas de test partagé de la détection locale (fichier JSON versionné)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--verifier", action="store_true",
            help="Ne rien écrire : échouer si le fichier existant n'est pas à jour.",
        )

    def handle(self, *args, **options):
        chemin = chemin_fichier()
        contenu = serialiser(generer())

        if options["verifier"]:
            if not chemin.exists() or chemin.read_text(encoding="utf-8") != contenu:
                raise CommandError(
                    f"{chemin} n'est pas à jour : lancer `python manage.py generer_vecteurs_detection`."
                )
            self.stdout.write(self.style.SUCCESS(f"{chemin} est à jour."))
            return

        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Jeu de test écrit : {chemin}"))
