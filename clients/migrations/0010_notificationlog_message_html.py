# Generated manually (pas de shell disponible sur cette machine) —
# à vérifier avec `python manage.py makemigrations --check`.
#
# Cf. saintex-spec-technique.md §8 : les recommandations sont désormais du
# texte enrichi (HTML limité). Le journal de preuve garde la version HTML
# réellement envoyée par email, en plus du texte brut (SMS, push).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0009_abandon_vaccination_famille'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationlog',
            name='message_html',
            field=models.TextField(
                blank=True,
                help_text=(
                    "Version HTML (texte enrichi : liens, gras...) du message, figée à "
                    "l'envoi — renseignée pour le canal email uniquement ; `message` reste "
                    "la version texte brut (SMS, push)."
                ),
            ),
        ),
    ]
