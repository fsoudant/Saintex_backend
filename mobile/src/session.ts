// État du parcours de premier lancement, gardé en mémoire : le consentement RGPD
// est donné sur le premier écran et transmis avec l'inscription (le serveur
// l'horodate). Il n'est volontairement pas persisté sur le téléphone avant
// l'inscription : si l'app est fermée en cours de tunnel, le voyageur repasse par
// l'écran de consentement.
let consentementDonne = false;

export function enregistrerConsentement(): void {
  consentementDonne = true;
}

export function consentementEstDonne(): boolean {
  return consentementDonne;
}
