import { getApiToken } from './storage';
import type {
  ContactRequest,
  ContactResponse,
  Contrat,
  InscriptionPayload,
  Preferences,
  PreferencesUpdate,
  ResultatInscription,
} from './types';

// TODO: externaliser (build config Capacitor par environnement) plutôt que
// coder en dur — utile dès qu'un environnement de test/staging existe.
// Production = Mac dédié auto-hébergé (Render/Neon abandonnés).
const API_BASE = 'https://saintex.myddns.me/api';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: unknown = null
  ) {
    super(message);
  }
}

// Premier message d'erreur de validation DRF pour un champ ({champ: ["message"]}),
// ou null : permet d'afficher tel quel le texte du serveur (ex. « date dans le passé »).
export function messageDeValidation(erreur: unknown, champ: string): string | null {
  if (!(erreur instanceof ApiError) || typeof erreur.body !== 'object' || erreur.body === null) {
    return null;
  }
  const valeur = (erreur.body as Record<string, unknown>)[champ];
  if (Array.isArray(valeur) && typeof valeur[0] === 'string') return valeur[0];
  if (typeof valeur === 'string') return valeur;
  return null;
}

// Message de l'API pour un champ « detail » (erreurs DRF hors validation de champ,
// ex. 503 « impossible d'envoyer le code »), ou null.
export function messageDetail(erreur: unknown): string | null {
  if (!(erreur instanceof ApiError) || typeof erreur.body !== 'object' || erreur.body === null) {
    return null;
  }
  const detail = (erreur.body as Record<string, unknown>).detail;
  return typeof detail === 'string' ? detail : null;
}

async function readError(response: Response, init: RequestInit, path: string): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // corps absent ou non JSON : on garde null
  }
  return new ApiError(response.status, `${init.method ?? 'GET'} ${path} a échoué (${response.status})`, body);
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
    throw await readError(response, init, path);
  }
  return response;
}

// Appel SANS jeton : l'inscription est ce qui fournit le jeton. On n'envoie jamais un
// jeton périmé qui traverserait une réinstallation.
async function publicPost(path: string, body: unknown): Promise<Response> {
  const init: RequestInit = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw await readError(response, init, path);
  }
  return response;
}

// POST /api/inscription/ — crée le compte et remet le jeton (201), ou, si l'email ou le
// téléphone existent déjà, envoie un code de vérification par email (202) à échanger
// via verifierCode(). Les erreurs 400 portent un message par champ (cf. messageDeValidation).
export async function inscrire(payload: InscriptionPayload): Promise<ResultatInscription> {
  const response = await publicPost('/inscription/', payload);
  const body = await response.json();
  if (response.status === 202) {
    return { type: 'verification', reference: body.reference, emailMasque: body.email_masque };
  }
  return { type: 'creee', apiToken: body.api_token };
}

// POST /api/inscription/verifier/ — échange le code reçu par email contre un NOUVEAU jeton
// (l'ancien est révoqué). Toute erreur de code renvoie 400 {"code": ["..."]}.
export async function verifierCode(reference: string, code: string): Promise<string> {
  const response = await publicPost('/inscription/verifier/', { reference, code });
  const body = await response.json();
  return body.api_token;
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

// GET /api/me/contrat/ — dates et durée du contrat (clients/views.py, MeContratView).
export async function fetchContrat(): Promise<Contrat> {
  const response = await authorizedFetch('/me/contrat/');
  return response.json();
}

// PATCH /api/me/contrat/ — change la date de départ (AAAA-MM-JJ). Le serveur refuse
// une date passée, au-delà de l'horizon autorisé, ou si le contrat a déjà démarré :
// l'erreur (400) porte alors le message à afficher (cf. messageDeValidation).
export async function updateDateDepart(dateISO: string): Promise<Contrat> {
  const response = await authorizedFetch('/me/contrat/', {
    method: 'PATCH',
    body: JSON.stringify({ contract_start_date: dateISO }),
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
