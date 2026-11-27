// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it (FAF values are model estimates; bases have no published headcount; the
// trade arc is a drawing aid; curated landmarks are an editorial pick).
import { esc, compact, int, money, pct } from "../../format.js";
import { t, placeName } from "../../i18n.js";
import { FORT_KINDS, fortKind, WONDER_KINDS } from "../../render/art/sites.js";
import { MODE_STYLE } from "../../render/art/improvements.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n) => (n == null || !Number.isFinite(n) ? "–" : compact(n));
const sign = (x) => (x > 0 ? "+" : x < 0 ? "−" : "±");
const placeText = (name, nameLat) => (name ? placeName({ name, name_lat: nameLat }) : "");

const HUB_NAME = { L: t("Large hub"), M: t("Medium hub"), S: t("Small hub"), N: t("Nonhub primary airport") };
const PORT_TYPE = { coastal: t("Coastal port"), great_lakes: t("Great Lakes port"), inland: t("River port") };

export const tips = {
  port(p, m) {
    const yr = p.year ?? "";
    const lines = [
      `<b>${esc(placeName(p))}</b> ${muted(esc([PORT_TYPE[p.type] || t("Port"), p.state].filter(Boolean).join(", ")))}`,
      t("#{rank} by tonnage · {tons} short tons ({year})", { rank: esc(p.rank), tons: `<b>${num(p.tons)}</b>`, year: esc(yr) }),
    ];
    if (p.foreign != null || p.domestic != null) lines.push(esc(t("Foreign {foreign} · domestic {domestic}", { foreign: num(p.foreign), domestic: num(p.domestic) })));
    if (p.imports != null || p.exports != null) lines.push(esc(t("Imports {imports} · exports {exports}", { imports: num(p.imports), exports: num(p.exports) })));
    lines.push(muted(esc(t("USACE principal ports; placed at the port area's centre (long river ports are approximate)."))));
    return lines.join("<br>");
  },
  airport(a) {
    const lines = [`<b>${esc(a.id)} · ${esc(placeName(a))}</b> ${muted(esc([placeText(a.city, a.city_lat), a.state].filter(Boolean).join(", ")))}`];
    lines.push(esc(a.hub ? HUB_NAME[a.hub] || a.hub : t("All-cargo airport (not a primary passenger airport)")));
    if (a.enplanements != null) {
      const count = `<b>${num(a.enplanements)}</b>`;
      if (a.enplanements_prev > 0) {
        const r = a.enplanements / a.enplanements_prev - 1;
        lines.push(t("{count} boardings in {year} ({change} on {prev})", { count, year: esc(a.year), change: sign(r) + pct(Math.abs(r), 1), prev: esc(a.year - 1) }));
      } else lines.push(t("{count} boardings in {year}", { count, year: esc(a.year) }));
    }
    if (a.cargo_lbs != null) lines.push(esc(t("All-cargo landed weight {weight} lb", { weight: num(a.cargo_lbs) })));
    lines.push(muted(esc(t("FAA CY enplanements and all-cargo data."))));
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
