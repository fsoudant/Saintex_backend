import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Codes de vérification par email pour la réinscription à un compte
    existant (cf. clients.inscription)."""

    dependencies = [
        ("clients", "0014_retrait_moteur_alerte_serveur"),
    ]

    operations = [
        migrations.CreateModel(
            name="CodeVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "reference",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Identifiant opaque remis au téléphone qui a demandé le code.",
                        unique=True,
                    ),
                ),
                (
                    "code_hash",
                    models.CharField(
                        help_text="Empreinte du code (HMAC), jamais le code lui-même.", max_length=64
                    ),
                ),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("expire_le", models.DateTimeField()),
                ("tentatives", models.PositiveSmallIntegerField(default=0)),
                (
                    "utilise_le",
                    models.DateTimeField(
                        blank=True,
                        help_text="Renseigné dès que le code a servi, ou qu'un code plus récent l'a remplacé.",
                        null=True,
                    ),
                ),
                (
                    "utilisateur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="codes_verification",
                        to="clients.utilisateur",
                    ),
                ),
            ],
            options={
                "verbose_name": "Code de vérification",
                "verbose_name_plural": "Codes de vérification",
                "ordering": ["-cree_le"],
            },
        ),
    ]
