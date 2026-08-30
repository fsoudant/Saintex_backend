from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0003_endemie_zone_exclue_zone_pays_delete_zonesaine'),
    ]

    operations = [
        migrations.AddField(
            model_name='conduiteatenir',
            name='saison_mois_debut',
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[
                    (1, 'Janvier'), (2, 'Février'), (3, 'Mars'), (4, 'Avril'),
                    (5, 'Mai'), (6, 'Juin'), (7, 'Juillet'), (8, 'Août'),
                    (9, 'Septembre'), (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre'),
                ],
                help_text=(
                    "Mois de début de la période à risque (ex. rec_fr mentionnant "
                    "'d'août à novembre'). Vide = risque non saisonnier, actif toute "
                    "l'année. À renseigner avec saison_mois_fin, jamais seul."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='conduiteatenir',
            name='saison_mois_fin',
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[
                    (1, 'Janvier'), (2, 'Février'), (3, 'Mars'), (4, 'Avril'),
                    (5, 'Mai'), (6, 'Juin'), (7, 'Juillet'), (8, 'Août'),
                    (9, 'Septembre'), (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre'),
                ],
                help_text=(
                    "Mois de fin de la période à risque (inclus). Peut être inférieur à "
                    "saison_mois_debut pour une période à cheval sur le nouvel an "
                    "(ex. 'd'octobre à février' → début=10, fin=2)."
                ),
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name='conduiteatenir',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(saison_mois_debut__isnull=True, saison_mois_fin__isnull=True)
                    | models.Q(saison_mois_debut__isnull=False, saison_mois_fin__isnull=False)
                ),
                name='conduiteatenir_saison_mois_ensemble',
            ),
        ),
    ]
