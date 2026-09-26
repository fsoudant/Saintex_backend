# Generated manually (pas de shell disponible sur cette machine) — à
# vérifier avec `python manage.py makemigrations --check` avant déploiement.
#
# Cf. saintex-spec-technique.md §8, décision réunion médicale : question
# "voyagez-vous en famille ?" à l'inscription, ajoutée au traçage des
# préférences (PreferenceChangeLog.CHAMPS_TRACES).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0006_parametrecontrat'),
    ]

    operations = [
        migrations.AddField(
            model_name='utilisateur',
            name='voyage_en_famille',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Question \"voyagez-vous en famille ?\" posée à l'inscription "
                    "(cf. §8, décision réunion médicale). Si True, la couverture "
                    "vaccinale déclarée par risque (VaccinationRisque.vaccine) se lit "
                    "comme \"tous les membres de la famille sont protégés contre ce "
                    "risque\" plutôt que \"cet utilisateur est vacciné\" — cf. "
                    "clients/notifications.py, _composer_recommandation."
                ),
            ),
        ),
    ]
