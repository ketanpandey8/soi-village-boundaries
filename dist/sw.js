// Offline support. The app itself is fetched fresh when online (so deploys show at once) and
// served from cache when not; map data is versioned (?v=) and never changes, so once a state
// or search file has been fetched it is kept and served from the device.
const DATA_V = "6";                         // must match DATA_V in build/app.html (build/check.sh)
const APP = "app", DATA = "data-v" + DATA_V, FONTS = "fonts";

self.addEventListener("install", e => {
  e.waitUntil(caches.open(APP).then(c => c.addAll(["/", "/manifest.webmanifest", "/icons/icon-192.png"])));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  // drop map data from older builds; it was replaced, and can be large
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("data-v") && k !== DATA).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET") return;
  if (u.origin === location.origin && u.pathname.startsWith("/data/") && u.searchParams.get("v") === DATA_V)
    return e.respondWith(cacheFirst(DATA, r));
  if (u.hostname === "fonts.googleapis.com" || u.hostname === "fonts.gstatic.com")
    return e.respondWith(cacheFirst(FONTS, r));
  if (r.mode === "navigate" && u.origin === location.origin && !u.pathname.startsWith("/api"))
    return e.respondWith(networkFirst(r));
});

async function cacheFirst(name, r) {
  const c = await caches.open(name), hit = await c.match(r);
  if (hit) return hit;
  const res = await fetch(r);
  if (res.ok) c.put(r, res.clone());
  return res;
}
// pages: the network when there is one; offline, the cached app, which routes by its own URL
async function networkFirst(r) {
  const c = await caches.open(APP);
  try {
    const res = await fetch(r);
    if (res.ok && new URL(r.url).pathname === "/") c.put("/", res.clone());
    return res;
  } catch (_) {
    return (await c.match(r)) || (await c.match("/")) || Response.error();
  }
}
