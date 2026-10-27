// Reflète UtilisateurPreferencesSerializer côté backend (clients/serializers.py).
// Champs SMS volontairement absents : jamais désactivable (spec §8).
export interface Preferences {
  email: string;
  phone: string;
  email_active: boolean;
  push_active: boolean;
  reminder_delay: ReminderDelay;
  subscription_status: string;
}

export type ReminderDelay = 'once' | 'daily' | 'every_2_days' | 'weekly';

// Champs modifiables par l'utilisateur uniquement (email/phone en lecture
// seule côté API, cf. read_only_fields du serializer).
export type PreferencesUpdate = Partial<
  Pick<Preferences, 'email_active' | 'push_active' | 'reminder_delay'>
>;

// --- Contact avec le serveur (POST /api/cache/, spec §4 et §5) -------------
// Reflète CacheView (clients/views.py) et risks/cache.py côté backend. Aucune
// position n'est transmise : le cache est mondial, identique pour tous.

export type TypeAlerte = 'entree' | 'rappel';

// Une alerte ou un rappel affiché par le téléphone, à remonter au serveur.
// `id` est généré par le téléphone (UUID) : le même rapport peut être renvoyé
// sans doublon. Aucune coordonnée.
export interface RapportAlerte {
  id: string;
  endemie: number; // identifiant fourni par le cache
  type: TypeAlerte;
  affichee_le: string; // ISO 8601, horloge du téléphone
  ouverte_le?: string | null;
  cache_version?: string;
}

export interface SanteAppli {
  localisation_toujours: boolean;
  notifications_autorisees: boolean;
}

// Tous les champs sont facultatifs.
export interface ContactRequest {
  cache_version?: string; // version du cache détenu
  sante?: SanteAppli;
  rapports?: RapportAlerte[]; // 100 au plus par contact
}

export interface ContratInfo {
  debut: string | null; // date ISO
  expiration: string | null;
}

// GeoJSON MultiPolygon, coordonnées [lon, lat] ; zones à cheval sur
// l'antiméridien découpées en deux parties collées à ±180°.
export interface GeometrieCache {
  type: 'MultiPolygon';
  coordinates: number[][][][];
}

export interface ConduiteCache {
  risque: { code: string; libelle_fr: string; libelle_en: string; couleur: string | null };
  saison: { debut: number; fin: number } | null; // mois 1-12, peut chevaucher le nouvel an
  recommandation_fr: string; // HTML assaini
  recommandation_en: string;
}

export interface EndemieCache {
  id: number;
  zone_id: number;
  zone_nom: string;
  conduite: string; // clé de `conduites`
  geometrie: string; // clé de `geometries` (géométrie effective : zone moins zone exclue)
  valide_du: string | null;
  valide_au: string | null;
}

export interface CacheMondial {
  version: string;
  genere_le: string;
  rayon_km: number | null; // null = monde entier
  conduites: Record<string, ConduiteCache>;
  geometries: Record<string, GeometrieCache>;
  endemies: EndemieCache[];
}

// Réponse « inchangé » quand `cache_version` envoyée est déjà la version courante.
export interface CacheInchange {
  version: string;
  inchange: true;
}

export interface ContactResponse {
  contrat: ContratInfo; // le téléphone reste muet avant `debut` et dès `expiration`
  cache: CacheMondial | CacheInchange;
  rapports_recus: string[]; // identifiants acquittés : à retirer de la file d'attente
}

export interface Country {
  code: string;
  name: string;
}

// Données saisies pendant le tunnel de premier lancement (spec §6).
// NB: il n'existe pas encore d'endpoint d'inscription côté backend
// (cf. clients/views.py, docstring du module) — cette forme est une
// anticipation à confirmer une fois l'endpoint défini.
export interface OnboardingPayload {
  contract_duration_months: number;
  selected_country_codes: string[];
  email: string;
  phone: string;
  email_active: boolean;
  push_active: boolean;
  reminder_delay: ReminderDelay;
}
