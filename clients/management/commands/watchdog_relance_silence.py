"""
Commande appelée périodiquement par le watchdog "appli silencieuse" (§8) —
cf. clients.watchdog pour la logique de détection/déclenchement. Destinée à
être planifiée via un Render Cron Job (cf. clients/watchdog.py, docstring de
module) plutôt que Celery Beat.
"""

from django.core.management.base import BaseCommand

from clients.watchdog import traiter_relances_silence


class Command(BaseCommand):
    help = (
        "Détecte les utilisateurs en silence (last_contact_at) au-delà du "
        "seuil de relance (§8 : 7h puis toutes les 6h) et leur envoie une "
        "relance. Idempotent : sûr à appeler fréquemment (cron toutes les "
        "15 min par exemple), ne duplique pas les envois déjà faits pour "
        "le cycle en cours."
    )

    def handle(self, *args, **options):
        notifies = traiter_relances_silence()

        if not notifies:
            self.stdout.write("Aucun utilisateur en silence à relancer.")
            return

        self.stdout.write(
            self.style.SUCCESS(f"{len(notifies)} utilisateur(s) relancé(s) pour silence prolongé.")
        )
