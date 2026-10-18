# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check` avant déploiement.
#
# Cf. saintex-spec-technique.md §8 : décision d'octobre 2026 avec le
# co-fondateur médical — les déclarations de vaccination des clients ne sont
# pas fiables (délai d'établissement des anticorps, ancienneté du vaccin...) :
# le questionnaire vaccinal est abandonné, et la notion de voyage en famille
# (qui n'existait que pour lire ce questionnaire) disparaît avec lui.
# Les tables clients_* étaient vides au dernier contrôle : aucune donnée perdue.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0008_rename_clients_not_utilisa_idx_clients_not_utilisa_178d80_idx_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='VaccinationRisque',
        ),
        migrations.RemoveField(
            model_name='utilisateur',
            name='voyage_en_famille',
        ),
    ]
