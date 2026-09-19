export type ScreenId = 'onboarding' | 'tunnel' | 'home' | 'preferences';

const SCREEN_ELEMENT_IDS: Record<ScreenId, string> = {
  onboarding: 'screen-onboarding',
  tunnel: 'screen-tunnel',
  home: 'screen-home',
  preferences: 'screen-preferences',
};

// Volontairement minimaliste : quatre écrans fixes, pas d'historique de
// navigation ni de paramètres d'URL. La coque UI reste fine (spec §2/§3),
// pas besoin d'un routeur complet pour ça.
export function showScreen(screen: ScreenId): void {
  for (const [id, elementId] of Object.entries(SCREEN_ELEMENT_IDS) as [ScreenId, string][]) {
    const el = document.getElementById(elementId);
    if (!el) continue;
    el.classList.toggle('hidden', id !== screen);
  }
}
