// Minimal service worker — enables PWA "Add to Home Screen".
// App requires network access; no offline caching intentional.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", () => self.clients.claim());
self.addEventListener("fetch", e => e.respondWith(fetch(e.request)));
