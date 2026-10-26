# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check`.
#
# Cf. saintex-spec-technique.md §5, §7 et §8 (révision d'octobre 2026) :
# - rapports d'alerte remontés par le téléphone (AlertReport) ;
# - état de santé de l'appli déclaré à chaque contact (permissions de
#   localisation « Toujours » et de notifications) pour détecter une
#   protection dégradée ;
# - nouveau type de notification serveur : protection_degradee.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0012_remove_parametrecontrat_cache_rayon_km'),
        ('risks', '0009_recommandations_texte_enrichi'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisateur',
            name='localisation_toujours',
            field=models.BooleanField(
                null=True,
                blank=True,
                help_text=(
                    "Permission de localisation « Toujours » active sur le téléphone, selon "
                    "son dernier contact (nul tant qu'aucun état n'a été reçu). Sert à "
                    "détecter une protection dégradée (cf. saintex-spec-technique.md §8)."
                ),
            ),
        ),
        migrations.AddField(
            model_name='utilisateur',
            name='notifications_autorisees',
            field=models.BooleanField(
                null=True,
                blank=True,
                help_text=(
                    "Notifications autorisées sur le téléphone, selon son dernier contact "
                    "(nul tant qu'aucun état n'a été reçu). Sert à détecter une protection "
                    "dégradée (cf. saintex-spec-technique.md §8)."
                ),
            ),
        ),
        migrations.AddField(
            model_name='utilisateur',
            name='sante_declaree_le',
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="Horodatage de la dernière déclaration d'état de santé de l'appli par le téléphone.",
            ),
        ),
        migrations.AlterField(
            model_name='notificationlog',
            name='type_notification',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('alerte_zone', 'Alerte entrée en zone à risque'),
                    ('rappel_zone', 'Rappel de séjour prolongé'),
                    ('relance_silence', 'Relance appli silencieuse'),
                    ('protection_degradee', "Protection dégradée de l'appli"),
                ],
            ),
        ),
        migrations.CreateModel(
            name='AlertReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifiant_client', models.UUIDField(
                    help_text=(
                        "Identifiant généré par le téléphone pour cette alerte : permet de recevoir "
                        "le même rapport plusieurs fois (nouvel essai après une coupure réseau, mise "
                        "à jour de l'ouverture) sans créer de doublon."
                    ),
                )),
                ('zone_nom', models.CharField(
                    blank=True, max_length=255, help_text="Nom de la zone, figé à la réception du rapport",
                )),
                ('risque_code', models.CharField(
                    blank=True, max_length=32, help_text="Code du risque, figé à la réception du rapport",
                )),
                ('type_alerte', models.CharField(
                    max_length=10,
                    choices=[('entree', 'Entrée en zone à risque'), ('rappel', 'Rappel de séjour prolongé')],
                )),
                ('affichee_le', models.DateTimeField(
                    help_text="Horodatage d'affichage de l'alerte, selon l'horloge du téléphone",
                )),
                ('ouverte_le', models.DateTimeField(
                    null=True,
                    blank=True,
                    help_text="Horodatage d'ouverture de l'alerte par l'utilisateur, nul si jamais ouverte",
                )),
                ('cache_version', models.CharField(
                    blank=True,
                    max_length=64,
                    help_text="Version du cache détenu par le téléphone au moment de l'alerte",
                )),
                ('recue_le', models.DateTimeField(
                    auto_now_add=True, help_text="Horodatage de réception par le serveur",
                )),
                ('endemie', models.ForeignKey(
                    null=True,
                    blank=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='rapports_alerte',
                    to='risks.endemie',
                    help_text="Nulle si l'endémie rapportée n'existe pas (ou plus) côté serveur.",
                )),
                ('utilisateur', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rapports_alerte',
                    to='clients.utilisateur',
                )),
            ],
            options={
                'verbose_name': "Rapport d'alerte",
                'verbose_name_plural': "Rapports d'alerte",
                'ordering': ['-recue_le'],
            },
        ),
        migrations.AddIndex(
            model_name='alertreport',
            index=models.Index(fields=['utilisateur', '-recue_le'], name='alertrep_user_recue_idx'),
        ),
        migrations.AddConstraint(
            model_name='alertreport',
            constraint=models.UniqueConstraint(
                fields=('utilisateur', 'identifiant_client'),
                name='un_rapport_par_utilisateur_et_identifiant',
            ),
        ),
    ]
