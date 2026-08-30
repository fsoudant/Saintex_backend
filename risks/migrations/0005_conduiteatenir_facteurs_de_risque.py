from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0004_conduiteatenir_saison_mois'),
    ]

    operations = [
        migrations.AddField(
            model_name='conduiteatenir',
            name='facteurs_de_risque_fr',
            field=models.TextField(
                blank=True,
                help_text=(
                    "Circonstances qui augmentent l'exposition pour cette variante "
                    "(ex. 'Soirées ou nuitées en milieu rural', 'Séjour en zone rurale "
                    "ou boisée, en dessous de 1500 m d'altitude')"
                ),
            ),
        ),
        migrations.AddField(
            model_name='conduiteatenir',
            name='facteurs_de_risque_en',
            field=models.TextField(blank=True),
        ),
    ]
