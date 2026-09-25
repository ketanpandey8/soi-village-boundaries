// Serves the static app, proxies /data/* from the R2 bucket, and gives state and village pages
// (/goa, /goa/626863) their own title and link preview.
//
// Worker responses aren't cached by Cloudflare's CDN automatically, so without the
// Cache API every request streams the file out of R2 again (UP is ~41 MB raw). The
// cache key is the full URL, so bumping ?v= in the app busts it.
const SITE = "India Villages";
const PAGE = /^\/([a-z-]+)(?:\/([^/]+))?\/?$/;

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

    // "/" is served straight from static assets; other paths that look like a state or
    // village page get the app with that page's preview tags
    const m = url.pathname.match(PAGE);
    if (m && (request.method === "GET" || request.method === "HEAD")) {
      const res = await page(env, url, m[1], m[2] && decodeURIComponent(m[2]));
      if (res) return res;
    }

    // everything else -> the static app (index.html)
    return env.ASSETS.fetch(request);
  },
};

// ---------- link previews ----------
const memo = new Map();                              // per isolate: small JSON from R2
async function r2json(env, key) {
  if (!memo.has(key)) {
    memo.set(key, env.DATA.get(key).then(o => (o ? o.json() : null)).catch(() => null));
    if (memo.size > 40) memo.delete(memo.keys().next().value);
  }
  return memo.get(key);
}
const cap = s => String(s || "").toLowerCase().replace(/\b\w/g, c => c.toUpperCase());

async function page(env, url, slug, lgd) {
  const states = await r2json(env, "states.json");
  const st = states && states.find(s => s.slug === slug);
  if (!st) return null;
  const origin = "https://" + url.host;
  let title = `${st.name} villages`;
  let desc = (st.villages ? `${st.villages.toLocaleString("en-IN")} village boundaries` : "Every village boundary") +
    ` in ${st.name}, from the Survey of India. Search any village by name or LGD code.`;
  let path = `/${slug}`;

  if (lgd && /^\d+$/.test(lgd)) {
    // the search index is split by the first two digits of the LGD code (build/make_search.py)
    const ix = await r2json(env, `search/lgd-${lgd.slice(0, 2)}.json`);
    const v = ix && ix.v.find(r => r[4] === lgd && ix.s[r[1]] === slug);
    if (v) {
      const [name, , d, t] = v, dist = cap(ix.d[d]), taluk = cap(ix.t[t]);
      const where = [taluk && `${taluk} taluk`, dist && `${dist} district`, st.name].filter(Boolean).join(", ");
      title = name ? `${name}, ${dist || st.name}` : `Village ${lgd}, ${dist || st.name}`;
      desc = `Boundary of ${name || "an unnamed village"} in ${where}. LGD code ${lgd}. Survey of India data.`;
      path = `/${slug}/${lgd}`;
    }
  }

  const app = await env.ASSETS.fetch(new Request(new URL("/", url)));
  const set = (sel, v) => ["content", v, sel];
  const tags = [
    set('meta[property="og:title"]', title),
    set('meta[property="og:description"]', desc),
    set('meta[name="description"]', desc),
    set('meta[property="og:url"]', origin + path),
    set('meta[property="og:image"]', `${origin}/cards/${slug}.png`),
  ];
  let rw = new HTMLRewriter().on("title", { element: e => e.setInnerContent(`${title} · ${SITE}`) });
  for (const [attr, v, sel] of tags) rw = rw.on(sel, { element: e => e.setAttribute(attr, v) });
  const res = rw.transform(app);
  const headers = new Headers(res.headers);
  headers.set("cache-control", "no-cache");        // small, and must change with each deploy
  headers.delete("etag");                          // the asset's etag doesn't describe this page
  return new Response(res.body, { status: 200, headers });
}
