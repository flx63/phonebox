/* Generated asset list from the same build that embeds the panel. */
const prefix = 'phonebox-panel-';
const cacheName = prefix + '__CACHE__';
const assets = new Set(__ASSETS__);

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(cacheName).then((cache) =>
    cache.addAll([...assets].map((path) => new Request(path, { cache: 'reload', credentials: 'omit' })))));
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith(prefix) && name !== cacheName) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || !assets.has(url.pathname)) return;
  if (url.search && !(request.mode === 'navigate' && url.pathname === '/panel/')) return;
  // One complete version stays active until its tabs are closed. API requests always go to the network.
  event.respondWith(caches.open(cacheName).then(async (cache) =>
    (await cache.match(url.pathname)) || fetch(request)));
});
