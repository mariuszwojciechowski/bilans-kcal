/* Kill switch starego service workera Fit Krasnala (dawny klient PWA w docs/).
   Przeglądarka sprawdza sw.js przy każdym otwarciu zainstalowanej aplikacji
   i porównuje bajty — więc ten plik zastąpi tamten, skasuje jego cache
   i wyrejestruje się sam. Efekt: zainstalowana stara wersja przestaje działać
   offline i przy następnym otwarciu ląduje na docs/index.html, który sprząta
   dane i przekierowuje na fit.krasnal.cc/mobile.

   NIE dopisuj tu obsługi fetch ani cache'owania — patrz komentarz
   w docs/index.html. */

self.addEventListener("install", function () {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(keys.map(function (k) { return caches.delete(k); }));
      })
      .catch(function () {})
      .then(function () { return self.registration.unregister(); })
      .then(function () { return self.clients.matchAll({ type: "window" }); })
      .then(function (clients) {
        clients.forEach(function (c) { c.navigate(c.url); });
      })
      .catch(function () {})
  );
});
