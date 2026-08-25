"""
Django settings — Saintex backend.

Base de données : PostgreSQL + PostGIS hébergé sur Neon.
Toute la config sensible passe par des variables d'environnement (.env),
jamais en dur ici.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

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
DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        engine="django.contrib.gis.db.backends.postgis",
        conn_max_age=600,
    )
}

# --- GDAL / GEOS -------------------------------------------------------
# GeoDjango s'appuie sur des bibliothèques système (pas des paquets pip) :
#   macOS   : brew install gdal geos proj
#   Ubuntu  : apt install gdal-bin libgdal-dev libgeos-dev libproj-dev
# En général auto-détectées ; si Django ne les trouve pas au démarrage,
# décommenter et ajuster les chemins ci-dessous (utile notamment sur macOS
# selon la version de Homebrew) :
# GDAL_LIBRARY_PATH = "/opt/homebrew/opt/gdal/lib/libgdal.dylib"
# GEOS_LIBRARY_PATH = "/opt/homebrew/opt/geos/lib/libgeos_c.dylib"

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
}
