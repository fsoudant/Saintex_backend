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

// Format 2 du cache (risks/cache.py, octobre 2026) : une recommandation UNIQUE
// par risque, et une phrase de modulation facultative par endémie.
export interface RisqueCache {
  libelle_fr: string;
  libelle_en: string;
  couleur: string | null;
  alerte_fr: string; // phrase d'alerte toute faite (élision incluse)
  alerte_en: string;
  description_fr: string; // HTML assaini
  description_en: string;
  recommandation_fr: string; // HTML assaini, peut être vide
  recommandation_en: string;
}

export interface ModulationCache {
  fr: string;
  en: string;
  saison: { debut: number; fin: number } | null; // mois 1-12, peut chevaucher le nouvel an
}

export interface EndemieCache {
  id: number;
  zone_id: number;
  zone_nom: string;
  risque: string; // clé de `risques`
  modulation: string | null; // clé de `modulations` ; null = sans précision, toute l'année
  geometrie: string; // clé de `geometries` (géométrie effective : zone moins zone exclue)
  valide_du: string | null;
  valide_au: string | null;
}

export interface CacheMondial {
  version: string;
  genere_le: string;
  format: 2;
  rayon_km: number | null; // null = monde entier
  risques: Record<string, RisqueCache>;
  modulations: Record<string, ModulationCache>;
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

// Inscription (POST /api/inscription/, clients/views.py InscriptionView) : données
// saisies pendant le tunnel de premier lancement (spec §6). Pas de choix de
// pays : le contrat démarre à la date de départ choisie par le voyageur.
// `consent` doit être vrai (consentement RGPD de l'écran d'accueil).
export interface InscriptionPayload {
  email: string;
  phone: string; // format international, ex. +33612345678
  email_active: boolean;
  push_active: boolean;
  reminder_delay: ReminderDelay;
  contract_start_date: string; // AAAA-MM-JJ
  contract_duration: number; // en mois
  consent: true;
}

// Compte créé (201) : le jeton est remis aussitôt. Compte existant (202) : un code a
// été envoyé par email, à échanger contre le jeton avec la `reference`.
export type ResultatInscription =
  | { type: 'creee'; apiToken: string }
  | { type: 'verification'; reference: string; emailMasque: string };

// GET/PATCH /api/me/contrat/ — reflète UtilisateurContratSerializer
// (clients/serializers.py). Seule `contract_start_date` est modifiable, et
// seulement tant que le contrat n'a pas démarré.
export interface Contrat {
  contract_duration: number | null; // en mois
  purchased_at: string | null;
  contract_start_date: string | null; // AAAA-MM-JJ
  contract_expiry_date: string | null;
  horizon_max_mois: number;
  subscription_status: string; // trial | active | expired | cancelled
}
