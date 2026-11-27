// The city screen: a docked dashboard (a bottom sheet on phones) with the header (and its city-type badge),
// Citizens (figure rows from citizens.json), Districts (districts.json + military.json), Economy, Workforce,
// Resources and Compare. Plain HTML strings + inline SVG charts; render(el, model, handlers) fills `el`. The
// citizens and districts files load on demand (h.loadData) and fill their sections when they arrive.
import { euros, esc, int, num, pct } from "../../format.js";
import { compact, money, popShort, yieldValue } from "./fmt.js";
import { icon, glyph } from "../../ui/icon.js";
import { css } from "../../color.js";
import { isCapital } from "../../world.js";
import { sparkline, meter, bar } from "./charts.js";
import { popSeries, rankCount, resourceValue, LAND } from "./model.js";
import { citizensHtml, mountCitizens } from "./citizens.js";
import { badgeHtml, cityDistricts, districtsHtml } from "./districts.js";
import { t, placeName } from "../../i18n.js";

const TABS = [
  ["citizens", t("Citizens"), "pop"],
  ["districts", t("City districts"), "l-developed"],
  ["economy", t("Economy"), "y-gold"],
  ["workforce", t("Workforce"), "y-production"],
  ["resources", t("Resources"), "resources"],
  ["compare", t("Compare"), "layers"],
];

const signed = (g, d = 1) => (g == null ? "–" : `${g >= 0 ? "+" : "−"}${pct(Math.abs(g), d)}`);
const rankCache = new WeakMap();
function countOf(cities, key) {
  let m = rankCache.get(cities);
  if (!m) rankCache.set(cities, (m = new Map()));
  if (!m.has(key)) m.set(key, rankCount(cities, key));
  return m.get(key);
}

function rankBadge(rank, of, label, tip) {
  if (rank == null) return "";
  const tier = rank <= 10 ? "gold" : rank <= 50 ? "silver" : "bronze";
  return `<div class="cv-rank ${tier}" title="${esc(tip || t("{label}: #{rank} of {of} cities (1 = highest)", { label, rank, of, n: of }))}">
    <span class="cv-medal">#${rank}</span><span class="cv-rank-l">${esc(label)}</span></div>`;
}

function lqBadge(lq) {
  if (lq == null) return "";
  const tip = t("Location quotient: this share is {lq}× the national share", { lq: num(lq, 2) });
  const cls = lq >= 1.25 ? "hi" : lq <= 0.75 ? "lo" : "mid";
  return `<span class="cv-lq ${cls}" title="${esc(tip)}">×${num(lq, 1)}</span>`;
}

function medallion(id, fallback, bg, size = 18) {
  return `<span class="cv-med" style="--bg:${esc(bg)}">${icon(id, fallback, { size })}</span>`;
}

