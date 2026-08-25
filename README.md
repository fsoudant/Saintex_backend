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

5. **Créer le compte admin** — ajouter 3 variables d'environnement sur Render
   (onglet *Environment* du service) : `DJANGO_SUPERUSER_USERNAME`,
   `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`. Elles sont lues
   automatiquement au démarrage du conteneur (`entrypoint.sh`) — pas besoin
   du Shell Render, indisponible sur le palier gratuit.

6. **Importer les données historiques**, toujours sans Shell :
   - Créer un sous-dossier `legacy_exports/` à la racine du repo, y copier
     les 6 fichiers JSON (`_zone__202608221002.json`,
     `risque_202608222244.json`, `conduiteatenir_202608222244.json`,
     `endemie_202608222243.json`, `pays_202608241323.json`,
     `zonesaine_202608241320.json`).
   - Sur Render, ajouter la variable d'environnement `RUN_LEGACY_IMPORT=true`.
   - `git add . && git commit -m "Import données historiques" && git push`
     — Render redéploie, et l'import se lance automatiquement au démarrage.
   - Une fois l'import confirmé (cf. étape 7), repasser `RUN_LEGACY_IMPORT`
     à `false` sur Render, pour que l'import ne se relance pas à chaque
     redémarrage du conteneur (le palier gratuit s'endort après 15 min
     d'inactivité et redémarre au prochain accès).

7. **Accéder à l'admin** : `https://<nom-du-service>.onrender.com/admin/`
   — se connecter avec le compte créé à l'étape 5. Le médecin peut consulter
   et modifier `Zone`, `Risque`, `ConduiteATenir`, `Endemie`, `Pays` et
   `ZoneSaine`, avec widget carte pour les champs géométriques.

## En attente / non bloquant

- Watchdog de relance et logique de notification : pas encore implémentés
  dans ce prototype (prévu via un Render Cron Job plutôt que Celery Beat,
  cf. décision prise sur le coût d'hébergement).
- Quelques anomalies mineures dans les données historiques à nettoyer côté
  MariaDB quand tu auras le temps (3 zones nommées de façon incohérente :
  `MG_PES`, `PLS`, une entrée avec un espace en début de nom).
