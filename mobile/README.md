# Saintex — coque mobile (Capacitor, iOS)

Coque UI légère uniquement (écrans onboarding, tunnel premier lancement,
accueil/solde, préférences). Le cœur fonctionnel — géolocalisation en tâche
de fond toutes les 6h, démarrage au boot, notification locale hors ligne —
est du natif Swift, hors de ce dossier (cf. `saintex-spec-technique.md` §2).

TypeScript vanilla, pas de framework UI, pour rester cohérent avec l'esprit
"coque fine" de la spec.

## Mise en route

```bash
cd mobile
npm install
npm run build        # compile src/ -> www/dist/
npx cap add ios       # première fois seulement : génère le projet Xcode
npm run sync          # build + cap sync ios (à refaire après chaque modif de src/)
npm run open:ios      # ouvre le projet dans Xcode
```

Nécessite Xcode installé en local — non exécutable depuis un environnement
sans Xcode.

## État actuel / limites connues

- **Pas d'endpoint d'inscription côté backend** : `clients/views.py` le dit
  explicitement, le parcours de consentement RGPD exact reste à définir.
  Le tunnel (écran 2) simule donc la fin du parcours sans obtenir de vrai
  jeton API — voir les `TODO` dans `src/api.ts` et `src/screens/tunnel.ts`.
- **Pas d'endpoint de liste des pays** : liste en dur dans `tunnel.ts`
  (`PLACEHOLDER_COUNTRIES`), à remplacer dès qu'un `/api/pays/` existe.
- **Paiement** : lien externe simulé (`PLACEHOLDER_PAYMENT_URL`), pas
  d'intégration Stripe réelle.
- **Écrans réellement branchés au backend existant** : préférences
  (`GET`/`PATCH /api/me/`) et solde/statut d'abonnement (même endpoint,
  champ `subscription_status`) — ce sont les deux seuls endpoints API
  actuellement implémentés côté serveur (`clients/urls.py`).
- **Jeton API** : stocké via `@capacitor/preferences` sous la clé
  `saintex_api_token` (`src/storage.ts`) — le module natif devra lire la
  même clé pour s'authentifier lors du polling GPS. À aligner avec le code
  Swift quand il sera écrit.
- **Pas de module natif ici** : ce dossier ne contient aucune tâche de fond
  GPS, aucun code Swift. Uniquement la coque Capacitor/web.
