# Déploiement d'un nouveau lot — Mac de démo (saintex.myddns.me)

Ce guide couvre la mise à jour du backend Saintex sur le Mac de démonstration
(macOS 12.7.6, Apache + Gunicorn + PostgreSQL/PostGIS local via Postgres.app),
distinct du déploiement automatique sur Render.

## Tronc commun (à faire à chaque fois)

```bash
cd ~/Documents/GitHub/Saintex_backend
git pull
```

Regarde ce qui a changé avant de continuer :

```bash
git log --oneline -5
git diff HEAD~1 HEAD --stat
```

Deux questions à se poser à la lecture du diff :
- `requirements.txt` a-t-il changé ?
- Y a-t-il de nouveaux fichiers dans un dossier `migrations/` (`clients/migrations/`, `risks/migrations/`) ?

Si `requirements.txt` a changé :

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Piège connu sur ce Mac** : le CPU est trop ancien pour les wheels NumPy
précompilées de PyPI (elles exigent le jeu d'instructions x86-64-v2 /
SSE4.2). Si `pip install` réinstalle NumPy et que l'admin Django plante au
démarrage avec une erreur du type *"NumPy was built with baseline
optimizations... but your machine doesn't support"*, relancer :

```bash
pip install numpy --no-binary numpy \
  --config-settings=setup-args="-Dcpu-baseline=native" \
  --config-settings=setup-args="-Dcpu-dispatch=none"
```

## Cas A — Lot sans impact sur la base de données

(correctifs, nouvelle vue, logique métier, évolutions mobile...)

```bash
sudo launchctl kickstart -k system/com.saintex.gunicorn
```

Rien d'autre. Apache ne fait que relayer vers Gunicorn (reverse proxy), pas
besoin d'y toucher.

## Cas B — Lot avec migrations Django

(nouveau champ, nouvelle table, modification de contrainte...)

```bash
python manage.py migrate
sudo launchctl kickstart -k system/com.saintex.gunicorn
```

Contrairement à Render (où `migrate` tourne automatiquement au déploiement),
ici c'est une étape manuelle, à faire juste après le `pip install`.

⚠️ **Vigilance** : si une migration future renomme ou supprime une colonne
déjà peuplée de données locales, `migrate` peut échouer ou faire perdre des
données. Pas de procédure générique — lire le contenu de la migration avant
de la lancer, et sauvegarder au besoin (`pg_dump` de `saintex_local` avant
d'appliquer).

## Cas C — Nouvelles données côté Neon (sans changement de code/schéma)

La base locale (`saintex_local`) est un **instantané figé**, pas une
réplique synchronisée avec Neon. Si de nouvelles zones/endémies sont
ajoutées en prod (par le médecin via l'admin, par exemple), ce Mac ne le
sait pas automatiquement.

Pour rafraîchir, refaire un export/import ciblé sur les tables `risks_*` :

```bash
/Applications/Postgres.app/Contents/Versions/18/bin/pg_dump "URL_NEON" -Fc -f saintex_neon_export.dump
/Applications/Postgres.app/Contents/Versions/18/bin/pg_restore -l saintex_neon_export.dump > restore_list.txt

# Sélection positive des tables métier uniquement (exclut auth_*/django_*/neon_auth.*)
grep -E "TABLE DATA public (risks_pays|risks_risque|risks_conduiteatenir|risks_zone|risks_endemie|clients_utilisateur|clients_pushtoken|clients_preferencechangelog|clients_vaccinationrisque|clients_userriskzonestatus|clients_notificationlog) " restore_list.txt > restore_list_business.txt
grep -E "SEQUENCE SET public (risks_pays|risks_zone|risks_endemie|clients_utilisateur|clients_pushtoken|clients_preferencechangelog|clients_vaccinationrisque|clients_userriskzonestatus|clients_notificationlog)_id_seq" restore_list.txt >> restore_list_business.txt

/Applications/Postgres.app/Contents/Versions/18/bin/pg_restore --data-only --disable-triggers -L restore_list_business.txt -d saintex_local saintex_neon_export.dump
```

⚠️ Si les données existent déjà localement, attends-toi à des erreurs de clé
primaire dupliquée sur les tables déjà peuplées (`pg_restore` les ignore et
continue) — pas grave en soi, mais à traiter au cas par cas plutôt que par
une procédure automatique pour l'instant. Voir aussi `restore_list.txt` /
`saintex_neon_export.dump` : à garder hors du dépôt Git (déjà dans
`.gitignore`).

## Aide-mémoire — commandes de vérification

```bash
# État des trois LaunchDaemons
sudo launchctl print system/com.saintex.apache | grep state
sudo launchctl print system/com.saintex.gunicorn | grep state
sudo launchctl print system/com.saintex.certbot-renew | grep state

# Ports en écoute
sudo lsof -iTCP -sTCP:LISTEN -P | grep httpd

# Logs
tail -50 /var/log/apache2/saintex-error.log
tail -50 ~/Documents/GitHub/Saintex_backend/logs/gunicorn-error.log

# Test local avant de blâmer le réseau/LiveBox
curl -vk https://localhost/
```

## Infrastructure de référence

- Domaine : `saintex.myddns.me` (No-IP, DynDNS activé sur la LiveBox, ports
  80/443 redirigés vers l'IP fixe du Mac)
- Certificat Let's Encrypt : renouvellement automatique via
  `/Library/LaunchDaemons/com.saintex.certbot-renew.plist` (2×/jour,
  `--deploy-hook "apachectl graceful"`)
- Apache : reverse proxy HTTPS → `127.0.0.1:8000`, daemon perso
  `/Library/LaunchDaemons/com.saintex.apache.plist` (le daemon Apple natif
  est bloqué par SIP sur cette machine)
- Gunicorn : `/Library/LaunchDaemons/com.saintex.gunicorn.plist`, tourne
  sous l'utilisateur `francois` (pas root)
- Base : PostgreSQL/PostGIS local via Postgres.app, connexion par socket
  Unix (`postgres://francois@/saintex_local?host=/tmp`) plutôt que TCP,
  pour éviter la popup macOS "Réseau local" qui bloque le démarrage
  automatique via `launchd`
