// PFI usage counter (Cloudflare Worker + D1).
//
// POST /ping  {"id": "<32 hex>", "version": "0.5.0", "lang": "en"}
//   Stores one row per id and ISO week. Nothing else is read or stored:
//   no IP address, no headers, no timestamps finer than the week.
// GET /stats  (header "Authorization: Bearer <STATS_KEY>")
//   Active installs per week for the last 26 weeks, and versions and
//   languages of the latest week.

const ID = /^[0-9a-f]{32}$/;
const VERSION = /^\d{1,3}\.\d{1,3}\.\d{1,3}$/;
const LANGS = new Set(["en", "fr", "ar"]);

function isoWeek(d) {
  const t = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((t - yearStart) / 86400000 + 1) / 7);
  return `${t.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/ping" && request.method === "POST") {
      if (Number(request.headers.get("Content-Length") || 0) > 512) {
        return json({ error: "too large" }, 413);
      }
      let body;
      try { body = await request.json(); } catch { return json({ error: "bad json" }, 400); }
      const { id, version, lang } = body || {};
      if (!ID.test(id || "") || !VERSION.test(version || "") || !LANGS.has(lang)) {
        return json({ error: "bad values" }, 400);
      }
      await env.DB.prepare(
        "INSERT INTO pings (week, id, version, lang) VALUES (?1, ?2, ?3, ?4) " +
        "ON CONFLICT (week, id) DO UPDATE SET version = ?3, lang = ?4",
      ).bind(isoWeek(new Date()), id, version, lang).run();
      return new Response(null, { status: 204 });
    }
    if (url.pathname === "/stats" && request.method === "GET") {
      const auth = request.headers.get("Authorization") || "";
      if (!env.STATS_KEY || auth !== `Bearer ${env.STATS_KEY}`) {
        return json({ error: "not allowed" }, 401);
      }
      const weeks = await env.DB.prepare(
        "SELECT week, COUNT(*) AS installs FROM pings GROUP BY week " +
        "ORDER BY week DESC LIMIT 26").all();
      const latest = weeks.results[0]?.week;
      const by = async (col) => latest ? (await env.DB.prepare(
        `SELECT ${col} AS value, COUNT(*) AS installs FROM pings WHERE week = ?1 ` +
        `GROUP BY ${col} ORDER BY installs DESC`).bind(latest).all()).results : [];
      const ever = await env.DB.prepare("SELECT COUNT(DISTINCT id) AS n FROM pings").first();
      return json({ weeks: weeks.results, latest_week: latest ?? null,
        versions: await by("version"), languages: await by("lang"),
        installs_ever: ever?.n ?? 0 });
    }
    return json({ error: "not found" }, 404);
  },

  // Keep one year of weeks; older rows are deleted every Monday.
  async scheduled(_event, env) {
    const cutoff = isoWeek(new Date(Date.now() - 371 * 86400000));
    await env.DB.prepare("DELETE FROM pings WHERE week < ?1").bind(cutoff).run();
  },
};
