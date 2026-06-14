// service-worker.js — InvestIQ PWA Service Worker
const CACHE = "investiq-v1.0.0";
const STATIC = ["/", "/index.html", "/static/js/main.chunk.js", "/static/css/main.chunk.css"];

// Install — cache static assets
self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(STATIC).catch(() => {}))
  );
  self.skipWaiting();
});

// Activate — clear old caches
self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network first, fallback to cache
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  // API calls — always network
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws")) return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok && e.request.method === "GET") {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// Push notifications
self.addEventListener("push", e => {
  const data = e.data?.json() || {};
  const opts = {
    body: data.mensaje || "Alerta de InvestIQ",
    icon: "/logo192.png",
    badge: "/logo192.png",
    tag: data.tipo || "investiq",
    data: { url: data.url || "/" },
    actions: [
      { action: "ver", title: "Ver ahora" },
      { action: "cerrar", title: "Cerrar" }
    ],
    vibrate: [100, 50, 100],
  };
  e.waitUntil(
    self.registration.showNotification(
      data.titulo || "InvestIQ",
      opts
    )
  );
});

// Notification click
self.addEventListener("notificationclick", e => {
  e.notification.close();
  if (e.action === "cerrar") return;
  const url = e.notification.data?.url || "/";
  e.waitUntil(
    clients.matchAll({ type: "window" }).then(ws => {
      const w = ws.find(w => w.url.includes(self.location.origin));
      if (w) { w.focus(); w.navigate(url); }
      else clients.openWindow(url);
    })
  );
});

// Background sync — retry failed orders
self.addEventListener("sync", e => {
  if (e.tag === "retry-orders") {
    e.waitUntil(retryPendingOrders());
  }
});

async function retryPendingOrders() {
  const cache = await caches.open("pending-orders");
  const keys = await cache.keys();
  for (const req of keys) {
    try {
      const res = await fetch(req.clone());
      if (res.ok) await cache.delete(req);
    } catch {}
  }
}
