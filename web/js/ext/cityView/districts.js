// City View "Districts": the metro's real industry specialisation (districts.json, BLS QCEW) as strategy-game
// districts, plus the Encampment tier from military.json (installations + armed-forces residents).
//
//   cityDistricts(ddata, mil, id) → [district]   the metro's districts, strongest first, each with what the dock and
//                                                the map plaques need ({id, name, short, color, icon, lq, emp, …})
//   badgeOf(ddata, id) → {label, text, color, icon, district} | null | undefined   the city-type badge
//   districtsHtml(m, ddata, mil) → HTML          the section body
//   badgeHtml(m, ddata) → HTML                   the header badge
import { esc, int, num, pct } from "../../format.js";
import { compact, money, pluralOf } from "./fmt.js";
import { icon } from "../../ui/icon.js";
import { hasIcon } from "../../icons.js";
import { t, placeName } from "../../i18n.js";

// Icons the district catalog names (d-*) are not drawn yet; until they are, a near icon from the set stands in,
// and canvas plaques without any icon get the letter in `mark`.
const FALLBACK = {
  campus: ["y-science", "🎓"], commercial_hub: ["i-finance", "💰"], industrial_zone: ["i-manufacturing", "🏭"],
  harbor: ["i-transportation", "⚓"], theater_square: ["i-arts", "🎭"], entertainment_complex: ["i-accommodation", "🎡"],
  aerodrome: ["i-transportation", "✈️"], government_plaza: ["i-public_admin", "🏛"], encampment: [null, "⛺"],
  aqueduct: ["i-utilities", "💧"],
};
const SHORT = {
  campus: t("Campus"), commercial_hub: t("Commerce"), industrial_zone: t("Industrial zone"), harbor: t("Harbor"), theater_square: t("Theater"),
  entertainment_complex: t("Leisure"), aerodrome: t("Aerodrome"), government_plaza: t("Gov. plaza"), encampment: t("Encampment"),
  aqueduct: t("Aqueduct"),
};
const TIER = { garrison: t("Garrison"), fortress: t("Fortress") };

const catCache = new WeakMap();
function catalog(ddata) {
  let m = catCache.get(ddata);
  if (!m) catCache.set(ddata, (m = new Map((ddata?.catalog || []).map((c) => [c.id, c]))));
  return m;
}

export function iconFor(id, cat) {
  if (cat?.icon && hasIcon(cat.icon)) return cat.icon;
  const f = FALLBACK[id]?.[0];
  return f && hasIcon(f) ? f : null;
}

const instCache = new WeakMap();
function installationsById(mil) {
  let m = instCache.get(mil);
  if (!m) instCache.set(mil, (m = new Map((mil?.installations || []).map((i) => [i.id, i]))));
  return m;
}

/**
 * The metro's districts: districts.json entries (strongest first), with military.json's Encampment merged in (its
 * tier label; added at the end when only military.json has one).
 */
export function cityDistricts(ddata, mil, id) {
  const cat = catalog(ddata);
  const row = ddata?.cities?.[id] || null;
  const mc = mil?.cities?.[id] || null;
  const out = [];
  for (const d of row?.districts || []) {
    const c = cat.get(d.id) || {};
    const spec = d.via === "specialty" && d.sub;
    out.push({
      ...d, name: c.name || d.id, color: c.color || "#5a6a7a", icon: iconFor(d.id, c), emoji: FALLBACK[d.id]?.[1] || "◆",
      cat: c, subName: d.sub ? c.sub?.[d.sub] || ddata.industries?.[d.sub]?.title || d.sub : null,
      // The map plaque: a speciality-qualified district is labelled by that speciality (its own LQ is the reason).
      short: spec ? c.sub?.[d.sub] || SHORT[d.id] : SHORT[d.id] || c.name || d.id,
      mapLq: spec ? d.sub_lq : d.lq,
      military: d.id === "encampment" ? mc : null,
    });
  }
  if (mc && !out.some((d) => d.id === "encampment")) {
    const c = cat.get("encampment") || {};
    out.push({
      id: "encampment", name: c.name || t("Encampment"), color: c.color || "#8a4a3a", icon: iconFor("encampment", c), emoji: "⛺",
      cat: c, lq: null, emp: null, short: TIER[mc.tier] || t("Encampment"), mapLq: null, military: mc, militaryOnly: true,
    });
  }
  for (const d of out) {
    if (d.military) d.tierLabel = TIER[d.military.tier] || d.military.tier;
  }
  return out;
}

