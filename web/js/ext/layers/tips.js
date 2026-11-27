// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it (FAF values are model estimates; bases have no published headcount; the
// trade arc is a drawing aid; curated landmarks are an editorial pick).
import { esc, compact, int, money, pct } from "../../format.js";
import { t, placeName } from "../../i18n.js";
import { FORT_KINDS, fortKind, WONDER_KINDS } from "../../render/art/sites.js";
import { MODE_STYLE } from "../../render/art/improvements.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n) => (n == null || !Number.isFinite(n) ? "–" : compact(n));
const placeText = (name, nameLat) => (name ? placeName({ name, name_lat: nameLat }) : "");

const PORT_TYPE = { inland: t("River port") };

export const tips = {
  port(p) {
    const lines = [`<b>${esc(placeName(p))}</b> ${muted(esc([PORT_TYPE[p.type] || t("Port"), p.river, p.state].filter(Boolean).join(", ")))}`];
    if (p.tons != null) lines.push(t("#{rank} by cargo · {tons} t ({year})", { rank: esc(p.rank), tons: `<b>${num(p.tons)}</b>`, year: esc(p.year ?? "") }));
    lines.push(muted(esc(t("Port area mapped in OpenStreetMap, placed at its centre."))));
    return lines.join("<br>");
  },
  airport(a) {
    const lines = [`<b>${esc(a.id)} · ${esc(placeName(a))}</b> ${muted(esc(a.state || ""))}`];
    if (a.enplanements != null) lines.push(t("{count} passengers in {year}", { count: `<b>${num(a.enplanements)}</b>`, year: esc(a.year ?? "") }));
    else lines.push(muted(esc(t("No published passenger count."))));
    return lines.join("<br>");
  },
  fort(f, m) {
    const comp = m.data.military?.components?.find((c) => c.id === f.component);
    const name = comp?.name || FORT_KINDS[fortKind(f.component)]?.name || t("Defense site");
    const tier = { major: t("Major installation"), base: t("Base"), site: t("Site") }[f.tier] || "";
    const status = { semi: t("semi-active"), care: t("caretaker status") }[f.status] || "";
    const lines = [
      `<b>${esc(placeName(f))}</b> ${muted(esc(f.state || ""))}`,
      esc([name, f.joint ? t("joint base") : "", tier, status].filter(Boolean).join(" · ")),
    ];
    if (f.area_km2 != null) lines.push(esc(t("Boundary {area} km²", { area: int(f.area_km2) })));
    lines.push(muted(esc(t("DoD MIRTA. Sized by boundary area: no per-base headcount is published."))));
    return lines.join("<br>");
  },
  range(r, m) {
    const comp = m.data.military?.components?.find((c) => c.id === r.component);
    return [
      `<b>${esc(placeName(r))}</b> ${muted(esc(r.state || ""))}`,
      esc([t("Restricted ground"), comp?.name, t("{area} km²", { area: int(r.area_km2) })].filter(Boolean).join(" · ")),
      muted(esc(t("One of the 30 largest DoD boundaries (MIRTA), drawn on the hexes it covers."))),
    ].join("<br>");
  },
  wonder(x, m) {
    const kind = WONDER_KINDS[x.kind]?.name || t("Wonder");
    const rule = m.data.wonders?.rules?.find((r) => r.id === x.rule);
    const mt = x.metrics || {};
    const lines = [`<b>${esc(placeName(x))}</b> ${muted(esc([x.state].filter(Boolean).join("")))}`];
    if (x.kind === "university") {
      lines.push(esc(t("{kind} · #{rank} by research spending", { kind, rank: x.rank })));
      if (mt.rd_usd != null) {
        const vars = { amount: money(mt.rd_usd), year: mt.year, share: mt.federal_usd != null ? pct(mt.federal_usd / mt.rd_usd, 0) : "" };
        lines.push(esc(mt.federal_usd != null ? t("R&D {amount} (FY{year}), {share} federal", vars) : t("R&D {amount} (FY{year})", vars)));
      }
      if (mt.enrollment != null) lines.push(esc(t("{count} students (12-month headcount, {year})", { count: int(mt.enrollment), year: mt.enrollment_year })));
    } else if (x.curated) {
      lines.push(esc(t("{kind} · hand-picked (curated, not ranked by data)", { kind })));
      if (mt.visits != null) lines.push(esc(t("{count} recreation visits ({year})", { count: num(mt.visits), year: mt.year })));
      if (mt.designated) lines.push(esc(t("National Historic Landmark since {year}", { year: mt.designated })));
    } else {
      const vars = { kind, rank: x.rank };
      const by = !mt.unit_type ? t("{kind} · #{rank} by visits", vars)
        : mt.unit_type === "National Park" ? t("{kind} · #{rank} by visits among National Parks", vars)
          : t("{kind} · #{rank} by visits among other park units", vars);
      lines.push(esc(by));
      if (mt.visits != null) {
        const visits = t("{count} recreation visits ({year})", { count: `<b>${num(mt.visits)}</b>`, year: esc(mt.year) });
        lines.push(`${visits}${mt.visits_of ? ` ${muted(`(${esc(placeText(mt.visits_of, mt.visits_of_lat))})`)}` : ""}`);
      }
      if (mt.area_km2 != null) lines.push(esc(t("{area} km²", { area: int(mt.area_km2) })));
    }
    if (rule?.text) lines.push(muted(esc(rule.text)));
    return lines.join("<br>");
  },
  route(rt, m) {
    const r = rt.route;
    const trade = m.data.trade || {};
    const zone = (z, id) => (z?.short ? placeText(z.short, z.short_lat) : z?.name ? placeName(z) : id);
    const a = zone(rt.a, r.a), b = zone(rt.b, r.b);
    const modes = Object.entries(r.modes || {}).filter(([, v]) => v >= 0.05).sort((p, q) => q[1] - p[1])
      .map(([k, v]) => `${esc(MODE_STYLE[k]?.label || k)} ${pct(v, 0)}`).join(" · ");
    const com = trade.commodities?.[r.top_commodity];
    const lines = [
      `<b>${esc(a)} ⇄ ${esc(b)}</b> ${muted(esc(t("trade route #{rank}", { rank: r.rank })))}`,
      t("{value} of freight a year, {tons} short tons (FAF {year} estimate)", {
        value: `<b>${money(r.value_musd * 1e6)}</b>`, tons: num(r.tons_k * 1e3), year: esc(trade.year ?? ""),
      }),
    ];
    if (modes) lines.push(modes);
    if (com) lines.push(esc(t("Top commodity: {name}", { name: com })));
    lines.push(muted(esc(t("Both directions summed. Drawn as an arc between each zone's largest city: FAF records where freight starts and ends, not its route."))));
    return lines.join("<br>");
  },
};
