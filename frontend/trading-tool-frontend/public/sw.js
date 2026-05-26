/*
 * PWA caching is intentionally disabled. Keep this worker around only to
 * unregister legacy installs and clear old Workbox/API caches after deploys.
 */

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));

      if (self.registration) {
        await self.registration.unregister();
      }

      await self.clients.claim();

      const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of clients) {
        client.postMessage({ type: "TRADAMIND_SW_DISABLED" });
      }
    })()
  );
});