// --- header --------------------------------------------------------------------------------------------------------
function header(m) {
  const c = m.city, n = m.nation.nation;
  const cities = m.cityList;
  const col = css(m.stateRGB);
  const chips = m.states.map((s) => (s.index >= 0
    ? `<button class="chip" data-state="${s.index}" title="${esc(t("Open {name}", { name: s.name }))}">${esc(s.abbr)}</button>`
    : `<span class="chip">${esc(s.abbr)}</span>`)).join("");
  const g = Number.isFinite(c.growth) ? c.growth : null;
  const yrs = Array.isArray(c.growth_years) ? c.growth_years : null;
  const growthTip = t("Population change {years}, census to census. Serbia: {national}", { years: yrs ? `${yrs[0]}–${yrs[1]}` : "", national: signed(n.growth) });
  const growth = g == null ? "" : `<span class="cv-growth ${g >= 0 ? "good" : "bad"}" title="${esc(growthTip)}">${g >= 0 ? "▲" : "▼"} ${pct(Math.abs(g), 1)}${yrs ? ` <small>${esc(t("since {year}", { year: yrs[0] }))}</small>` : ""}</span>`;
  const perCap = c.gdp != null && c.population ? c.gdp / c.population : null;
  const r = c.ranks || {};
  const N = (k) => countOf(cities, k);
  return `
  <div class="sheet-grip cv-grip" aria-hidden="true"></div>
  <header class="cv-head" style="--sc:${col}">
    <div class="cv-ribbon" aria-hidden="true"></div>
    <button class="icon-btn cv-close" data-close aria-label="${esc(t("Close the City View (Esc)"))}" title="${esc(t("Back to the map (Esc)"))}">${icon("close", "✕", { size: 13 })}</button>
    <div class="cv-kind">${esc(t("City View"))} · ${esc(c.metro === false ? t("Town") : t("City"))}</div>
    <div class="cv-title">
      <div class="cv-crest" aria-hidden="true"><span>${esc(popShort(c.population))}</span></div>
      <div class="cv-tt">
        <h2 class="cv-name" tabindex="-1">${isCapital(c) ? `<span class="cv-cap" title="${esc(t("National capital"))}">★</span> ` : ""}${esc(placeName(c))}</h2>
        <div class="cv-full">${esc(placeName({ name: c.full, name_lat: c.full_lat }) || "")}</div>
        <div class="cv-typeslot" data-ctype></div>
        ${chips ? `<div class="chips">${chips}</div>` : ""}
      </div>
    </div>
    <div class="cv-headline">
      <div class="cv-big"><span class="lbl">${icon("pop", "👥", { size: 13 })} ${esc(t("Population"))}</span><b>${int(c.population)}</b>${growth}</div>
      <div class="cv-big"><span class="lbl">${icon("y-gold", "💰", { size: 13 })} ${esc(c.gdp_year ? t("GDP {year}", { year: c.gdp_year }) : t("GDP"))}</span><b>${money(c.gdp)}</b>${
        perCap != null ? `<span class="cv-sub">${esc(t("{v} per person", { v: money(perCap) }))}</span>` : ""}</div>
    </div>
    <div class="cv-ranks" aria-label="${esc(t("Ranks among {count} cities", { n: cities.length, count: int(cities.length) }))}">
      ${rankBadge(r.population, N("population"), t("Population"))}
      ${rankBadge(r.gdp, N("gdp"), t("GDP"))}
      ${rankBadge(r.gdp_per_capita, N("gdp_per_capita"), t("GDP / person"))}
      ${rankBadge(r.growth, N("growth"), t("Growth"), r.growth != null ? t("Growth: #{rank} of {of} (1 = fastest growing)", { rank: r.growth, of: N("growth") }) : "")}
    </div>
  </header>
  <nav class="cv-tabs" aria-label="${esc(t("City View sections"))}">
    ${TABS.map(([id, label, ic]) => `<button type="button" data-tab="${id}">${icon(ic, "•", { size: 14 })}<span>${esc(label)}</span></button>`).join("")}
  </nav>`;
}

