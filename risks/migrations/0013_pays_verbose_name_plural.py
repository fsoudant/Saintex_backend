# Cosmétique : « Pays » est invariable (l'administration affichait « Payss »).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('risks', '0012_modulation_nettoyage'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='pays',
            options={'verbose_name_plural': 'Pays'},
        ),
    ]
