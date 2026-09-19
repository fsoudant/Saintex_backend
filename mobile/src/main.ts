import { isOnboardingDone } from './storage';
import { showScreen } from './router';
import { initOnboardingScreen } from './screens/onboarding';
import { initTunnelScreen } from './screens/tunnel';
import { initHomeScreen, renderBalanceCard } from './screens/home';
import { initPreferencesScreen, loadPreferencesIntoForm } from './screens/preferences';

// Point d'entrée de la coque Capacitor. Ne fait QUE de l'UI : le vrai
// travail (polling GPS 6h, démarrage au boot, notification locale hors
// ligne — spec §2/§4/§5) est du ressort du module natif Swift, pas de ce
// fichier. Cf. saintex-spec-technique.md pour la répartition des rôles.
async function bootstrap(): Promise<void> {
  initOnboardingScreen();
  initTunnelScreen();
  initHomeScreen();
  initPreferencesScreen();

  const alreadyOnboarded = await isOnboardingDone();
  if (alreadyOnboarded) {
    showScreen('home');
    await renderBalanceCard();
    await loadPreferencesIntoForm();
  } else {
    showScreen('onboarding');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  bootstrap().catch((error) => console.error('Erreur au démarrage de l\'app :', error));
});