// --- citizens ------------------------------------------------------------------------------------------------------
function citizens(m) {
  const c = m.city, n = m.nation.nation;
  const series = popSeries(c);
  const ch = series.length >= 2 ? series.at(-1).value / series[0].value - 1 : null;
  // sub: the small line beside the value; by default the national value, left out when there is none.
  const row = (ic, fb, label, v, us, fmt, better, max, sub = us != null ? esc(t("Serbia {v}", { v: fmt(us) })) : "", tick = us) => `
    <div class="cv-stat">
      <div class="cv-stat-top"><span class="sl">${icon(ic, fb, { size: 14 })}${esc(label)}</span>
        <span class="sv"><b>${v == null ? "–" : fmt(v)}</b>${sub ? `<small>${sub}</small>` : ""}</span></div>
      ${meter(v, tick, max ?? Math.max(v || 0, us || 0) * 1.35, better)}
    </div>`;
  // Employed residents: no national figure to set beside a count, so the share of residents (and the national share).
  const empShare = c.employed != null && c.population > 0 ? c.employed / c.population : null;
  const usEmpShare = n.employed != null && n.population > 0 ? n.employed / n.population : null;
  const empSub = empShare == null ? ""
    : esc([t("{v} of residents", { v: pct(empShare) }), usEmpShare != null ? t("Serbia {v}", { v: pct(usEmpShare) }) : ""].filter(Boolean).join(" · "));
  const multi = m.tiles.length > 1;
  const noteVars = { residents: `<b>${esc(t("≈ residents"))}</b>`, land: `<b>${esc(t("main land use"))}</b>`, n: m.tiles.length, count: int(m.tiles.length), people: compact(m.residentsSum) };
  const tilesNote = !multi ? esc(t("This city fits inside one map hex (about {area} km²), shown with its centre.", { area: compact(m.hexArea) }))
    : m.residentsSum > 0 ? t("On the map each city hex shows {residents} (municipal population density × hex area, an estimate) and its {land} (share of the hex's land). Together the {count} hexes hold about {people} people by that estimate.", noteVars)
      : t("On the map each city hex shows {residents} (municipal population density × hex area, an estimate) and its {land} (share of the hex's land).", noteVars);
  return `
  <section class="cv-sec" id="cv-citizens" data-sec="citizens" aria-labelledby="cv-h-citizens">
    <h3 id="cv-h-citizens">${icon("pop", "👥", { size: 15 })}${esc(t("Citizens"))}</h3>
    <div class="cv-citizens" data-citizens>${citizensHtml(m, undefined)}</div>
    <h4 class="cv-h4">${esc(t("Population"))}</h4>
    <div class="cv-card">
      <div class="cv-card-h"><span>${esc(series.length ? t("Population {years}", { years: `${series[0].year}–${series.at(-1).year}` }) : t("Population"))}</span>${
        ch != null ? `<span class="${ch >= 0 ? "good" : "bad"}">${signed(ch)}</span>` : ""}</div>
      ${sparkline(series, { fmt: (v) => popShort(v), title: t("Population of {city} by year", { city: placeName(c) }) })}
      <p class="cv-note">${esc(t("Every census on today's borders (RZS); in KiM, the Kosovo Agency of Statistics' yearly estimates."))}</p>
    </div>
    <div class="cv-stats">
      ${row("pop", "👥", t("Employed residents"), c.employed, null, int, null, c.population, empSub, usEmpShare != null ? usEmpShare * c.population : null)}
      ${row("unemployment", "😐", t("Unemployment"), c.unemployment, n.unemployment, (x) => pct(x), "low")}
      ${row("l-income", "💶", t("Average net wage / mo"), c.median_income, n.median_income, euros, "high")}
    </div>
    <div class="cv-legend-tiles">${tileLegend(m)}<p>${tilesNote}</p></div>
    <h4 class="cv-h4">${esc(t("Member municipalities"))} <span class="muted">(${(c.counties || []).length})</span></h4>
    <div class="cv-counties" data-counties><p class="muted cv-note">${esc(t("Loading municipalities…"))}</p></div>
  </section>`;
}

function tileLegend(m) {
  const counts = new Map();
  for (const tile of m.tiles) if (tile.land) counts.set(tile.land.key, (counts.get(tile.land.key) || 0) + 1);
  return `<div class="cv-tl">${LAND.filter((g) => counts.has(g.key)).map((g) =>
    `<span class="cv-tl-i"><i style="background:${esc(m.landColor(g.key))}"></i>${esc(g.label)} <small>${counts.get(g.key)}</small></span>`).join("")}</div>`;
}

