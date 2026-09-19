import { Preferences as CapPreferences } from '@capacitor/preferences';

// Stockage local minimal : jeton API et flag "onboarding terminé".
// Le module natif (Swift) lit lui aussi la clé API_TOKEN_KEY via son propre
// accès au trousseau/UserDefaults partagé — à aligner avec lui plutôt que de
// dupliquer un mécanisme de stockage séparé (cf. spec §6 étape 6 : le
// processus natif est déclenché juste après le paiement et doit connaître
// le jeton pour s'authentifier lors du polling GPS).
const API_TOKEN_KEY = 'saintex_api_token';
const ONBOARDING_DONE_KEY = 'saintex_onboarding_done';

export async function getApiToken(): Promise<string | null> {
  const { value } = await CapPreferences.get({ key: API_TOKEN_KEY });
  return value;
}

export async function setApiToken(token: string): Promise<void> {
  await CapPreferences.set({ key: API_TOKEN_KEY, value: token });
}

export async function clearApiToken(): Promise<void> {
  await CapPreferences.remove({ key: API_TOKEN_KEY });
}

export async function isOnboardingDone(): Promise<boolean> {
  const { value } = await CapPreferences.get({ key: ONBOARDING_DONE_KEY });
  return value === 'true';
}

export async function markOnboardingDone(): Promise<void> {
  await CapPreferences.set({ key: ONBOARDING_DONE_KEY, value: 'true' });
}