/** The city-type badge; undefined while districts.json is loading, null when there is none. */
export function badgeOf(ddata, id) {
  if (!ddata) return ddata; // undefined (loading) or null (missing)
  const row = ddata.cities?.[id];
  if (!row) return null;
  if (!row.badge) return { label: t("Diversified"), text: t("No city district passes the rule: no industry group stands out."), color: "#6a7484", icon: null, district: null };
  const c = catalog(ddata).get(row.badge.district) || {};
  return { ...row.badge, color: c.color || "#6a7484", icon: iconFor(row.badge.district, c), emoji: FALLBACK[row.badge.district]?.[1] };
}

export function badgeHtml(m, ddata) {
  const b = badgeOf(ddata, m.city.id);
  if (!b) return "";
  const tip = t("City type: {type} (BLS QCEW {year})", { type: b.text || b.label, year: String(ddata.year || "") });
  return `<span class="cv-type${b.district ? "" : " plain"}" style="--tc:${esc(b.color)}" title="${esc(tip)}">
    <span class="cv-type-ic">${icon(b.icon, b.emoji || "◆", { size: 13 })}</span>${esc(b.label)}</span>`;
}

const ge = (lb) => (lb ? "≥" : "");
const signed = (x) => (x == null ? "–" : `${x >= 0 ? "+" : "−"}${pct(Math.abs(x), 1)}`);

function lqTag(lq, lb, tip) {
  if (lq == null) return "";
  const cls = lq >= 1.25 ? "hi" : lq <= 0.75 ? "lo" : "mid";
  return `<span class="cv-lq ${cls}" title="${esc(tip || t("Location quotient: {lq}× the national share of jobs", { lq: num(lq, 2) }))}">×${ge(lb)}${num(lq, 1)}</span>`;
}