export function countiesTable(m, data) {
  const c = m.city;
  if (!data || !Array.isArray(data.rows)) return `<p class="muted cv-note">${esc(t("Municipality table not available."))}</p>`;
  const col = Object.fromEntries(data.columns.map((k, j) => [k, j]));
  const want = new Set(c.counties || []);
  const rows = data.rows.filter((r) => want.has(r[col.geoid])).sort((a, b) => (b[col.population] || 0) - (a[col.population] || 0));
  if (!rows.length) return `<p class="muted cv-note">${esc(t("No municipality rows for this city."))}</p>`;
  const maxPop = rows[0][col.population] || 1;
  const show = rows.slice(0, 8);
  const vint = data.vintage ? ` (${esc(data.vintage)})` : "";
  const nameOf = (r) => placeName({ name: r[col.name], name_lat: col.name_lat != null ? r[col.name_lat] : undefined });
  return `<div class="cv-ctable" role="table" aria-label="${esc(t("Member municipalities"))}">
    <div class="cv-cr cv-cr-h" role="row"><span role="columnheader">${esc(t("Municipality"))}</span><span role="columnheader">${esc(t("People"))}</span><span role="columnheader">${esc(t("/km²"))}</span><span role="columnheader">${esc(t("Income"))}</span></div>
    ${show.map((r) => `<div class="cv-cr" role="row">
      <span role="cell" class="cv-cn">${esc(nameOf(r))} <small>${esc(r[col.state])}</small>${bar(r[col.population] / maxPop, "var(--sc, #c9a45c)")}</span>
      <span role="cell">${compact(r[col.population])}</span><span role="cell">${r[col.density] != null ? int(r[col.density]) : "–"}</span>
      <span role="cell">${money(r[col.income])}</span></div>`).join("")}
    ${rows.length > show.length ? `<p class="muted cv-note">${esc(t("and {n} more.", { n: rows.length - show.length }))}</p>` : ""}
    <p class="cv-note">${esc(t("Census municipal figures"))}${vint}.</p>
  </div>`;
}

// --- districts -----------------------------------------------------------------------------------------------------
function districts(m) {
  return `
  <section class="cv-sec" id="cv-districts" data-sec="districts" aria-labelledby="cv-h-districts">
    <h3 id="cv-h-districts">${icon("l-developed", "🏙", { size: 15 })}${esc(t("City districts"))}</h3>
    <div data-districts>${districtsHtml(m, undefined, null)}</div>
  </section>`;
}

