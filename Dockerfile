# Déploiement Render : image avec GDAL/GEOS/PROJ installés en tant que
# paquets système, indispensables à GeoDjango (django.contrib.gis).
# Sur Render : créer un "Web Service" à partir de ce repo, type d'environnement
# "Docker" — Render détecte ce Dockerfile automatiquement.

FROM python:3.12-slim

# Bibliothèques système requises par GeoDjango
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

# Render fournit le port via la variable d'environnement $PORT
CMD gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
