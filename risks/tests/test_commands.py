"""Tests de la commande de gestion ensure_superuser (création idempotente
du compte admin au démarrage du conteneur).

Aucune base de données : l'ORM est simulé par des mocks.
"""

from unittest import mock

from django.test import SimpleTestCase

from risks.management.commands.ensure_superuser import Command


class EnsureSuperuserTests(SimpleTestCase):
    def _patched(self, **env):
        # clear=True : isole complètement os.environ pendant le test pour que
        # des variables de l'hôte (ex. DJANGO_SUPERUSER_*) ne s'y reflètent pas.
        return mock.patch.dict("os.environ", env, clear=True)

    def test_variables_absentes_aucune_creation(self):
        user_model = mock.MagicMock()
        with mock.patch(
            "risks.management.commands.ensure_superuser.get_user_model",
            return_value=user_model,
        ), self._patched():
            Command().handle()
        # get_user_model() est appelé en tête de handle() même sans variables,
        # mais aucune création ne doit être tentée.
        user_model.objects.filter.assert_not_called()
        user_model.objects.create_superuser.assert_not_called()

    def test_compte_existant_rien_a_faire(self):
        user_model = mock.MagicMock()
        user_model.objects.filter.return_value.exists.return_value = True
        with mock.patch(
            "risks.management.commands.ensure_superuser.get_user_model",
            return_value=user_model,
        ), self._patched(
            DJANGO_SUPERUSER_USERNAME="admin",
            DJANGO_SUPERUSER_EMAIL="a@b.c",
            DJANGO_SUPERUSER_PASSWORD="secret",
        ):
            Command().handle()
        # On vérifie bien l'existence sans rien créer.
        user_model.objects.filter.assert_called_once_with(username="admin")
        user_model.objects.create_superuser.assert_not_called()

    def test_creation_du_superuser(self):
        user_model = mock.MagicMock()
        user_model.objects.filter.return_value.exists.return_value = False
        with mock.patch(
            "risks.management.commands.ensure_superuser.get_user_model",
            return_value=user_model,
        ), self._patched(
            DJANGO_SUPERUSER_USERNAME="admin",
            DJANGO_SUPERUSER_EMAIL="a@b.c",
            DJANGO_SUPERUSER_PASSWORD="secret",
        ):
            Command().handle()
        user_model.objects.create_superuser.assert_called_once_with(
            username="admin", email="a@b.c", password="secret"
        )