// --- economy -------------------------------------------------------------------------------------------------------
function economy(m) {
  const c = m.city, nat = m.nation, n = nat.nation;
  const r = c.ranks || {};
  const cities = m.cityList;
  const perCap = c.gdp != null && c.population ? c.gdp / c.population : null;
  const usPerCap = n.gdp && n.population ? n.gdp / n.population : null;
  const yields = nat.yields.map((y) => {
    const v = c.yields?.[y.key];
    const rk = r[y.key];
    return `<div class="cv-yield" style="--yc:${esc(y.color)}" title="${esc(t(y.label))}: ${esc(y.description || "")}">
      <div class="ico">${glyph(y, 20)}</div><div class="val">${yieldValue(y, v)}</div>
      <div class="lbl">${esc(y.key === "gold" ? t("GDP") : t(y.label))}</div>
      ${rk != null ? `<div class="rk">#${rk} <small>${esc(t("of {n}", { n: countOf(cities, y.key) }))}</small></div>` : ""}</div>`;
  }).join("");
  const gi = m.gdpInds;
  const maxShare = gi.length ? Math.max(...gi.map((d) => Math.max(d.share, d.natShare))) : 1;
  const gdpRow = (d) => d.undisclosed
    ? `<div class="cv-ind und" title="${esc(t("BEA withholds some municipal figures to protect individual businesses: {list}. This is the city's GDP minus every disclosed industry.", { list: d.missing.map((k) => nat.industries?.[k] || k).join(", ") || t("several industries") }))}">
      <span class="cv-ind-ic" style="--bg:${esc(d.color)}">${icon(d.icon, "?", { size: 13 })}</span>
      <span class="cv-ind-n">${esc(d.short)}</span>
      <span class="cv-ind-v">${money(d.value)} <small>${pct(d.share, 0)}</small></span>
      ${bar(d.share / maxShare, "#7c8494", 0)}
    </div>`
    : `<div class="cv-ind" title="${esc(t("{industry}: {value} ({share} of the city's GDP; Serbia {national})", { industry: d.label, value: money(d.value), share: pct(d.share), national: pct(d.natShare) }))}${d.estimated ? `. ${esc(t("Includes an estimate for small municipalities whose figure BEA withholds."))}` : ""}">
      <span class="cv-ind-ic" style="--bg:${esc(d.color)}">${icon(d.icon, "•", { size: 13 })}</span>
      <span class="cv-ind-n">${esc(d.short)}${lqBadge(d.lq)}</span>
      <span class="cv-ind-v">${d.estimated ? "≈" : ""}${money(d.value)} <small>${pct(d.share, 0)}</small></span>
      ${bar(d.share / maxShare, d.lq != null && d.lq >= 1.25 ? "#9fd76a" : "#c9a45c", d.natShare / maxShare)}
    </div>`;
  return `
  <section class="cv-sec" id="cv-economy" data-sec="economy" aria-labelledby="cv-h-economy">
    <h3 id="cv-h-economy">${icon("y-gold", "💰", { size: 15 })}${esc(t("Economy"))}</h3>
    <div class="cv-gdp">
      <div><span class="lbl">${esc(c.gdp_year ? t("GDP ({year})", { year: c.gdp_year }) : t("GDP"))}</span><b>${money(c.gdp)}</b>${r.gdp != null ? `<small>${esc(t("#{rank} of {n}", { rank: r.gdp, n: countOf(cities, "gdp") }))}</small>` : ""}</div>
      <div><span class="lbl">${esc(t("GDP per person"))}</span><b>${money(perCap)}</b>${
        usPerCap ? `<small class="${perCap >= usPerCap ? "good" : "bad"}">${esc(t("Serbia {v}", { v: money(usPerCap) }))}</small>` : ""}</div>
      <div><span class="lbl">${esc(t("Share of Serbia's GDP"))}</span><b>${c.gdp != null && n.gdp ? pct(c.gdp / n.gdp, 2) : "–"}</b><small>${esc(t("{v} of people", { v: pct(c.population / n.population, 2) }))}</small></div>
    </div>
    <h4 class="cv-h4">${esc(t("Yields"))} <span class="muted">${esc(t("rank among cities"))}</span></h4>
    <div class="cv-yields">${yields}</div>
    <h4 class="cv-h4">${esc(t("GDP by industry"))} <span class="muted">${esc(t("tick = national share"))}</span></h4>
    ${gi.length ? `<div class="cv-inds">${gi.slice(0, 8).map(gdpRow).join("")}</div>
      ${gi.length > 8 ? `<details class="cv-more"><summary>${esc(t("All {n} industries", { n: gi.length }))}</summary><div class="cv-inds">${gi.slice(8).map(gdpRow).join("")}</div></details>` : ""}`
      : `<p class="muted cv-note">${esc(t("No industry breakdown for this city."))}</p>`}
    <p class="cv-note">${esc([
      t("{vintage}, current euros, counted where the work is done; shares are of the city's total GDP. ×N = the industry's share of GDP compared with its share of Serbia's GDP.", { vintage: nat.gdp_vintage || t("GDP by municipality") }),
      gi.some((d) => d.estimated) ? t("≈ An estimate: the okrug's (or KiM's) value added by activity, shared out by employees and scaled to GDP.") : "",
      gi.some((d) => d.undisclosed) ? t("Undisclosed = GDP the statistics office withholds for confidentiality.") : "",
    ].filter(Boolean).join(" "))}</p>
  </section>`;
}

