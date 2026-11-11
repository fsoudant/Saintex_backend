import { inscrire } from '../api';
import { aujourdhuiISO } from '../dates';
import { messageErreurInscription, terminerInscription } from '../parcours';
import { consentementEstDonne } from '../session';
import { showScreen } from '../router';
import { ouvrirVerification } from './verification';
import type { InscriptionPayload, ReminderDelay } from '../types';

// Paiement (spec §6, « Stratégie de paiement » : lien externe plutôt qu'IAP natif pour
// limiter les commissions). Pas encore de page de paiement : pendant la phase pilote,
// l'inscription suffit. À brancher ici (ouvrir le lien avant de terminer le parcours)
// quand la page Stripe existera.
const URL_PAIEMENT: string | null = null;

const CHAMPS_EN_ERREUR = ['email', 'phone', 'contract_start_date', 'contract_duration', 'consent'];

export function initTunnelScreen(): void {
  const continueBtn = document.getElementById('btn-tunnel-continue') as HTMLButtonElement | null;
  const emailInput = document.getElementById('user-email') as HTMLInputElement | null;
  const phoneInput = document.getElementById('user-phone') as HTMLInputElement | null;
  const durationSelect = document.getElementById('contract-duration') as HTMLSelectElement | null;
  const startInput = document.getElementById('contract-start') as HTMLInputElement | null;
  const reminderSelect = document.getElementById('reminder-delay') as HTMLSelectElement | null;
  const emailToggle = document.getElementById('pref-email') as HTMLInputElement | null;
  const pushToggle = document.getElementById('pref-push') as HTMLInputElement | null;
  const status = document.getElementById('tunnel-status');

  if (!continueBtn || !emailInput || !phoneInput || !durationSelect || !startInput || !reminderSelect) {
    return;
  }

  // Un voyage se prépare à l'avance : la date de départ est choisie ici (par
  // défaut aujourd'hui) et le contrat démarre ce jour-là (spec §6). Le serveur fait
  // foi sur les bornes (pas dans le passé, horizon maximal) : on ne duplique pas
  // l'horizon ici, on affiche son message s'il refuse la date.
  startInput.min = aujourdhuiISO();
  startInput.value = aujourdhuiISO();

  const validate = () => {
    const emailValid = emailInput.value.includes('@');
    const phoneValid = phoneInput.value.trim().length >= 6;
    const startValid = startInput.value !== '' && startInput.value >= aujourdhuiISO();
    continueBtn.disabled = !(emailValid && phoneValid && startValid);
  };

  emailInput.addEventListener('input', validate);
  phoneInput.addEventListener('input', validate);
  startInput.addEventListener('input', validate);
  validate();

  continueBtn.addEventListener('click', async () => {
    if (status) status.textContent = '';

    // Garde-fou : le tunnel n'est atteignable qu'après l'écran de consentement ;
    // sans lui, le serveur refuserait de toute façon l'inscription.
    if (!consentementEstDonne()) {
      showScreen('onboarding');
      return;
    }

    const payload: InscriptionPayload = {
      email: emailInput.value.trim(),
      phone: phoneInput.value.trim(),
      email_active: emailToggle?.checked ?? true,
      push_active: pushToggle?.checked ?? true,
      reminder_delay: reminderSelect.value as ReminderDelay,
      contract_start_date: startInput.value,
      contract_duration: Number(durationSelect.value),
      consent: true,
    };

    continueBtn.disabled = true;
    try {
      const resultat = await inscrire(payload);
      if (resultat.type === 'verification') {
        // Un compte existe déjà avec cet email ou ce téléphone : un code a été envoyé
        // à l'email du compte, à saisir sur l'écran suivant.
        ouvrirVerification(resultat.reference, resultat.emailMasque, payload);
        return;
      }
      if (URL_PAIEMENT) window.open(URL_PAIEMENT, '_blank');
      await terminerInscription(resultat.apiToken);
    } catch (error) {
      console.error("Inscription impossible :", error);
      if (status) status.textContent = messageErreurInscription(error, CHAMPS_EN_ERREUR);
    } finally {
      validate();
    }
  });
}
