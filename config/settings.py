"""
Django settings — Saintex backend.

Base de données : PostgreSQL + PostGIS hébergé sur Neon.
Toute la config sensible passe par des variables d'environnement (.env),
jamais en dur ici.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# ----------------------------------------------------------------------
# Charger le .env (au même niveau que manage.py)
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ----------------------------------------------------------------------
# Paramètres de base — lecture depuis les variables d'environnement
# (préfixe DJANGO_, cf. entrypoint.sh / config Render)
# ----------------------------------------------------------------------
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# -------------------  paramètres de sécurité HTTP/HTTPS  -------------------
# Render termine le TLS au niveau de son proxy et transmet la requête en HTTP
# simple au conteneur ; sans cet en-tête, Django ne voit jamais "https" et
# SECURE_SSL_REDIRECT=True provoque une boucle de redirection infinie.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "False").lower() == "true"
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "False").lower() == "true"
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "False").lower() == "true"
SECURE_CONTENT_TYPE_NOSNIFF = os.getenv("DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", "False").lower() == "true"
SECURE_BROWSER_XSS_FILTER = os.getenv("DJANGO_SECURE_BROWSER_XSS_FILTER", "False").lower() == "true"

SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "False").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "False").lower() == "true"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",  # GeoDjango — nécessaire pour PostGIS
    "rest_framework",
    "risks",  # Zone, Risque, ConduiteATenir, Endemie
    "clients",  # Utilisateur, Position, PushToken, PreferenceChangeLog (cf. Saintex.rtf §5)
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de données -------------------------------------------------------
# DATABASE_URL attendue au format :
#   postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
# Le moteur "postgis" (et non le "postgresql" standard) est requis pour que
# GeoDjango sache gérer les champs géométriques (Zone.geom).
_database_url = os.environ["DATABASE_URL"]
if "test" in sys.argv:
    # `manage.py test` a besoin de CREATE/DROP DATABASE pour la base de test
    # éphémère — opérations qui se comportent mal derrière le pooler PgBouncer
    # de Neon (sessions qui trainent, DROP DATABASE bloqué par "other users").
    # On bascule donc automatiquement sur la connexion directe (sans
    # "-pooler") pour les tests uniquement, sans toucher à .env.
    _database_url = _database_url.replace("-pooler.", ".")

DATABASES = {
    "default": dj_database_url.parse(
        _database_url,
        engine="django.contrib.gis.db.backends.postgis",
        conn_max_age=600,
    )
}

# --- GDAL / GEOS -------------------------------------------------------
# GeoDjango s'appuie sur des bibliothèques système (pas des paquets pip) :
#   macOS   : brew install gdal geos proj
#   Ubuntu  : apt install gdal-bin libgdal-dev libgeos-dev libproj-dev
# En général auto-détectées ; si Django ne les trouve pas au démarrage,
# pointer explicitement vers les librairies via GDAL_LIBRARY_PATH /
# GEOS_LIBRARY_PATH (variables d'environnement) — utile notamment sur macOS
# selon la version de Homebrew, ou pour utiliser celles embarquées dans un
# wheel Python (ex. pyogrio pour libgdal).
GDAL_LIBRARY_PATH = os.environ.get("GDAL_LIBRARY_PATH") or None
GEOS_LIBRARY_PATH = os.environ.get("GEOS_LIBRARY_PATH") or None

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # Jeton opaque propre aux voyageurs (Utilisateur.api_token), distinct des
    # comptes staff Django (cf. clients.authentication) ; ceux-ci continuent
    # de passer par la session admin classique, hors DRF.
    "DEFAULT_AUTHENTICATION_CLASSES": ["clients.authentication.UtilisateurTokenAuthentication"],
}
