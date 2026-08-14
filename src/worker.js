// Serves the static app and proxies /data/<state>.geojson from the R2 bucket.
// Same-origin, so the front-end keeps fetching "data/…" with no CORS and no change.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/data/")) {
      const key = decodeURIComponent(url.pathname.slice("/data/".length));
      const obj = await env.DATA.get(key);
      if (!obj) return new Response("Not found", { status: 404 });

      const headers = new Headers();
      obj.writeHttpMetadata(headers);                 // etag, stored metadata
      headers.set("content-type", "application/json; charset=utf-8");
      headers.set("cache-control", "public, max-age=31536000, immutable");
      return new Response(obj.body, { headers });
    }

    // everything else -> the static app (index.html)
    return env.ASSETS.fetch(request);
  },
};
