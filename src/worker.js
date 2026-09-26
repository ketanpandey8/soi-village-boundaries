// Serves the static app, proxies /data/* from the R2 bucket, gives state and village pages
// (/goa, /goa/626863) their own title, link preview and text, serves the sitemaps, and
// relays PostHog analytics through this domain (/relay/*).
//
// Worker responses aren't cached by Cloudflare's CDN automatically, so without the
// Cache API every request streams the file out of R2 again (UP is ~41 MB raw). The
// cache key is the full URL, so bumping ?v= in the app busts it.
const SITE = "India Villages";
const PAGE = /^\/(embed\/)?([a-z-]+)(?:\/([^/]+))?\/?$/;   // [/embed]/<state>[/<lgd>]

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/relay/")) return relay(request, url);

    if (url.pathname.startsWith("/data/")) {
      if (request.method !== "GET" && request.method !== "HEAD")
        return new Response("Method not allowed", { status: 405, headers: { allow: "GET, HEAD" } });

      // Open to any origin: an embed inside a sandboxed frame (many HTML editors' previews)
      // runs with origin "null", so even its own /data/ fetches count as cross-origin.
      const cache = caches.default;
      const hit = await cache.match(request);
      if (hit) {                                      // entries cached before this header existed lack it
        if (hit.headers.get("access-control-allow-origin")) return hit;
        const res = new Response(hit.body, hit);
        res.headers.set("access-control-allow-origin", "*");
        res.headers.set("access-control-expose-headers", "x-raw-size");
        return res;
      }

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
      headers.set("access-control-allow-origin", "*");
      headers.set("access-control-expose-headers", "x-raw-size");
      const res = new Response(obj.body, { headers });
      if (request.method === "GET") ctx.waitUntil(cache.put(request, res.clone()));
      return res;
    }

    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) return api(request, env, ctx, url);

    // sitemaps, built by build/make_pages.py
    const sm = url.pathname.match(/^\/sitemap(?:-(\d+))?\.xml$/);
    if (sm && (request.method === "GET" || request.method === "HEAD")) {
      // kept in the edge cache so crawlers get them quickly (each is a few MB before compression)
      const key = new Request(url.origin + url.pathname);
      const hit = await caches.default.match(key);
      if (hit) return request.method === "HEAD" ? new Response(null, hit) : hit;
      const obj = await env.DATA.get(sm[1] ? `sitemaps/sitemap-${sm[1]}.xml` : "sitemaps/index.xml");
      if (!obj) return new Response("Not found", { status: 404 });
      const res = new Response(obj.body, { headers: {
        "content-type": "application/xml; charset=utf-8", "cache-control": "public, max-age=86400",
        "etag": obj.httpEtag, "last-modified": obj.uploaded.toUTCString() } });
      ctx.waitUntil(caches.default.put(key, res.clone()));
      return request.method === "HEAD" ? new Response(null, res) : res;
    }

    // "/" is served straight from static assets; other paths that look like a state or
    // village page get the app with that page's preview tags
    const m = url.pathname.match(PAGE);
    if (m && (request.method === "GET" || request.method === "HEAD")) {
      const res = await page(env, url, m[2], m[3] && decodeURIComponent(m[3]), !!m[1]);
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

async function page(env, url, slug, lgd, embed) {
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
    // embeds live on other sites: keep them out of search results, and point to the real page
    .on('link[rel="canonical"]', { element: e => { if (embed) e.after('<meta name="robots" content="noindex">', { html: true }); } })
    .on("title", { element: e => e.setInnerContent(`${title} · ${SITE}`) })
    .on("#seo", { element: e => e.setInnerContent(body, { html: true }) });
  for (const [attr, v, sel] of tags) rw = rw.on(sel, { element: e => e.setAttribute(attr, v) });
  const res = rw.transform(app);
  const headers = new Headers(res.headers);
  headers.set("cache-control", "no-cache");        // small, and must change with each deploy
  headers.delete("etag");                          // the asset's etag doesn't describe this page
  return new Response(res.body, { status: 200, headers });
}

// ---------- API ----------
// GET /api/village/<lgd>                     the village(s) with that LGD code, as JSON
// GET /api/village/<state>/<lgd>.geojson     one village's boundary with every surveyed point
// Open to any site (CORS), cached at the edge for a day.
const API_HEADERS = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*",
  "cache-control": "public, max-age=86400" };
const CREDIT = "Village boundaries © Survey of India, National Geospatial Policy 2022";
const json = (body, status = 200, type) =>
  new Response(JSON.stringify(body), { status, headers: type ? { ...API_HEADERS, "content-type": type } : API_HEADERS });

