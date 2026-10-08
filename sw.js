/* Service worker de Kunaq: guarda las páginas en el equipo para que abran SIN internet.
   Solo funciona cuando el sistema se abre con http:// (por ejemplo desde servidor_nube.py).
   Estrategia: intenta la red 3 segundos; si la señal es mala usa la copia guardada. */
const VERSION = 'kunaq-v2';
const ARCHIVOS = ['views/index.html', 'views/admin.html', 'assets/kunaq-core.js',
                  'assets/kunaq-core.css', 'assets/kunaq-logo.png', 'assets/kunaq-mark.png', 'assets/favicon.png'];

self.addEventListener('install', (e) => {
  // uno por uno: si un archivo no existe en este servidor, los demás igual se guardan
  e.waitUntil(caches.open(VERSION).then((c) => Promise.allSettled(ARCHIVOS.map((a) => c.add(new URL(a, self.registration.scope).href)))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/api/')) return;   // la API nunca se guarda
  e.respondWith((async () => {
    const cache = await caches.open(VERSION);
    try {
      const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 3000);
      const r = await fetch(e.request, { signal: ctl.signal }); clearTimeout(t);
      if (r.ok) cache.put(e.request, r.clone());
      return r;
    } catch (err) {
      return (await cache.match(e.request)) || (await cache.match(e.request, { ignoreSearch: true })) || Response.error();
    }
  })());
});