// --- workforce -----------------------------------------------------------------------------------------------------
function workforce(m) {
  const cards = m.inds.map((d) => {
    const spec = d.lq != null && d.lq >= 1.25;
    return `<div class="cv-bld${spec ? " spec" : ""}" title="${esc(t("{industry}: {count} residents work here ({share}; Serbia {national})", { industry: d.label, n: d.jobs, count: int(d.jobs), share: pct(d.share), national: pct(d.natShare) }))}">
      ${medallion(d.icon, "•", d.color, 17)}
      <div class="cv-bld-t"><span class="cv-bld-n">${esc(d.short)}</span>
        <span class="cv-bld-v">${compact(d.jobs)} <small>${pct(d.share, 1)}</small></span></div>
      ${lqBadge(d.lq)}
    </div>`;
  }).join("");
  return `
  <section class="cv-sec" id="cv-workforce" data-sec="workforce" aria-labelledby="cv-h-workforce">
    <h3 id="cv-h-workforce">${icon("y-production", "⚙️", { size: 15 })}${esc(t("Workforce"))}</h3>
    <p class="cv-lead">${t("Where the city's {count} employed residents work, by industry. {lq} compares an industry's share of jobs with its national share.", { n: m.city.employed, count: int(m.city.employed), lq: '<span class="cv-lq hi">×N</span>' })}</p>
    <div class="cv-blds">${cards || `<p class="muted cv-note">${esc(t("No industry data."))}</p>`}</div>
    <p class="cv-note">${esc(t("{vintage}: employed residents by activity, counted where they live.", { vintage: m.nation.vintage }))}</p>
  </section>`;
}

// --- resources -----------------------------------------------------------------------------------------------------
function resources(m) {
  const list = m.sites.map((s, k) => {
    const type = s.type;
    const val = resourceValue(s.item, type, compact);
    const name = placeName(s.item);
    return `<button type="button" class="cv-site" data-site="${k}" title="${esc(t("Fly to {name}", { name }))}">
      <span class="cv-med" style="--bg:${esc(type?.color || "#3a4a5e")}">${glyph(type, 16)}</span>
      <span class="cv-site-t"><b>${esc(name)}</b><small>${esc(type?.name || s.item.type)}${s.item.state ? ` · ${esc(s.item.state)}` : ""}</small>
        ${s.item.detail ? `<small class="cv-site-d">${esc(s.item.detail)}</small>` : ""}</span>
      <span class="cv-site-v">${esc(val)}<i aria-hidden="true">›</i></span>
    </button>`;
  }).join("");
  const cats = {};
  for (const s of m.sites) cats[s.type?.category || "other"] = (cats[s.type?.category || "other"] || 0) + 1;
  const mw = m.sites.filter((s) => s.type?.unit === "MW").reduce((a, s) => a + (s.item.value || 0), 0);
  const nSites = m.sites.length;
  const power = mw >= 1000 ? t("{v} GW", { v: num(mw / 1000, 1) }) : t("{v} MW", { v: int(mw) });
  const summary = nSites
    ? `<p class="cv-lead">${esc(nSites === 1 ? t("{n} mapped site", { n: nSites }) : t("{n} mapped sites", { n: nSites }))}${
      mw ? ` · ${esc(t("{power} of mapped generating capacity", { power }))}` : ""}. ${esc(t("Click one to fly there."))}</p>`
    : `<p class="muted cv-note">${esc(t("No mapped resource sites in this city. Only large sites are mapped (each type has a size threshold)."))}</p>`;
  return `
  <section class="cv-sec" id="cv-resources" data-sec="resources" aria-labelledby="cv-h-resources">
    <h3 id="cv-h-resources">${icon("resources", "⛏️", { size: 15 })}${esc(t("Resources"))}</h3>
    ${summary}
    <div class="cv-sites">${list}</div>
    ${m.sites.length ? `<p class="cv-note">${esc(t("Sites whose hex centre lies in one of the city's municipalities. Mapped sites only, not the city's full capacity."))}</p>` : ""}
  </section>`;
}

// --- compare -------------------------------------------------------------------------------------------------------
const COMPARE = {
  size: [
    [t("Population"), (c) => c.population, (v) => popShort(v)],
    [t("GDP / person"), (c) => (c.gdp != null && c.population ? c.gdp / c.population : null), money],
    [t("Wage"), (c) => c.median_income, money],
    [t("Growth"), (c) => (Number.isFinite(c.growth) ? c.growth : null), (v) => signed(v)],
  ],
  housing: [
    [t("Jobless"), (c) => c.unemployment, (v) => pct(v)],
  ],
};