function districtCard(d, row, ddata, mil) {
  const nat = ddata?.national || {};
  const c = d.cat || {};
  const lb = !!d.lower_bound;
  const supTip = !lb ? "" : d.suppressed === 1
    ? t("BLS withheld part of this in {n} member municipality, so it is a lower bound.", { n: d.suppressed })
    : t("BLS withheld part of this in {n} member municipalities, so it is a lower bound.", { n: d.suppressed });
  const facts = [];
  if (d.emp != null) {
    facts.push(`<div><span>${esc(t("Jobs"))}</span><b>${ge(lb)}${compact(d.emp)}</b><small>${d.share != null ? esc(t("{share} of the city", { share: pct(d.share, 1) })) : ""}</small></div>`);
  }
  if (d.avg_pay != null) {
    facts.push(`<div><span>${esc(t("Avg pay"))}</span><b>${money(d.avg_pay)}</b><small>${row?.avg_pay != null ? esc(t("city {pay}", { pay: money(row.avg_pay) })) : ""}</small></div>`);
  }
  if (d.strength != null) {
    facts.push(`<div title="${esc(t("Jobs above the national norm: jobs − jobs ÷ LQ (how city districts are ranked)"))}"><span>${esc(t("Above norm"))}</span><b>${ge(lb)}${compact(Math.max(0, d.strength))}</b><small>${esc(t("jobs"))}</small></div>`);
  }
  let spec = "";
  if (d.sub && d.subName) {
    // the speciality's own withheld flag (districts.json sub_lower_bound; older files: the top-industries row)
    const slb = d.sub_lower_bound ?? !!(row?.top || []).find((it) => it.naics === d.sub)?.lower_bound;
    const name = `<b>${esc(d.subName)}</b>`;
    const lead = d.via === "specialty" ? t("Qualifies through: {name}", { name }) : t("Strongest speciality: {name}", { name });
    const subTip = slb ? t("Location quotient: at least {lq}× the national share (BLS withheld part of it, so it is a lower bound)", { lq: num(d.sub_lq, 2) }) : undefined;
    spec = `<p class="cv-dc-sub">${lead} ${lqTag(d.sub_lq, slb, subTip)}${
      d.sub_emp != null ? ` <small>${esc(t("{v} jobs", { n: pluralOf(d.sub_emp), v: ge(slb) + compact(d.sub_emp) }))}</small>` : ""}${
      d.via === "specialty" && d.lq != null ? `<br><small>${esc(t("The city district's industries as a whole are {lq}× the national share; this speciality alone passes the rule.", { lq: num(d.lq, 2) }))}</small>` : ""}</p>`;
  }
  let milHtml = "";
  if (d.military) {
    const mc = d.military;
    const inst = installationsById(mil);
    const names = (mc.installations || []).map((i) => placeName(inst.get(i))).filter(Boolean);
    const vars = { tier: `<b>${esc(d.tierLabel)}</b>`, n: mc.armed_forces, count: int(mc.armed_forces), share: pct(mc.share, mc.share < 0.01 ? 2 : 1) };
    const more = mc.installation_count - Math.min(5, names.length);
    milHtml = `<div class="cv-dc-mil">
      <p>${mc.naval ? t("{tier} (naval): {count} residents in the armed forces, {share} of people 16 and over.", vars)
        : t("{tier}: {count} residents in the armed forces, {share} of people 16 and over.", vars)}</p>
      ${names.length ? `<p class="cv-dc-inst">${names.slice(0, 5).map((n) => `<span>${esc(n)}</span>`).join("")}${
        more > 0 ? `<small>${esc(t("+{n} more", { n: more }))}</small>` : ""}</p>` : ""}
    </div>`;
  }
  const caveat = c.caveat ? `<p class="cv-dc-cav">${esc(c.caveat)}</p>` : "";
  const title = d.militaryOnly ? `${esc(d.name)} · ${esc(d.tierLabel)}` : d.military ? `${esc(d.name)} · ${esc(d.tierLabel)}` : esc(d.name);
  const lqTip = d.lq != null ? [t("Location quotient: the city's share of jobs in these industries is {lq}× the national share.", { lq: num(d.lq, 2) }), supTip].filter(Boolean).join(" ") : "";
  return `<div class="cv-dc" style="--dc:${esc(d.color)}" title="${esc([c.description, supTip].filter(Boolean).join(" "))}">
    <div class="cv-dc-h"><span class="cv-dc-hex">${icon(d.icon, d.emoji, { size: 18 })}</span>
      <div class="cv-dc-t"><b>${title}</b><small>${esc(c.description || "")}</small></div>
      ${d.lq != null ? lqTag(d.lq, lb, lqTip) : ""}</div>
    ${facts.length ? `<div class="cv-dc-f">${facts.join("")}</div>` : ""}
    ${spec}${milHtml}${caveat}
  </div>`;
}

function topTable(row, ddata) {
  const top = row?.top || [];
  if (!top.length) return "";
  const max = Math.max(...top.map((it) => it.lq || 0), 1);
  const head = esc(t("Most specialised industries"));
  return `<h4 class="cv-h4">${head} <span class="muted">${esc(t("by location quotient"))}</span></h4>
  <div class="cv-top" role="table" aria-label="${head}">
    <div class="cv-top-r cv-top-hd" role="row"><span role="columnheader">${esc(t("Industry"))}</span><span role="columnheader">${esc(t("Jobs"))}</span><span role="columnheader">${esc(t("×SRB"))}</span><span role="columnheader">${esc(t("Pay"))}</span><span role="columnheader">${esc(t("1 yr"))}</span></div>
    ${top.map((it) => {
      const title = ddata.industries?.[it.naics]?.title || `NAICS ${it.naics}`;
      const lb = !!it.lower_bound;
      const lower = !lb ? "" : it.suppressed === 1
        ? t("Lower bound: BLS withheld it in {n} member municipality.", { n: it.suppressed })
        : t("Lower bound: BLS withheld it in {n} member municipalities.", { n: it.suppressed });
      return `<div class="cv-top-r" role="row" title="${esc(title)} (NAICS ${esc(it.naics)})${lower ? `. ${esc(lower)}` : ""}">
        <span role="cell" class="cv-top-n">${esc(title)}<i style="width:${((Math.log(1 + (it.lq || 0)) / Math.log(1 + max)) * 100).toFixed(1)}%"></i></span>
        <span role="cell">${ge(lb)}${compact(it.emp)}</span>
        <span role="cell"><b>${it.lq != null ? `${ge(lb)}${num(it.lq, 1)}` : "–"}</b></span>
        <span role="cell">${money(it.avg_pay)}</span>
        <span role="cell" class="${it.oty_pct == null ? "" : it.oty_pct >= 0 ? "good" : "bad"}">${signed(it.oty_pct)}</span></div>`;
    }).join("")}
  </div>`;
}

