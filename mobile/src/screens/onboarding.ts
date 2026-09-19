import { showScreen } from '../router';

// Écran 1 : consentement RGPD (spec §7 : "consentement explicite au premier
// lancement"). Le bouton Continuer reste désactivé tant que la case n'est
// pas cochée — pas de contournement possible.
export function initOnboardingScreen(): void {
  const checkbox = document.getElementById('consent-checkbox') as HTMLInputElement | null;
  const continueBtn = document.getElementById('btn-onboarding-continue') as HTMLButtonElement | null;
  if (!checkbox || !continueBtn) return;

  checkbox.addEventListener('change', () => {
    continueBtn.disabled = !checkbox.checked;
  });

  continueBtn.addEventListener('click', () => {
    if (!checkbox.checked) return;
    // TODO: horodater et transmettre consent_date/consent_status au backend
    // dès qu'un endpoint d'inscription existe (cf. api.ts, submitOnboarding).
    showScreen('tunnel');
  });
}