export function compareTable(m, set = "size") {
  const rows = [m.city, ...m.peers];
  const cols = COMPARE[set] || COMPARE.size;
  const max = cols.map(([, f]) => Math.max(...rows.map((c) => Math.abs(f(c) ?? 0))) || 1);
  return `<div class="cv-cmp" role="table" aria-label="${esc(t("{city} and its peers", { city: placeName(m.city) }))}">
    <div class="cv-cmp-r cv-cmp-h" role="row"><span role="columnheader">${esc(t("City"))}</span>${cols.map(([l]) => `<span role="columnheader">${esc(l)}</span>`).join("")}</div>
    ${rows.map((c, k) => `<div class="cv-cmp-r${k === 0 ? " me" : ""}" role="row">
      <span role="cell">${k === 0 ? `<b class="cv-cmp-n">${esc(placeName(c))}</b>` : `<button type="button" class="cv-cmp-n" data-peer="${esc(c.id)}" title="${esc(t("Open {city} in the City View", { city: c.full ? placeName({ name: c.full, name_lat: c.full_lat }) : placeName(c) }))}">${esc(placeName(c))}</button>`}<small>${esc((c.states || []).join("–"))}</small></span>
      ${cols.map(([, f, fmt], j) => {
        const v = f(c);
        const col = v != null && v < 0 ? "#f08a6a" : k === 0 ? "#ecd08e" : "#8fa6bd";
        return `<span role="cell"><em>${v == null ? "–" : esc(fmt(v))}</em>${bar(v == null ? 0 : Math.abs(v) / max[j], col)}</span>`;
      }).join("")}
    </div>`).join("")}
  </div>`;
}

function compare(m) {
  return `
  <section class="cv-sec" id="cv-compare" data-sec="compare" aria-labelledby="cv-h-compare">
    <h3 id="cv-h-compare">${icon("layers", "⚖️", { size: 15 })}${esc(t("Compare"))}</h3>
    <p class="cv-lead">${esc(t("The {n} cities closest in population. Click one to open it.", { n: m.peers.length }))}</p>
    <div class="cv-seg" role="group" aria-label="${esc(t("Metrics"))}">
      <button type="button" data-set="size" aria-pressed="true">${esc(t("Size & wealth"))}</button>
      <button type="button" data-set="housing" aria-pressed="false">${esc(t("Jobs"))}</button>
    </div>
    <div data-compare>${compareTable(m, "size")}</div>
  </section>`;
}

function footer(m) {
  const nat = m.nation;
  const sources = nat.gdp_vintage ? t("{vintage}; GDP: {gdp}", { vintage: nat.vintage, gdp: nat.gdp_vintage }) : nat.vintage;
  return `<div class="cv-foot">${esc(t("Sources: {sources}. Ranks are among all {count} cities on the map.", { sources, n: m.cityList.length, count: int(m.cityList.length) }))}
    <a href="#" data-pedia>${esc(t("Almanac"))} ›</a></div>`;
}

/**
 * Fill the dock. handlers: {onClose, onState(idx), onPeer(id), onSite(site), onSiteHover(site|null), onPedia,
 * loadCounties() → Promise<counties.json|null>, loadData(name) → Promise<data|null>, onDistricts(list)} (the
 * metro's districts once districts.json is in, for the map plaques).
 */
/**
 * Scrolls the dock to a section (its tab id, e.g. "districts"). Citizens and districts arrive later and change the
 * heights above, so the section is re-aligned as they do, for up to 4 s or until the user scrolls themselves.
 */
export function goToSection(el, id) {
  const sec = el?.querySelector(`[data-sec="${id}"]`);
  if (!sec) return false;
  const align = () => {
    const nav = el.querySelector(".cv-tabs");
    el.scrollTop = Math.max(0, sec.offsetTop - (nav?.offsetHeight || 0) - 4);
    el.onscroll?.(); // the tab spy (a scroll event is not always sent for a programmatic jump)
  };
  align();
  let ro = null;
  const stop = () => {
    ro?.disconnect();
    ro = null;
    for (const type of ["wheel", "touchstart", "keydown", "pointerdown"]) el.removeEventListener(type, stop);
  };
  for (const type of ["wheel", "touchstart", "keydown", "pointerdown"]) el.addEventListener(type, stop, { passive: true });
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(() => { if (sec.isConnected) align(); else stop(); });
    for (const c of el.children) ro.observe(c);
  }
  setTimeout(stop, 4000);
  return true;
}

