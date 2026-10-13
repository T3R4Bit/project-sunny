// Minimal service worker: makes the PWA installable and keeps the app shell available offline.
// API calls always go to the network; only same-origin GETs for the shell and built assets are cached.
const CACHE = 'sunny-shell-v2';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(['/', '/manifest.json'])));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  const isShell = url.pathname === '/' || url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icon-');
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !isShell) return;

  // Network first so deploys show up immediately; fall back to cache when offline.
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
