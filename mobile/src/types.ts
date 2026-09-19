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
