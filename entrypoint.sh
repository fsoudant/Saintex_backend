#!/usr/bin/env bash
# Exécuté à chaque démarrage du conteneur (cf. Dockerfile).
# Remplace l'usage du Shell Render, indisponible sur le palier gratuit.
set -e

python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py ensure_superuser

if [ "$RUN_LEGACY_IMPORT" = "true" ]; then
    echo "RUN_LEGACY_IMPORT=true -> import des données historiques (legacy_exports/)..."
    python manage.py migrate_legacy_data legacy_exports/
else
    echo "RUN_LEGACY_IMPORT non activé -> import ignoré."
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