async function api(request, env, ctx, url) {
  if (request.method === "OPTIONS")
    return new Response(null, { headers: { "access-control-allow-origin": "*", "access-control-allow-methods": "GET, HEAD" } });
  if (request.method !== "GET" && request.method !== "HEAD") return json({ error: "Use GET" }, 405);
  const key = new Request(url.origin + url.pathname);
  const hit = await caches.default.match(key);
  if (hit) return hit;
  const res = await apiAnswer(env, url);
  if (res.status === 200) ctx.waitUntil(caches.default.put(key, res.clone()));
  return res;
}

async function apiAnswer(env, url) {
  const origin = "https://" + url.host;
  let m = url.pathname.match(/^\/api\/village\/(\d+)\/?$/);
  if (m) {
    const lgd = m[1];
    const [ix, states] = await Promise.all([r2json(env, `pages/lgd-${lgd.slice(0, 3)}.json`), r2json(env, "states.json")]);
    const rows = (ix && ix[lgd]) || [];
    if (!rows.length) return json({ error: `No village with LGD code ${lgd}` }, 404);
    const stName = s => ((states || []).find(x => x.slug === s) || {}).name || s;
    return json({ villages: rows.map(([slug, name, d, t, area, cat, nbrs]) => ({
      lgd, name: name || null, state: stName(slug), state_slug: slug, district: d || null, taluk: t || null,
      area_km2: area ?? null, category: cat || null,
      bordering: nbrs.map(([l, n]) => ({ lgd: l || null, name: n || null })),
      page: `${origin}/${slug}/${lgd}`, geojson: `${origin}/api/village/${slug}/${lgd}.geojson`,
    })), source: CREDIT });
  }
  m = url.pathname.match(/^\/api\/village\/([a-z-]+)\/(\d+)\.geojson$/);
  if (m) {
    const [, slug, lgd] = m;
    const ix = await r2json(env, `pages/lgd-${lgd.slice(0, 3)}.json`);
    const row = ((ix && ix[lgd]) || []).find(r => r[0] === slug);
    if (!row) return json({ error: `No village with LGD code ${lgd} in ${slug}` }, 404);
    const [, name, d, t, area, cat, , file, j] = row;
    if (!file) return json({ error: "No boundary file for this village" }, 404);
    const obj = await env.DATA.get(`${slug}/${file}.packed.json`);
    if (!obj) return json({ error: "Boundary file missing" }, 404);
    const pk = await obj.json(), g = pk.g[j], q = pk.q;
    if (!g || (pk.p[j] || {}).l !== lgd) return json({ error: "Boundary not found" }, 404);
    const ring = r => { const o = []; let x = 0, y = 0;
      for (let k = 0; k < r.length; k += 2) { x += r[k]; y += r[k + 1]; o.push([x / q, y / q]); } return o; };
    const polys = g.map(p => p.map(ring));
    return json({ type: "Feature",
      properties: { lgd, name: name || null, taluk: t || null, district: d || null, state_slug: slug,
        area_km2: area ?? null, category: cat || null, source: CREDIT },
      geometry: polys.length === 1 ? { type: "Polygon", coordinates: polys[0] } : { type: "MultiPolygon", coordinates: polys },
    }, 200, "application/geo+json; charset=utf-8");
  }
  if (url.pathname === "/api" || url.pathname === "/api/")
    return json({ endpoints: {
      [`${origin}/api/village/<lgd>`]: "villages with that LGD code: name, state, district, taluk, area, category, bordering villages",
      [`${origin}/api/village/<state>/<lgd>.geojson`]: "the village boundary as a GeoJSON Feature, every surveyed point",
    }, example: `${origin}/api/village/626847`, source: CREDIT });
  return json({ error: "Not found. See /api" }, 404);
}

// ---------- PostHog relay ----------
// Ad blockers block PostHog's own domains, so the app sends analytics to /relay/* here and
// this forwards it: the library files to the assets host, events to the ingestion host.
// PostHog places visitors by IP, so the visitor's (not the Worker's) goes along.
async function relay(request, url) {
  const path = url.pathname.slice("/relay".length);
  const host = /^\/(static|array)\//.test(path) ? "us-assets.i.posthog.com" : "us.i.posthog.com";
  const headers = new Headers(request.headers);
  headers.delete("cookie");                       // this site's cookies aren't PostHog's business
  const ip = request.headers.get("cf-connecting-ip");
  if (ip) headers.set("x-forwarded-for", ip);
  return fetch(new Request(`https://${host}${path}${url.search}`, {
    method: request.method, headers, redirect: "manual",
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
  }));
}
