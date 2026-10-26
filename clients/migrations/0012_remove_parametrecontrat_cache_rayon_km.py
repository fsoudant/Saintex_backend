# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check`.
#
# Cf. saintex-spec-technique.md §5 : le cache hors ligne est désormais mondial
# (identique pour tous, mesuré à 386 Ko compressés sur les données réelles),
# donc plus de rayon à paramétrer — suppression du champ ajouté par 0011.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0011_parametrecontrat_cache_rayon_km'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='parametrecontrat',
            name='cache_rayon_km',
        ),
    ]
