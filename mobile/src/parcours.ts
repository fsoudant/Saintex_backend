import { ApiError, messageDeValidation, messageDetail } from './api';
import { markOnboardingDone, setApiToken } from './storage';
import { showScreen } from './router';
import { renderBalanceCard } from './screens/home';
import { loadPreferencesIntoForm } from './screens/preferences';

// Fin du parcours de premier lancement : le jeton remis par le serveur (compte créé,
// ou récupéré par code de vérification) est enregistré ; le module natif Swift le lit
// dans la même clé (UserDefaults) et contacte aussitôt le serveur (spec §6, étape 6),
// puis le voyageur arrive sur l'accueil.
export async function terminerInscription(apiToken: string): Promise<void> {
  await setApiToken(apiToken);
  await markOnboardingDone();
  showScreen('home');
  await Promise.all([renderBalanceCard(), loadPreferencesIntoForm()]);
}

// Message à afficher pour une erreur de l'API d'inscription : le texte du serveur pour
// le premier des `champs` en erreur, un message générique sinon.
export function messageErreurInscription(erreur: unknown, champs: string[] = []): string {
  if (erreur instanceof ApiError) {
    if (erreur.status === 429) return 'Trop de tentatives. Réessayez dans quelques minutes.';
    for (const champ of champs) {
      const message = messageDeValidation(erreur, champ);
      if (message) return message;
    }
    if (erreur.status === 400) return 'Certaines informations sont invalides.';
    const detail = messageDetail(erreur);
    if (detail) return detail;
  }
  return 'Le serveur est injoignable pour le moment, réessayez.';
}
