import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.saintex.app',
  appName: 'Saintex',
  webDir: 'www',
  ios: {
    // Le vrai travail (GPS toutes les 6h, boot, notifications locales hors ligne)
    // est fait par le module natif Swift, hors de cette coque Capacitor.
    // Cf. saintex-spec-technique.md §2 et §5.
    contentInset: 'automatic'
  }
};

export default config;
