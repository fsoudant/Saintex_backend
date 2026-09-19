import { fetchPreferences, updatePreferences } from '../api';
import { showScreen } from '../router';
import type { ReminderDelay } from '../types';

// Écran préférences (spec §7 : email_active, push_active, reminder_delay
// modifiables par l'utilisateur ; SMS non désactivable, affiché coché/
// grisé). Chaque PATCH est journalisé côté serveur dans PreferenceChangeLog
// (clients/views.py, MePreferencesView.patch) — rien à faire de plus ici.
export function initPreferencesScreen(): void {
  document.getElementById('nav-home-2')?.addEventListener('click', () => showScreen('home'));
  document.getElementById('nav-preferences-2')?.addEventListener('click', () => showScreen('preferences'));

  const saveBtn = document.getElementById('btn-preferences-save');
  const statusEl = document.getElementById('preferences-status');
  const emailToggle = document.getElementById('settings-pref-email') as HTMLInputElement | null;
  const pushToggle = document.getElementById('settings-pref-push') as HTMLInputElement | null;
  const reminderSelect = document.getElementById('settings-reminder-delay') as HTMLSelectElement | null;

  saveBtn?.addEventListener('click', async () => {
    if (!emailToggle || !pushToggle || !reminderSelect || !statusEl) return;
    statusEl.textContent = 'Enregistrement…';
    try {
      await updatePreferences({
        email_active: emailToggle.checked,
        push_active: pushToggle.checked,
        reminder_delay: reminderSelect.value as ReminderDelay,
      });
      statusEl.textContent = 'Préférences enregistrées.';
    } catch (error) {
      console.error('Échec de la mise à jour des préférences :', error);
      statusEl.textContent = "Échec de l'enregistrement, réessaie plus tard.";
    }
  });
}

export async function loadPreferencesIntoForm(): Promise<void> {
  const emailToggle = document.getElementById('settings-pref-email') as HTMLInputElement | null;
  const pushToggle = document.getElementById('settings-pref-push') as HTMLInputElement | null;
  const reminderSelect = document.getElementById('settings-reminder-delay') as HTMLSelectElement | null;
  if (!emailToggle || !pushToggle || !reminderSelect) return;

  try {
    const prefs = await fetchPreferences();
    emailToggle.checked = prefs.email_active;
    pushToggle.checked = prefs.push_active;
    reminderSelect.value = prefs.reminder_delay;
  } catch (error) {
    console.error('Impossible de charger les préférences :', error);
  }
}
