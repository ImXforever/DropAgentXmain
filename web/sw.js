/* DropAgentX Service Worker — v4.2.0
   استاتیک: stale-while-revalidate · API: همیشه شبکه · ناوبری: شبکه، فالبک آفلاین */
const CACHE = "dax-v0.6.0";
const OFFLINE_URL = "/offline.html";
const PRECACHE = [OFFLINE_URL, "/icon.svg", "/vendor/three.min.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return;            // API همیشه زنده
  if (e.request.mode === "navigate") {                      // صفحه‌ها: شبکه→کش→آفلاین
    e.respondWith(
      fetch(e.request)
        .then((r) => { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, cp)); return r; })
        .catch(() => caches.match(e.request).then((m) => m || caches.match(OFFLINE_URL)))
    );
    return;
  }
  e.respondWith(                                            // استاتیک: کش اول + به‌روزرسانی پس‌زمینه
    caches.match(e.request).then((cached) => {
      const fresh = fetch(e.request).then((r) => {
        if (r.ok) { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, cp)); }
        return r;
      }).catch(() => cached);
      return cached || fresh;
    })
  );
});
