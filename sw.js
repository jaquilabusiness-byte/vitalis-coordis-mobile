// VITALIS COORDIS — Service Worker
// Strategy: Cache-first for all app shell assets, network-first for fonts/CDN.
// All localStorage (sync state, intake logs) works natively offline — no extra handling needed.

const CACHE_NAME = 'vitalis-mobile-v13';

// App shell — everything needed to run offline
const SHELL = [
  './',
  './index.html',
];

// External CDN assets to cache on first use (runtime caching)
const CDN_ORIGINS = [
  'https://fonts.googleapis.com',
  'https://fonts.gstatic.com',
];

// ── Install: pre-cache app shell ─────────────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

// ── Activate: clean up old caches ────────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: cache-first for shell, stale-while-revalidate for CDN ─────────────
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET and browser-extension requests
  if (request.method !== 'GET') return;
  if (!url.protocol.startsWith('http')) return;

  const isCDN = CDN_ORIGINS.some(o => request.url.startsWith(o));

  if (isCDN) {
    // Stale-while-revalidate for fonts/external resources
    event.respondWith(
      caches.open(CACHE_NAME).then(async cache => {
        const cached = await cache.match(request);
        const networkFetch = fetch(request).then(res => {
          if (res.ok) cache.put(request, res.clone());
          return res;
        }).catch(() => cached);
        return cached || networkFetch;
      })
    );
  } else {
    // Cache-first for everything else (app shell)
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res.ok) {
            caches.open(CACHE_NAME).then(cache => cache.put(request, res.clone()));
          }
          return res;
        }).catch(() => {
          // Offline fallback: serve index.html for navigation requests
          if (request.mode === 'navigate') {
            return caches.match('./index.html');
          }
        });
      })
    );
  }
});
