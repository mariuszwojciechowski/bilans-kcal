import type { CapacitorConfig } from '@capacitor/cli';

// URL zdalnej aplikacji. Produkcja domyślnie; do testów w LAN:
//   FIT_KRASNAL_APP_URL=http://192.168.1.10:8000 npx cap sync android
const appUrl = process.env.FIT_KRASNAL_APP_URL || 'https://fit.krasnal.cc';
const appHost = new URL(appUrl).host;
const isHttp = appUrl.startsWith('http://');

const config: CapacitorConfig = {
  appId: 'cc.krasnal.fit',
  appName: 'Fit Krasnal',
  webDir: 'www',
  server: {
    url: appUrl,
    // Logowanie Google (OIDC) ma się odbyć w WebView: bez tego wpisu Capacitor
    // wyrzuca accounts.google.com do zewnętrznej przeglądarki (ACTION_VIEW)
    // i sesja ląduje w Chrome, nie w aplikacji.
    allowNavigation: [appHost, 'accounts.google.com'],
    androidScheme: 'https',
    cleartext: isHttp,
  },
  android: {
    allowMixedContent: isHttp,
    // Marker w UA: strona wykrywa powłokę nawet gdy most nie został wstrzyknięty
    // (nawigacja po POST, np. logowanie) i przeładowuje się przez GET.
    appendUserAgent: 'FitKrasnalApp/1',
  },
  plugins: {
    StatusBar: {
      overlaysWebView: false,
      style: 'LIGHT',
      backgroundColor: '#ffffff',
    },
  },
};

export default config;
