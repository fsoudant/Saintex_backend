# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check` avant déploiement.
#
# Cf. saintex-spec-technique.md §8, décision réunion médicale : deux messages
# distincts par conduite à tenir (protégé/non protégé). Renomme
# recommandation_fr/en (préserve les données existantes des 81 conduites)
# en recommandation_non_protege_fr/en, et ajoute recommandation_protege_fr/en
# (vides, à rédiger par l'équipe médicale — cf. help_text du modèle : tant
# qu'ils sont vides, le moteur de notification retombe sur la version non
# protégée, jamais de texte vide envoyé).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0006_risque_vaccin_disponible'),
    ]

    operations = [
        migrations.RenameField(
            model_name='conduiteatenir',
            old_name='recommandation_fr',
            new_name='recommandation_non_protege_fr',
        ),
        migrations.RenameField(
            model_name='conduiteatenir',
            old_name='recommandation_en',
            new_name='recommandation_non_protege_en',
        ),
        migrations.AlterField(
            model_name='conduiteatenir',
            name='recommandation_non_protege_fr',
            field=models.TextField(
                blank=True,
                help_text=(
                    "Conduite à tenir affichée à un voyageur non protégé contre ce risque "
                    "(texte validé médical) — anciennement recommandation_fr, scindé en "
                    "deux textes distincts (§8, décision réunion médicale). Sert aussi "
                    "de repli si recommandation_protege_fr n'est pas encore rédigée."
                ),
            ),
        ),
        migrations.AddField(
            model_name='conduiteatenir',
            name='recommandation_protege_fr',
            field=models.TextField(
                blank=True,
                help_text=(
                    "Conduite à tenir affichée à un voyageur déjà protégé contre ce "
                    "risque (vacciné, cf. clients.VaccinationRisque) — texte distinct "
                    "décidé en réunion avec le co-fondateur médical (§8). Tant que ce "
                    "champ n'est pas rempli pour une conduite donnée, le moteur de "
                    "notification retombe sur recommandation_non_protege_fr (jamais de "
                    "texte vide envoyé, cf. clients/notifications.py)."
                ),
            ),
        ),
        migrations.AddField(
            model_name='conduiteatenir',
            name='recommandation_protege_en',
            field=models.TextField(blank=True),
        ),
    ]
