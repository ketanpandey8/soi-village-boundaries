// Serves the static app and proxies /data/<state>.geojson from the R2 bucket.
// Same-origin, so the front-end keeps fetching "data/…" with no CORS and no change.
//
// Worker responses aren't cached by Cloudflare's CDN automatically, so without the
// Cache API every request streams the file out of R2 again (UP is ~41 MB raw). The
// cache key is the full URL, so bumping ?v= in the app busts it.
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/data/")) {
      if (request.method !== "GET" && request.method !== "HEAD")
        return new Response("Method not allowed", { status: 405, headers: { allow: "GET, HEAD" } });

      const cache = caches.default;
      const hit = await cache.match(request);
      if (hit) return hit;

      const key = decodeURIComponent(url.pathname.slice("/data/".length));
      const obj = await env.DATA.get(key);
      if (!obj) return new Response("Not found", { status: 404 });

      const headers = new Headers();
      obj.writeHttpMetadata(headers);                 // stored metadata
      headers.set("etag", obj.httpEtag);
      headers.set("content-type", "application/json; charset=utf-8");
      headers.set("cache-control", "public, max-age=31536000, immutable");
      // decoded size, for the loading percentage (content-length is the compressed size)
      headers.set("x-raw-size", String(obj.size));
      const res = new Response(obj.body, { headers });
      if (request.method === "GET") ctx.waitUntil(cache.put(request, res.clone()));
      return res;
    }

    // everything else -> the static app (index.html)
    return env.ASSETS.fetch(request);
  },
};
