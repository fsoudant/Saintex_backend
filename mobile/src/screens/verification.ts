import { inscrire, verifierCode } from '../api';
import { messageErreurInscription, terminerInscription } from '../parcours';
import { showScreen } from '../router';
import type { InscriptionPayload } from '../types';

// Écran de vérification : l'email ou le téléphone saisis correspondent déjà à un
// compte (réinstallation, nouveau téléphone). Le serveur a envoyé un code à six
// chiffres à l'email du compte ; saisi ici, il redonne accès au compte avec un
// nouveau jeton (l'ancien téléphone perd l'accès). Cf. clients/inscription.py.

let reference = '';
let donneesInscription: InscriptionPayload | null = null;

export function ouvrirVerification(ref: string, emailMasque: string, donnees: InscriptionPayload): void {
  reference = ref;
  donneesInscription = donnees;

  const adresse = document.getElementById('verification-email');
  if (adresse) adresse.textContent = emailMasque;
  const champ = document.getElementById('verification-code') as HTMLInputElement | null;
  if (champ) champ.value = '';
  const statut = document.getElementById('verification-status');
  if (statut) statut.textContent = '';
  const valider = document.getElementById('btn-verification-valider') as HTMLButtonElement | null;
  if (valider) valider.disabled = true;

  showScreen('verification');
}

export function initVerificationScreen(): void {
  const champ = document.getElementById('verification-code') as HTMLInputElement | null;
  const valider = document.getElementById('btn-verification-valider') as HTMLButtonElement | null;
  const renvoyer = document.getElementById('btn-verification-renvoyer') as HTMLButtonElement | null;
  const retour = document.getElementById('btn-verification-retour');
  const statut = document.getElementById('verification-status');
  if (!champ || !valider || !renvoyer) return;

  const codeComplet = () => /^\d{6}$/.test(champ.value);
  champ.addEventListener('input', () => {
    // Que des chiffres (les claviers proposent parfois un espace ou un tiret).
    champ.value = champ.value.replace(/\D/g, '').slice(0, 6);
    valider.disabled = !codeComplet();
  });

  valider.addEventListener('click', async () => {
    if (statut) statut.textContent = '';
    valider.disabled = true;
    try {
      const jeton = await verifierCode(reference, champ.value);
      await terminerInscription(jeton);
    } catch (error) {
      console.error('Vérification impossible :', error);
      if (statut) statut.textContent = messageErreurInscription(error, ['code']);
      valider.disabled = !codeComplet();
    }
  });

  renvoyer.addEventListener('click', async () => {
    if (!donneesInscription) return;
    if (statut) statut.textContent = '';
    renvoyer.disabled = true;
    try {
      const resultat = await inscrire(donneesInscription);
      if (resultat.type === 'verification') {
        reference = resultat.reference;
        if (statut) {
          statut.textContent =
            "Un code a été envoyé. S'il n'arrive pas, vérifiez vos courriers indésirables ou patientez une minute avant de redemander.";
        }
      } else {
        await terminerInscription(resultat.apiToken);
      }
    } catch (error) {
      console.error('Renvoi du code impossible :', error);
      if (statut) statut.textContent = messageErreurInscription(error);
    } finally {
      renvoyer.disabled = false;
    }
  });

  retour?.addEventListener('click', () => showScreen('tunnel'));
}
