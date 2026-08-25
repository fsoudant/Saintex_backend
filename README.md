# Saintex — Backend (prototype back-office)

## Déploiement sur Render (palier gratuit)

1. **Créer le dépôt** : pousser ce dossier (`saintex_backend/`) sur un nouveau
   dépôt GitHub depuis ton Mac :
   ```
   cd saintex_backend
   git init
   git add .
   git commit -m "Squelette backend Saintex"
   gh repo create saintex-backend --private --source=. --push
   ```
   (ou via l'interface GitHub si tu préfères ne pas utiliser `gh`)

2. **Créer le service sur Render** :
   - Dashboard Render → *New* → *Web Service*
   - Connecter le dépôt GitHub `saintex-backend`
   - Environnement : **Docker** (Render détecte le `Dockerfile` automatiquement)
   - Plan : **Free**

3. **Variables d'environnement** (onglet *Environment* du service) :
   - `DJANGO_SECRET_KEY` — Render peut la générer automatiquement (cf. `render.yaml`)
   - `DJANGO_DEBUG` = `false`
   - `DJANGO_ALLOWED_HOSTS` = `.onrender.com`
   - `DATABASE_URL` — la chaîne de connexion **directe** (pas "pooled") copiée
     depuis la console Neon, *Connection Details*

4. **Déployer** — Render construit l'image et démarre le service. Premier
   accès après une période d'inactivité : 30-60 secondes (palier gratuit,
   sans incidence pour un usage ponctuel par le médecin).

5. **Initialiser la base**, depuis l'onglet *Shell* du service sur Render
   (ou en local si `DATABASE_URL` est aussi dans ton `.env`) :
   ```
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py migrate_legacy_data /chemin/vers/le/dossier/json
   ```
   Le dossier JSON doit contenir les 6 fichiers : `_zone__202608221002.json`,
   `risque_202608222244.json`, `conduiteatenir_202608222244.json`,
   `endemie_202608222243.json`, `pays_202608241323.json`,
   `zonesaine_202608241320.json`.

   Sur le palier gratuit, le shell Render n'a pas accès à des fichiers
   locaux — le plus simple est de committer temporairement le dossier JSON
   dans le repo (dans un sous-dossier, ex. `legacy_exports/`) pour que la
   commande puisse le lire depuis le service déployé, puis de le retirer
   une fois l'import fait.

6. **Accéder à l'admin** : `https://<nom-du-service>.onrender.com/admin/`
   — se connecter avec le compte créé à l'étape 5. Le médecin peut consulter
   et modifier `Zone`, `Risque`, `ConduiteATenir`, `Endemie` et `ZoneSaine`,
   avec widget carte pour les champs géométriques.

## En attente / non bloquant

- Watchdog de relance et logique de notification : pas encore implémentés
  dans ce prototype (prévu via un Render Cron Job plutôt que Celery Beat,
  cf. décision prise sur le coût d'hébergement).
- Quelques anomalies mineures dans les données historiques à nettoyer côté
  MariaDB quand tu auras le temps (3 zones nommées de façon incohérente :
  `MG_PES`, `PLS`, une entrée avec un espace en début de nom).