/** The Districts section body. ddata: districts.json (undefined while loading, null when missing). */
export function districtsHtml(m, ddata, mil) {
  if (ddata === undefined) return `<p class="muted cv-note">${esc(t("Loading city districts…"))}</p>`;
  if (!ddata) return `<p class="muted cv-note">${esc(t("City district data is not available."))}</p>`;
  const id = m.city.id;
  const row = ddata.cities?.[id] || null;
  const list = cityDistricts(ddata, mil, id);
  const b = badgeOf(ddata, id);
  let lead;
  if (!row) {
    lead = `<p class="cv-lead">${esc(t("BLS publishes no municipal employment for {city}'s member municipalities, so it has no industry districts.", { city: placeName(m.city) }))}</p>`;
  } else {
    const vars = { n: row.emp, jobs: int(row.emp), pay: money(row.avg_pay), national: money(ddata.national?.avg_pay) };
    const from = row.counties ? { ...vars, a: row.counties[0], b: row.counties[1] } : null;
    const counted = !from ? t("{jobs} jobs counted, average pay {pay} (Serbia {national}).", vars)
      : from.b === 1 ? t("{jobs} jobs counted from {a} of {b} member municipality, average pay {pay} (Serbia {national}).", from)
        : t("{jobs} jobs counted from {a} of {b} member municipalities, average pay {pay} (Serbia {national}).", from);
    lead = `<p class="cv-lead">${b?.district ? `<b class="cv-type-l" style="--tc:${esc(b.color)}">${esc(b.label)}</b> · ${esc(b.text || "")}. ` : ""}${esc(counted)}</p>`;
  }
  const cards = list.length
    ? `<div class="cv-dcs">${list.map((d) => districtCard(d, row, ddata, mil)).join("")}</div>`
    : row ? `<p class="muted cv-note">${esc(t("No city district passes the rule here: the city's jobs are spread like the nation's."))}</p>` : "";
  const milRule = mil?.rule && list.some((d) => d.military) ? `<p><b>${esc(t("Encampment tier"))}</b> (military.json): ${esc(mil.rule)}</p>` : "";
  const milVintage = typeof mil?.vintage === "object" ? [mil.vintage.installations, mil.vintage.acs].filter(Boolean).join("; ") : mil?.vintage || "";
  return `${lead}
    ${cards}
    ${topTable(row, ddata)}
    <div class="cv-schematic">
      <p><b>◆</b> ${esc(t("On the map, each city district stands as a plaque on a city hex near the centre. The positions are schematic: they show what the city specialises in, not where the jobs are."))}</p>
    </div>
    <details class="cv-more cv-rule"><summary>${esc(t("How city districts are chosen"))}</summary>
      <p>${esc(ddata.rule?.text || "")}</p>${milRule}
      <p>${esc(t("QCEW counts jobs where the employer is, not where workers live; it leaves out the self-employed, most farm workers, railroads and uniformed military."))}</p>
    </details>
    <p class="cv-note">${esc(t("{vintage}, all ownerships (federal and state only for the Government plaza and Encampment). ×N = location quotient; ≥ = a lower bound (BLS withheld a municipality's figure).", { vintage: ddata.vintage || "BLS QCEW" }))}${
      mil && list.some((d) => d.military) ? ` ${esc(t("Encampment tier: {vintage}.", { vintage: milVintage }))}` : ""}</p>`;
}
