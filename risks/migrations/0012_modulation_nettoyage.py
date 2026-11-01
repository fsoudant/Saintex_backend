# Évolution d'octobre 2026 — recommandation unique par risque, `Modulation`
# (cf. saintex-spec-technique.md §7 et §8). Étape 3/3 : nettoyage du schéma.
#
# - `Endemie.risque` devient obligatoire (rempli par la 0011) ;
# - `Modulation` perd les attributs qui vivent désormais sur `Risque` : risque,
#   nature du risque fr/en, recommandation fr/en, légende fr/en, couleur.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0011_modulation_donnees'),
    ]

    operations = [
        migrations.AlterField(
            model_name='endemie',
            name='risque',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='endemies',
                to='risks.risque',
            ),
        ),
        migrations.RemoveField(model_name='modulation', name='risque'),
        migrations.RemoveField(model_name='modulation', name='nature_du_risque_fr'),
        migrations.RemoveField(model_name='modulation', name='nature_du_risque_en'),
        migrations.RemoveField(model_name='modulation', name='recommandation_fr'),
        migrations.RemoveField(model_name='modulation', name='recommandation_en'),
        migrations.RemoveField(model_name='modulation', name='legende_fr'),
        migrations.RemoveField(model_name='modulation', name='legende_en'),
        migrations.RemoveField(model_name='modulation', name='couleur'),
        migrations.AlterField(
            model_name='modulation',
            name='modulation_fr',
            field=models.TextField(
                blank=True,
                help_text=(
                    "Phrase qui précise le contexte du risque (ex. « Le risque est majoré "
                    "si vous séjournez en milieu rural. », « Le risque est réduit "
                    "au-dessus de 1500 mètres d'altitude »)."
                ),
            ),
        ),
    ]
