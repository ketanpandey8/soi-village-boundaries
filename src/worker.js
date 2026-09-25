// Serves the static app, proxies /data/* from the R2 bucket, gives state and village pages
// (/goa, /goa/626863) their own title, link preview and text, and serves the sitemaps.
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

    // sitemaps, built by build/make_pages.py
    const sm = url.pathname.match(/^\/sitemap(?:-(\d+))?\.xml$/);
    if (sm) {
      const obj = await env.DATA.get(sm[1] ? `sitemaps/sitemap-${sm[1]}.xml` : "sitemaps/index.xml");
      if (!obj) return new Response("Not found", { status: 404 });
      return new Response(obj.body, { headers: {
        "content-type": "application/xml; charset=utf-8", "cache-control": "public, max-age=86400" } });
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

const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const num = n => Number(n).toLocaleString("en-IN");

async function page(env, url, slug, lgd) {
  const states = await r2json(env, "states.json");
  const st = states && states.find(s => s.slug === slug);
  if (!st) return null;
  const origin = "https://" + url.host;
  let title = `${st.name} villages`;
  let desc = (st.villages ? `${num(st.villages)} village boundaries` : "Every village boundary") +
    ` in ${st.name}, from the Survey of India. Search any village by name or LGD code.`;
  let path = `/${slug}`;
  let body = `<h1>Villages of ${esc(st.name)}</h1><p>${esc(desc)}</p><p><a href="/">All of India</a></p>`;

  if (lgd && /^\d+$/.test(lgd)) {
    // village page data, split by the first three digits of the LGD code (build/make_pages.py)
    const ix = await r2json(env, `pages/lgd-${lgd.slice(0, 3)}.json`);
    const v = ix && (ix[lgd] || []).find(r => r[0] === slug);
    if (v) {
      const [, name, d, t, area, cat, nbrs] = v, dist = cap(d), taluk = cap(t);
      const where = [taluk && `${taluk} taluk`, dist && `${dist} district`, st.name].filter(Boolean).join(", ");
      const nm = name || `Village ${lgd}`;
      title = `${nm}, ${dist || st.name}`;
      desc = `Boundary of ${name || "an unnamed village"} in ${where}. LGD code ${lgd}.` +
        (area != null ? ` Area ${area} km².` : "") +
        (nbrs.length ? ` Borders ${nbrs.slice(0, 3).map(n => n[1] || n[0]).join(", ")}${nbrs.length > 3 ? " and more" : ""}.` : "") +
        " Survey of India data.";
      path = `/${slug}/${lgd}`;
      const link = ([l, n]) => l ? `<a href="/${slug}/${esc(l)}">${esc(n || "Village " + l)}</a>` : esc(n || "an unnamed village");
      body = `<h1>${esc(nm)} village, ${esc(dist || st.name)}</h1>` +
        `<p>${esc(nm)} is a village in ${esc(where)}. Its LGD code is ${esc(lgd)}` +
        (area != null ? ` and it covers ${esc(area)} km²` : "") + (cat ? `. Category: ${esc(cat)}` : "") + `.</p>` +
        (nbrs.length ? `<p>Bordering villages: ${nbrs.map(link).join(", ")}.</p>` : "") +
        `<p>Boundary from the Survey of India village boundary database. <a href="/${slug}">All villages in ${esc(st.name)}</a></p>`;
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
    ["href", origin + path, 'link[rel="canonical"]'],
  ];
  let rw = new HTMLRewriter()
    .on("title", { element: e => e.setInnerContent(`${title} · ${SITE}`) })
    .on("#seo", { element: e => e.setInnerContent(body, { html: true }) });
  for (const [attr, v, sel] of tags) rw = rw.on(sel, { element: e => e.setAttribute(attr, v) });
  const res = rw.transform(app);
  const headers = new Headers(res.headers);
  headers.set("cache-control", "no-cache");        // small, and must change with each deploy
  headers.delete("etag");                          // the asset's etag doesn't describe this page
  return new Response(res.body, { status: 200, headers });
}
