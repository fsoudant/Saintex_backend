import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.saintex.app',
  appName: 'Saintex',
  webDir: 'www',
  plugins: {
    // Les fetch() de la coque web partent du WebView (origine capacitor://localhost) :
    // sans en-têtes CORS côté Django, le navigateur les bloque (erreur « {} » dans la
    // console). CapacitorHttp les fait passer par le réseau natif, qui ignore CORS.
    CapacitorHttp: { enabled: true }
  },
  ios: {
    // Le vrai travail (GPS toutes les 6h, boot, notifications locales hors ligne)
    // est fait par le module natif Swift, hors de cette coque Capacitor.
    // Cf. saintex-spec-technique.md §2 et §5.
    contentInset: 'automatic'
  }
};

export default config;
