import { fetchContrat, messageDeValidation, updateDateDepart } from '../api';
import { aujourdhuiISO, departAtteint, formaterDate } from '../dates';
import { showScreen } from '../router';
import type { Contrat } from '../types';

// Valeurs de Utilisateur.subscription_status (clients/models.py, StatutAbonnement) :
// trial, active, expired, cancelled.
const STATUS_LABELS: Record<string, { label: string; cssClass: string }> = {
  trial: { label: "Période d'essai", cssClass: 'pending' },
  active: { label: 'Actif', cssClass: 'active' },
  expired: { label: 'Expiré', cssClass: 'expired' },
  cancelled: { label: 'Annulé', cssClass: 'expired' },
};

function echapper(texte: string): string {
  return texte.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function initHomeScreen(): void {
  document.getElementById('nav-preferences')?.addEventListener('click', () => showScreen('preferences'));
  document.getElementById('nav-home')?.addEventListener('click', () => showScreen('home'));

  const bouton = document.getElementById('btn-home-start-save');
  const champ = document.getElementById('home-start') as HTMLInputElement | null;
  const statut = document.getElementById('home-start-status');
  if (!bouton || !champ) return;

  bouton.addEventListener('click', async () => {
    if (statut) statut.textContent = '';
    if (!champ.value) {
      if (statut) statut.textContent = 'Choisissez une date de départ.';
      return;
    }
    try {
      await updateDateDepart(champ.value);
      await renderBalanceCard();
    } catch (error) {
      if (statut) {
        statut.textContent =
          messageDeValidation(error, 'contract_start_date') ?? 'Impossible de modifier la date pour le moment.';
      }
    }
  });
}

function ligne(libelle: string, valeur: string): string {
  return `<p class="status-label">${libelle}</p><p class="status-detail">${echapper(valeur)}</p>`;
}

// Carte « Mon voyage » : statut du contrat, date de départ et fin. La date de
// départ n'est modifiable que tant qu'elle n'est pas atteinte (le serveur le
// refuse ensuite : clients.models.valider_date_debut_contrat).
export async function renderBalanceCard(): Promise<void> {
  const card = document.getElementById('balance-card');
  const edition = document.getElementById('departure-edit');
  const champ = document.getElementById('home-start') as HTMLInputElement | null;
  if (!card) return;

  try {
    const contrat: Contrat = await fetchContrat();
    const status = STATUS_LABELS[contrat.subscription_status] ?? {
      label: contrat.subscription_status,
      cssClass: '',
    };

    let detail = '';
    if (contrat.contract_start_date) {
      const depart = formaterDate(contrat.contract_start_date);
      detail += ligne(departAtteint(contrat.contract_start_date) ? 'Départ' : 'Départ prévu', depart);
      if (contrat.contract_expiry_date) {
        detail += ligne('Fin du contrat', formaterDate(contrat.contract_expiry_date));
      }
    } else {
      detail += ligne('Départ', 'Date non choisie');
    }

    card.className = `card ${status.cssClass}`;
    card.innerHTML = `
      <p class="status-label">Statut de l'abonnement</p>
      <p class="status-value">${echapper(status.label)}</p>
      ${detail}
    `;

    // Modification possible tant que le voyage n'a pas commencé.
    const modifiable = !departAtteint(contrat.contract_start_date);
    edition?.classList.toggle('hidden', !modifiable);
    if (modifiable && champ) {
      champ.min = aujourdhuiISO();
      champ.value = contrat.contract_start_date ?? aujourdhuiISO();
    }
  } catch (error) {
    console.error('Impossible de charger le contrat :', error);
    card.innerHTML = `<p class="loading">Statut indisponible pour l'instant.</p>`;
    edition?.classList.add('hidden');
  }
}
