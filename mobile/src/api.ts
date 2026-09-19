import { getApiToken } from './storage';
import type { OnboardingPayload, Preferences, PreferencesUpdate } from './types';

// TODO: externaliser (build config Capacitor par environnement) plutôt que
// coder en dur — utile dès qu'un environnement de test/staging existe.
const API_BASE = 'https://saintex-backend.onrender.com/api';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getApiToken();
  const headers = new Headers(init.headers);
  headers.set('Content-Type', 'application/json');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    throw new ApiError(response.status, `${init.method ?? 'GET'} ${path} a échoué (${response.status})`);
  }
  return response;
}

// GET /api/me/ — correspond à MePreferencesView côté backend (clients/views.py).
export async function fetchPreferences(): Promise<Preferences> {
  const response = await authorizedFetch('/me/');
  return response.json();
}

// PATCH /api/me/ — met à jour uniquement les champs autorisés par
// UtilisateurPreferencesSerializer (email/phone/subscription_status en
// lecture seule côté serveur).
export async function updatePreferences(update: PreferencesUpdate): Promise<Preferences> {
  const response = await authorizedFetch('/me/', {
    method: 'PATCH',
    body: JSON.stringify(update),
  });
  return response.json();
}

// POST /api/positions/ — polling GPS (spec §4). Normalement déclenché par
// le module natif Swift en tâche de fond, pas par cette coque UI ; exposé
// ici surtout pour permettre un test manuel pendant le développement.
export async function pollPosition(lat: number, lon: number): Promise<void> {
  await authorizedFetch('/positions/', {
    method: 'POST',
    body: JSON.stringify({ lat, lon }),
  });
}

// --- Fonctions non encore branchées à un vrai endpoint backend ---
//
// Aucune de ces routes n'existe encore côté serveur : ni inscription/compte,
// ni liste des pays, ni paiement. Le docstring de clients/views.py est
// explicite là-dessus ("l'inscription n'est volontairement pas traitée ici").
// Ces fonctions sont des points d'intégration prévus, pas des appels
// fonctionnels — à corriger dès que ces endpoints existent réellement.

export async function fetchAvailableCountries(): Promise<never> {
  throw new Error(
    "TODO: pas encore d'endpoint /api/pays/ côté backend — liste de pays actuellement en dur dans tunnel.ts"
  );
}

export async function submitOnboarding(_payload: OnboardingPayload): Promise<never> {
  throw new Error(
    "TODO: pas encore d'endpoint d'inscription côté backend (cf. docstring clients/views.py) — " +
      'le tunnel §6 ne peut pas encore créer de compte réel ni obtenir de jeton API'
  );
}
