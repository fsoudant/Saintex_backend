import { fetchPreferences } from '../api';
import { showScreen } from '../router';
import type { Preferences } from '../types';

// Traduction affichage pour subscription_status. Les valeurs exactes du
// champ (modèle Utilisateur côté backend) ne sont pas confirmées à ce
// stade — à ajuster une fois le modèle de contrat stabilisé (cf. spec §6,
// "Points encore ouverts" et mémoire : décision fixe/reconduction en
// attente de validation avec le médecin).
const STATUS_LABELS: Record<string, { label: string; cssClass: string }> = {
  pending: { label: 'En attente de départ', cssClass: 'pending' },
  active: { label: 'Actif', cssClass: 'active' },
  expired: { label: 'Expiré', cssClass: 'expired' },
};

export function initHomeScreen(): void {
  document.getElementById('nav-preferences')?.addEventListener('click', () => showScreen('preferences'));
  document.getElementById('nav-home')?.addEventListener('click', () => showScreen('home'));
}

export async function renderBalanceCard(): Promise<void> {
  const card = document.getElementById('balance-card');
  if (!card) return;

  try {
    const prefs: Preferences = await fetchPreferences();
    const status = STATUS_LABELS[prefs.subscription_status] ?? {
      label: prefs.subscription_status,
      cssClass: '',
    };
    card.className = `card ${status.cssClass}`;
    card.innerHTML = `
      <p class="status-label">Statut de l'abonnement</p>
      <p class="status-value">${status.label}</p>
    `;
  } catch (error) {
    console.error('Impossible de charger le statut :', error);
    card.innerHTML = `<p class="loading">Statut indisponible pour l'instant.</p>`;
  }
}
