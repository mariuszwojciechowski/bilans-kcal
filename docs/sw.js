/* Service worker Fit Krasnal — offline dla PWA.
   Strona (nawigacja): najpierw sieć (świeże aktualizacje), fallback cache (offline).
   Assety: cache-first. Przy zmianie index.html podbij wersję CACHE. */
const CACHE = "fitkrasnal-v11";
const ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./logo.png",
                "./krasnal-icon.png",
                "./icon-192.png", "./icon-512.png", "./apple-touch-icon.png",
                "./icon-maskable-192.png", "./icon-maskable-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return; // Gemini idzie po sieci
  if (e.request.mode === "navigate") {
    // no-cache: rewalidacja z serwerem (GitHub Pages ma Cache-Control 10 min,
    // bez tego świeży deploy bywałby widoczny z opóźnieniem)
    e.respondWith(
      fetch(e.request.url, { cache: "no-cache" })
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put("./index.html", copy));
          return resp;
        })
        .catch(() => caches.match("./index.html"))
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((resp) => {
      const copy = resp.clone();
      caches.open(CACHE).then((c) => c.put(e.request, copy));
      return resp;
    }))
  );
});
