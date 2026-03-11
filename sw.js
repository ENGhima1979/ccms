// CCMS Service Worker v3.0
const CACHE = 'ccms-v3';
const OFFLINE_URL = '/offline';

const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  'https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.11.3/font/bootstrap-icons.min.css',
];

// Install
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC_ASSETS).catch(() => {}))
  );
  self.skipWaiting();
});

// Activate
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch - Network First for API, Cache First for static
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  
  // Skip non-GET and API calls
  if (e.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname.includes('/pdf')) return;
  
  // Cache first for static assets
  if (url.pathname.startsWith('/static/') || 
      url.hostname.includes('cdnjs') ||
      url.hostname.includes('fonts.')) {
    e.respondWith(
      caches.match(e.request).then(cached => 
        cached || fetch(e.request).then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(e.request, clone));
          }
          return res;
        })
      )
    );
    return;
  }

  // Network first for pages
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok && res.status === 200) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request).then(cached => cached || caches.match('/')))
  );
});

// Push notifications
self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {};
  e.waitUntil(
    self.registration.showNotification(data.title || 'CCMS إشعار', {
      body: data.body || '',
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/icon-72.png',
      tag: data.tag || 'ccms',
      data: { url: data.url || '/' },
      dir: 'rtl',
      lang: 'ar',
      vibrate: [200, 100, 200],
      actions: data.actions || [],
    })
  );
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow(e.notification.data.url || '/'));
});
