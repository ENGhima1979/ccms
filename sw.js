// CCMS Service Worker v4.0 — PWA Level 3
const CACHE    = 'ccms-v4';
const API_CACHE= 'ccms-api-v4';
const OFFLINE  = '/offline';

const STATIC = [
  '/', '/offline', '/static/manifest.json',
  '/static/icons/icon-192.png', '/static/icons/icon-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js',
];

// Install — cache statics
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(STATIC).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// Activate — clean old caches
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys
        .filter(k => k !== CACHE && k !== API_CACHE)
        .map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch — Network first for API, Cache first for assets
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Skip non-GET
  if (e.request.method !== 'GET') return;

  // API calls — network first, cache fallback (5min TTL)
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(API_CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Static assets — cache first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.match(e.request).then(c => c || fetch(e.request)
        .then(res => {
          caches.open(CACHE).then(c2 => c2.put(e.request, res.clone()));
          return res;
        }))
    );
    return;
  }

  // Navigation — network first, offline fallback
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(OFFLINE))
    );
    return;
  }
});

// Push Notifications
self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  e.waitUntil(
    self.registration.showNotification(data.title || 'CCMS', {
      body:    data.body  || 'لديك إشعار جديد',
      icon:    '/static/icons/icon-192.png',
      badge:   '/static/icons/icon-72.png',
      tag:     data.tag   || 'ccms-notification',
      data:    { url: data.url || '/' },
      dir:     'rtl',
      lang:    'ar',
      vibrate: [200, 100, 200],
      actions: data.actions || [
        { action: 'view',    title: 'عرض' },
        { action: 'dismiss', title: 'تجاهل' }
      ]
    })
  );
});

// Notification click
self.addEventListener('notificationclick', e => {
  e.notification.close();
  if (e.action === 'dismiss') return;
  const url = e.notification.data?.url || '/';
  e.waitUntil(
    clients.matchAll({ type:'window', includeUncontrolled:true }).then(list => {
      const existing = list.find(c => c.url.includes(self.location.origin));
      if (existing) { existing.focus(); existing.navigate(url); }
      else clients.openWindow(url);
    })
  );
});

// Background Sync — queue failed POST requests
self.addEventListener('sync', e => {
  if (e.tag === 'sync-correspondence') {
    e.waitUntil(syncPendingRequests());
  }
});

async function syncPendingRequests() {
  // Retry any queued correspondence submissions
  const cache = await caches.open('ccms-sync-queue');
  const keys  = await cache.keys();
  await Promise.all(keys.map(async req => {
    try {
      await fetch(req);
      await cache.delete(req);
    } catch {}
  }));
}
