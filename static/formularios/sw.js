const CACHE = 'formularios-v1';
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
  if (e.tag === 'sync-formulario') {
    e.waitUntil(syncPendentes());
  }
});

async function syncPendentes() {
  // Implementação simplificada — será expandida na Fase 4
}
