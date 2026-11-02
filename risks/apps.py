from django.apps import AppConfig


class RisksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "risks"
    # Titre de la section sur la page d'accueil de l'administration
    # (sinon Django affiche le nom technique de l'application, « Risks »).
    verbose_name = "Risques"
