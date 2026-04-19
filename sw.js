// VITALIS COORDIS — Service Worker v9
// v9: Removed iframe-break (CSP-blocked), pre-set vtl_onboarded to skip onboarding re-trigger,
//     ensuring direct boot to app shell on every load.
// IP: All IP held by Avotombo Legacy Trust. All rights reserved.

const CACHE_NAME = 'vitalis-v9';

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

  if (request.method !== 'GET') return;
  if (!url.protocol.startsWith('http')) return;

  const isCDN = CDN_ORIGINS.some(o => request.url.startsWith(o));

  if (isCDN) {
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
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res.ok) {
            caches.open(CACHE_NAME).then(cache => cache.put(request, res.clone()));
          }
          return res;
        }).catch(() => {
          if (request.mode === 'navigate') {
            return caches.match('./index.html');
          }
        });
      })
    );
  }
});

// ── Push notification display ─────────────────────────────────────────────────
// Receives push events from the main thread via self.registration.showNotification()
// or from a push server (future). Currently driven by main-thread scheduler.
self.addEventListener('push', (event) => {
  let data = { title: 'Vitalis Coordis', body: 'Time for your protocol stack.', phase: 'am' };
  try { data = event.data ? event.data.json() : data; } catch {}
  event.waitUntil(showReminderNotification(data));
});

// ── Notification click → deep-link to Stack tab ───────────────────────────────
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const phase = event.notification.data?.phase ?? 'am';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (clientList) => {
      // Find an existing app window and focus it, passing the phase
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) || client.url.includes('vitalis')) {
          client.focus();
          client.postMessage({ type: 'REMINDER_DEEP_LINK', phase });
          return;
        }
      }
      // No existing window — open a new one
      const win = await clients.openWindow('./?reminder=' + phase);
      if (win) {
        // Small delay to let the page load before posting message
        setTimeout(() => {
          win.postMessage({ type: 'REMINDER_DEEP_LINK', phase });
        }, 1500);
      }
    })
  );
});

// ── Message handler from main thread ─────────────────────────────────────────
// Main thread calls: navigator.serviceWorker.controller.postMessage({ type: 'SHOW_REMINDER', ... })
self.addEventListener('message', (event) => {
  const msg = event.data;
  if (!msg || !msg.type) return;

  if (msg.type === 'SHOW_REMINDER') {
    // Direct trigger from main thread scheduler — show the notification now
    event.waitUntil(showReminderNotification({
      title: msg.title || 'Vitalis Coordis',
      body: msg.body || 'Time for your protocol stack.',
      phase: msg.phase || 'am',
    }));
  }
});

// ── Helper: show a notification ───────────────────────────────────────────────
async function showReminderNotification({ title, body, phase }) {
  const phaseColors = { am: '#38bdf8', mid: '#c084fc', pm: '#34d399' };
  const color = phaseColors[phase] ?? '#00e5cc';

  return self.registration.showNotification(title, {
    body,
    icon: './icons/icon-192.png',
    badge: './icons/badge-96.png',
    tag: 'vitalis-reminder-' + phase,   // replaces previous notification for same phase
    renotify: true,
    vibrate: [200, 100, 200],
    data: { phase, ts: Date.now() },
    actions: [
      { action: 'open-stack', title: 'View Stack' },
      { action: 'dismiss',    title: 'Dismiss'     },
    ],
  });
}
