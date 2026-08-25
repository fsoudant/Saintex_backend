import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Crée un superutilisateur à partir de DJANGO_SUPERUSER_USERNAME / "
        "_EMAIL / _PASSWORD, seulement s'il n'existe pas déjà. Contrairement "
        "à 'createsuperuser --noinput', ne plante pas si le compte existe "
        "déjà — sûr à appeler à chaque démarrage du conteneur."
    )

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not (username and password):
            self.stdout.write(self.style.WARNING(
                "DJANGO_SUPERUSER_USERNAME / _PASSWORD absents des variables "
                "d'environnement — aucun compte créé."
            ))
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Superutilisateur '{username}' déjà présent, rien à faire.")
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superutilisateur '{username}' créé."))
