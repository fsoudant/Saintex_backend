import { setApiToken, markOnboardingDone } from './storage';

// PROTOTYPE d'essai du module natif (cf. index.html, bloc « Outils d'essai »).
// Enregistre à la main le jeton API d'un utilisateur créé dans l'admin : le
// module natif Swift le lit dans la même clé (UserDefaults, préfixe
// "CapacitorStorage.") et déclenche un contact avec le serveur dès qu'il le
// voit apparaître. À RETIRER quand l'inscription réelle existera.
export function initDebugTools(): void {
  const input = document.getElementById('debug-token') as HTMLInputElement | null;
  const bouton = document.getElementById('btn-debug-token');
  const statut = document.getElementById('debug-token-status');
  if (!input || !bouton || !statut) return;

  bouton.addEventListener('click', async () => {
    const jeton = input.value.trim();
    if (!jeton) {
      statut.textContent = 'Jeton vide.';
      return;
    }
    await setApiToken(jeton);
    await markOnboardingDone();
    input.value = '';
    statut.textContent = 'Jeton enregistré. Le module natif contacte le serveur.';
  });
}
