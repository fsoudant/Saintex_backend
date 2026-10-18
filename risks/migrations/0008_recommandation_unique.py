# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check` avant déploiement.
#
# Cf. saintex-spec-technique.md §8 : décision d'octobre 2026 avec le
# co-fondateur médical — le questionnaire de vaccination est abandonné (les
# déclarations des clients ne sont pas fiables), donc plus de messages
# différenciés protégé / non protégé. Retour à un texte unique par conduite à
# tenir : suppression de recommandation_protege_fr/en (jamais rédigés, donc
# aucune perte de contenu) et retour de recommandation_non_protege_fr/en au
# nom recommandation_fr/en (données des 81 conduites préservées).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0007_recommandation_protege'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='conduiteatenir',
            name='recommandation_protege_fr',
        ),
        migrations.RemoveField(
            model_name='conduiteatenir',
            name='recommandation_protege_en',
        ),
        migrations.RenameField(
            model_name='conduiteatenir',
            old_name='recommandation_non_protege_fr',
            new_name='recommandation_fr',
        ),
        migrations.RenameField(
            model_name='conduiteatenir',
            old_name='recommandation_non_protege_en',
            new_name='recommandation_en',
        ),
        migrations.AlterField(
            model_name='conduiteatenir',
            name='recommandation_fr',
            field=models.TextField(
                blank=True,
                help_text=(
                    "Conduite à tenir transmise au voyageur à l'entrée dans la zone "
                    "(texte validé par l'équipe médicale). Texte unique pour tous les "
                    "voyageurs : la distinction protégé / non protégé a été abandonnée "
                    "en octobre 2026 (cf. spec §8)."
                ),
            ),
        ),
        migrations.AlterField(
            model_name='risque',
            name='vaccin_disponible',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Information indicative : un vaccin existe-t-il pour ce risque ? "
                    "Faux notamment pour le paludisme (PAL), qui n'a pas de vaccin. "
                    "N'intervient plus dans les notifications depuis l'abandon du "
                    "questionnaire vaccinal (octobre 2026)."
                ),
            ),
        ),
    ]
