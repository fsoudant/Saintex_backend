from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("risks", "0013_pays_verbose_name_plural"),
    ]

    operations = [
        migrations.CreateModel(
            name="Conseil",
            fields=[
                (
                    "code",
                    models.SlugField(
                        help_text=(
                            "Identifiant court sans espace ni accent (ex. moustiques, diarrhee). Il sert dans "
                            "les liens des recommandations : il ne peut plus être modifié une fois la fiche créée."
                        ),
                        max_length=40,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("titre_fr", models.CharField(max_length=256)),
                ("titre_en", models.CharField(max_length=256)),
                (
                    "contenu_fr",
                    models.TextField(
                        blank=True,
                        help_text="Texte enrichi validé par l'équipe médicale (cf. risks.richtext).",
                    ),
                ),
                ("contenu_en", models.TextField(blank=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "fiche conseil",
                "verbose_name_plural": "fiches conseil",
                "ordering": ["titre_fr"],
            },
        ),
    ]
