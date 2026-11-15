/* TRADE-AI service worker: shows new-signal notifications. No caching, no tracking. */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { title: "TRADE-AI", body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || "TRADE-AI", {
    body: d.body || "New analysis available.", tag: d.tag, renotify: true,
    icon: "assets/img/icon-192.png", badge: "assets/img/icon-192.png", data: { url: d.url || "app.html#/signals" }
  }));
});
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL(e.notification.data.url, self.registration.scope).href;
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const c of all) if (c.url.startsWith(self.registration.scope)) { await c.focus(); return c.navigate(url); }
    return self.clients.openWindow(url);
  })());
});
