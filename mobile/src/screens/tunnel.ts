import { markOnboardingDone } from '../storage';
import { showScreen } from '../router';
import type { Country, OnboardingPayload, ReminderDelay } from '../types';

// TODO: remplacer par un appel à /api/pays/ dès que cet endpoint existe
// côté backend (cf. api.ts, fetchAvailableCountries). Liste volontairement
// courte et arbitraire pour permettre de tester l'écran en attendant.
const PLACEHOLDER_COUNTRIES: Country[] = [
  { code: 'TH', name: 'Thaïlande' },
  { code: 'KE', name: 'Kenya' },
  { code: 'BR', name: 'Brésil' },
  { code: 'IN', name: 'Inde' },
  { code: 'ID', name: 'Indonésie' },
  { code: 'PE', name: 'Pérou' },
];

// URL de paiement externe (spec §6, "Stratégie de paiement" : lien externe
// plutôt qu'IAP natif pour limiter les commissions). Placeholder — à
// remplacer par la vraie page de paiement Stripe une fois créée.
const PLACEHOLDER_PAYMENT_URL = 'https://pay.saintex.example/checkout';

export function initTunnelScreen(): void {
  const countryList = document.getElementById('country-list');
  const continueBtn = document.getElementById('btn-tunnel-continue') as HTMLButtonElement | null;
  const emailInput = document.getElementById('user-email') as HTMLInputElement | null;
  const phoneInput = document.getElementById('user-phone') as HTMLInputElement | null;
  const durationSelect = document.getElementById('contract-duration') as HTMLSelectElement | null;
  const reminderSelect = document.getElementById('reminder-delay') as HTMLSelectElement | null;
  const emailToggle = document.getElementById('pref-email') as HTMLInputElement | null;
  const pushToggle = document.getElementById('pref-push') as HTMLInputElement | null;

  if (!countryList || !continueBtn || !emailInput || !phoneInput || !durationSelect || !reminderSelect) {
    return;
  }

  for (const country of PLACEHOLDER_COUNTRIES) {
    const label = document.createElement('label');
    label.className = 'consent-row';
    label.innerHTML = `<input type="checkbox" value="${country.code}" /><span>${country.name}</span>`;
    countryList.appendChild(label);
  }

  const validate = () => {
    const anyCountryChecked = countryList.querySelectorAll('input:checked').length > 0;
    const emailValid = emailInput.value.includes('@');
    const phoneValid = phoneInput.value.trim().length >= 6;
    continueBtn.disabled = !(anyCountryChecked && emailValid && phoneValid);
  };

  countryList.addEventListener('change', validate);
  emailInput.addEventListener('input', validate);
  phoneInput.addEventListener('input', validate);

  continueBtn.addEventListener('click', async () => {
    const selectedCountryCodes = Array.from(
      countryList.querySelectorAll('input:checked')
    ).map((el) => (el as HTMLInputElement).value);

    const payload: OnboardingPayload = {
      contract_duration_months: Number(durationSelect.value),
      selected_country_codes: selectedCountryCodes,
      email: emailInput.value,
      phone: phoneInput.value,
      email_active: emailToggle?.checked ?? true,
      push_active: pushToggle?.checked ?? true,
      reminder_delay: reminderSelect.value as ReminderDelay,
    };

    // TODO: pas d'endpoint d'inscription réel côté backend pour l'instant
    // (cf. api.ts, submitOnboarding) : on ne peut donc pas encore obtenir de
    // jeton API ici. On simule le passage pour pouvoir tester la suite du
    // parcours ; le déclenchement natif GPS (spec §6 étape 6) n'est PAS
    // câblé tant que ce point n'est pas résolu.
    console.warn('Onboarding non persisté côté serveur (endpoint manquant) :', payload);

    window.open(PLACEHOLDER_PAYMENT_URL, '_blank');

    await markOnboardingDone();
    showScreen('home');
  });
}
