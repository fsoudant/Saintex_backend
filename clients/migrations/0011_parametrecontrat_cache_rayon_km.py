# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check`.
#
# Cf. saintex-spec-technique.md §5 : le rayon du cache hors ligne est
# paramétrable côté serveur, sans nouvelle version de l'appli.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0010_notificationlog_message_html'),
    ]

    operations = [
        migrations.AddField(
            model_name='parametrecontrat',
            name='cache_rayon_km',
            field=models.PositiveSmallIntegerField(
                default=500,
                help_text=(
                    "Rayon (en km) autour de la dernière position connue du téléphone dans "
                    "lequel le serveur lui transmet les zones à risque et leurs "
                    "recommandations (cache hors ligne, cf. §5). Modifiable sans nouvelle "
                    "version de l'appli ; à ajuster après mesure de la taille réelle du "
                    "cache (commande mesurer_cache)."
                ),
            ),
        ),
    ]
