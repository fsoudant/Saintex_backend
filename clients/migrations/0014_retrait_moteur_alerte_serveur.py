# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check`.
#
# Cf. saintex-spec-technique.md §4, §5 et §7 (révision d'octobre 2026) : la
# détection se fait sur le téléphone, le serveur ne reçoit plus aucune
# position. Retrait de l'ancien moteur d'alerte côté serveur :
# - UserRiskZoneStatus (état des zones actives) : désormais tenu sur le téléphone ;
# - NotificationLog.position : plus aucune position conservée ;
# - type de notification rappel_zone : les rappels sont locaux.
# Les tables clients_* étaient vides au dernier contrôle : aucune donnée perdue.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0013_alertreport_sante_protection_degradee'),
    ]

    operations = [
        migrations.DeleteModel(
            name='UserRiskZoneStatus',
        ),
        migrations.RemoveField(
            model_name='notificationlog',
            name='position',
        ),
        migrations.AlterField(
            model_name='notificationlog',
            name='endemie',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notifications',
                to='risks.endemie',
                help_text="Renseignée pour le SMS court d'une alerte d'entrée en zone (alerte_zone), nulle pour les autres types",
            ),
        ),
        migrations.AlterField(
            model_name='notificationlog',
            name='type_notification',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('alerte_zone', 'Alerte entrée en zone à risque'),
                    ('relance_silence', 'Relance appli silencieuse'),
                    ('protection_degradee', "Protection dégradée de l'appli"),
                ],
            ),
        ),
    ]
