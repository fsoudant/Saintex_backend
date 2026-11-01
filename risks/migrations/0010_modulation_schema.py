# Évolution d'octobre 2026 — recommandation unique par risque, `Modulation`
# (cf. saintex-spec-technique.md §7 et §8). Étape 1/3 : schéma, sans perte.
#
# - `ConduiteATenir` est renommée `Modulation` (table, clés étrangères et
#   données conservées) ; `facteurs_de_risque_fr/en` devient `modulation_fr/en`.
# - `Endemie.conduite_a_tenir` devient `Endemie.modulation` (facultative) ;
#   `Endemie.risque` est ajoutée (nulle pour l'instant, remplie par la
#   migration 0011, puis rendue obligatoire par la 0012).
# - `Risque` reçoit la recommandation unique (remplie par la 0011).
# - Les anciens champs de la conduite (risque, nature du risque, recommandation,
#   légende, couleur) restent en place jusqu'à la 0012, pour que la 0011 puisse
#   les lire.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0009_recommandations_texte_enrichi'),
    ]

    operations = [
        migrations.AddField(
            model_name='risque',
            name='recommandation_fr',
            field=models.TextField(
                blank=True,
                help_text=(
                    "Recommandation unique du risque (texte enrichi validé par l'équipe "
                    "médicale), identique pour tous les voyageurs et toutes les zones "
                    "(cf. spec §8)."
                ),
            ),
        ),
        migrations.AddField(
            model_name='risque',
            name='recommandation_en',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='endemie',
            name='risque',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='endemies',
                to='risks.risque',
            ),
        ),
        # L'index sur l'ancienne clé étrangère est retiré avant le renommage,
        # puis recréé sous son nouveau nom.
        migrations.RemoveIndex(
            model_name='endemie',
            name='risks_endem_conduit_210725_idx',
        ),
        migrations.RemoveConstraint(
            model_name='conduiteatenir',
            name='conduiteatenir_saison_mois_ensemble',
        ),
        migrations.RenameModel(old_name='ConduiteATenir', new_name='Modulation'),
        migrations.RenameField(
            model_name='endemie',
            old_name='conduite_a_tenir',
            new_name='modulation',
        ),
        migrations.RenameField(
            model_name='modulation',
            old_name='facteurs_de_risque_fr',
            new_name='modulation_fr',
        ),
        migrations.RenameField(
            model_name='modulation',
            old_name='facteurs_de_risque_en',
            new_name='modulation_en',
        ),
        migrations.AlterField(
            model_name='endemie',
            name='modulation',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='endemies',
                to='risks.modulation',
                help_text=(
                    "Précision facultative du risque (milieu rural, altitude...) et "
                    "période de l'année concernée ; vide = risque actif toute l'année, "
                    "sans précision."
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name='modulation',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(saison_mois_debut__isnull=True, saison_mois_fin__isnull=True)
                    | models.Q(saison_mois_debut__isnull=False, saison_mois_fin__isnull=False)
                ),
                name='modulation_saison_mois_ensemble',
            ),
        ),
        migrations.AddIndex(
            model_name='endemie',
            index=models.Index(fields=['risque'], name='risks_endem_risque_idx'),
        ),
        migrations.AddIndex(
            model_name='endemie',
            index=models.Index(fields=['modulation'], name='risks_endem_modul_idx'),
        ),
    ]
