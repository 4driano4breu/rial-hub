const CACHE = 'equipamentos-v1';
const URLS_TO_CACHE = [];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(URLS_TO_CACHE)));
});

self.addEventListener('fetch', e => {
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});

self.addEventListener('sync', e => {
  if (e.tag === 'sync-checklist') {
    e.waitUntil(syncPendentes());
  }
});

async function syncPendentes() {
  // Background sync placeholder
}