export function render(el, m, h) {
  el.classList.add("cv-dock");
  el.style.setProperty("--sc", css(m.stateRGB));
  el.innerHTML = header(m) + citizens(m) + districts(m) + economy(m) + workforce(m) + resources(m) + compare(m) + footer(m);
  el.scrollTop = 0;

  el.querySelector("[data-close]").onclick = () => h.onClose();
  el.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => h.onState(+b.dataset.state)));
  el.querySelector("[data-pedia]").onclick = (e) => { e.preventDefault(); h.onPedia(); };

  // Sites: hover lights the hex on the map, click flies there.
  el.querySelectorAll("[data-site]").forEach((b) => {
    const s = m.sites[+b.dataset.site];
    b.onclick = () => h.onSite(s);
    b.onmouseenter = b.onfocus = () => h.onSiteHover(s);
    b.onmouseleave = b.onblur = () => h.onSiteHover(null);
  });

  // Compare: metric sets and peer links (delegated, the table is re-rendered).
  const cmp = el.querySelector("[data-compare]");
  el.querySelectorAll("[data-set]").forEach((b) => (b.onclick = () => {
    el.querySelectorAll("[data-set]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    cmp.innerHTML = compareTable(m, b.dataset.set);
  }));
  cmp.addEventListener("click", (e) => {
    const b = e.target.closest("[data-peer]");
    if (b) h.onPeer(b.dataset.peer);
  });

  // Tabs scroll to their section; the active tab follows the scroll position.
  const nav = el.querySelector(".cv-tabs");
  const tabs = [...el.querySelectorAll("[data-tab]")];
  const secs = tabs.map((tab) => el.querySelector(`[data-sec="${tab.dataset.tab}"]`));
  tabs.forEach((tab, k) => (tab.onclick = () => {
    const top = secs[k].offsetTop - nav.offsetHeight - 4;
    el.scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }));
  const spy = () => {
    const y = el.scrollTop + nav.offsetHeight + 24;
    let k = 0;
    secs.forEach((s, j) => { if (s.offsetTop <= y) k = j; });
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 4) k = secs.length - 1;
    tabs.forEach((tab, j) => tab.classList.toggle("on", j === k));
  };
  el.onscroll = spy;
  spy();

  // Citizens and districts arrive with their files (each loaded once, on demand).
  const czHost = el.querySelector("[data-citizens]");
  Promise.resolve(h.loadData?.("citizens")).then((data) => {
    if (!czHost.isConnected) return;
    czHost.innerHTML = citizensHtml(m, data ?? null);
    mountCitizens(czHost, m, data);
  }, () => { if (czHost.isConnected) czHost.innerHTML = citizensHtml(m, null); });
  const dHost = el.querySelector("[data-districts]");
  const typeSlot = el.querySelector("[data-ctype]");
  Promise.all([h.loadData?.("districts"), Promise.resolve(h.loadData?.("military")).catch(() => null)]).then(([dd, mil]) => {
    if (!dHost.isConnected) return;
    dHost.innerHTML = districtsHtml(m, dd ?? null, mil ?? null);
    typeSlot.innerHTML = badgeHtml(m, dd ?? null);
    h.onDistricts?.(dd ? cityDistricts(dd, mil, m.city.id) : []);
  }, () => { if (dHost.isConnected) dHost.innerHTML = districtsHtml(m, null, null); });

  // Member counties arrive with counties.json (loaded once, on demand).
  const host = el.querySelector("[data-counties]");
  Promise.resolve(h.loadCounties()).then((data) => {
    if (host.isConnected) host.innerHTML = countiesTable(m, data);
  }, () => { if (host.isConnected) host.innerHTML = `<p class="muted cv-note">${esc(t("Municipality table not available."))}</p>`; });
}
