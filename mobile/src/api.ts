import { getApiToken } from './storage';
import type {
  ContactRequest,
  ContactResponse,
  OnboardingPayload,
  Preferences,
  PreferencesUpdate,
} from './types';

// TODO: externaliser (build config Capacitor par environnement) plutôt que
// coder en dur — utile dès qu'un environnement de test/staging existe.
// Production = Mac dédié auto-hébergé (Render/Neon abandonnés).
const API_BASE = 'https://saintex.myddns.me/api';

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

// POST /api/cache/ — contact avec le serveur (spec §4 et §5) : remplace
// l'ancien envoi de position (/api/positions/, supprimé). Aucune position :
// le cache est mondial et identique pour tous. Envoie, tous champs
// facultatifs, la version du cache détenu, l'état de santé de l'appli
// (permissions) et les rapports d'alerte en attente ; reçoit les dates du
// contrat (le téléphone reste muet avant/après), le cache — ou "inchangé" —
// et les identifiants de rapports acquittés (à retirer de la file d'attente).
// Normalement appelé par le module natif en tâche de fond toutes les 6 h,
// pas par cette coque UI ; exposé ici pour les tests manuels.
export async function contactServeur(requete: ContactRequest = {}): Promise<ContactResponse> {
  const response = await authorizedFetch('/cache/', {
    method: 'POST',
    body: JSON.stringify(requete),
  });
  return response.json();
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
