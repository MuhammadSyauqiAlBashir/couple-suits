// Storefront service worker: installable app + fast repeat visits.
// Pages: network first (prices and stock must be fresh), offline fallback.
// Static files and product images: cache first (their URLs change when they change).
const VERSION = "__VERSION__"
const STATIC = "cs-static-" + VERSION
const MEDIA = "cs-media"

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(STATIC).then((c) => c.addAll(["/offline", "/static/icons/icon-192.png"])).then(() => self.skipWaiting()))
})

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k.startsWith("cs-static-") && k !== STATIC).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()))
})

async function trim(name, max) {
  const c = await caches.open(name)
  const keys = await c.keys()
  for (const k of keys.slice(0, Math.max(0, keys.length - max))) await c.delete(k)
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url)
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(async () => (await caches.match("/offline")) || Response.error()))
    return
  }
  const bucket = url.pathname.startsWith("/static/") ? STATIC : url.pathname.startsWith("/media/") ? MEDIA : null
  if (!bucket) return
  e.respondWith(caches.open(bucket).then(async (c) => {
    const hit = await c.match(e.request)
    if (hit) return hit
    const res = await fetch(e.request)
    if (res.ok) { c.put(e.request, res.clone()); if (bucket === MEDIA) trim(MEDIA, 300) }
    return res
  }))
})
