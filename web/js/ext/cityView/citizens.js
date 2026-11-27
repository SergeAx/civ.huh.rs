// City View "Citizens" rows: the metro's people as rows of small figures (citizens.json, ACS 1-year).
//
//   citizensHtml(m, data) → HTML      the rows (placeholders for the figure canvases)
//   mountCitizens(host, m, data)       paints the figures and wires the hover / focus read-out
//
// Each row: N figures (workforce 20, ages, faith and peoples 10 from the file; education 10, rounded here with
// the same largest-remainder method), a caption ("each figure ≈ 72K workers"), a read-out line that a hovered or
// focused figure fills ("1 in 4 workers in Novi Sad is a professional (Serbia: 1 in 6)"), and a
// thin national bar for comparison. A row the census left out is said so, never drawn as zeros.
import { esc, int, num, pct } from "../../format.js";
import { compact, pluralOf } from "./fmt.js";
import { CATEGORY_COLOR, figureCanvas, loadPainter } from "./figures.js";
import { t, placeName } from "../../i18n.js";

const ROWS = [
  { id: "workforce", title: t("Workforce"), sub: t("by occupation"), noun: "workers", n: null },
  { id: "age", title: t("Generations"), sub: t("by age"), noun: "residents", n: null },
  { id: "faith", title: t("Faith"), sub: t("declared religion"), noun: "residents", n: null },
  { id: "education", title: t("Education"), sub: t("residents 15 and over"), noun: "adults", n: 10 },
  { id: "people", title: t("Peoples"), sub: t("declared national community"), noun: "residents", n: null },
];

// What the row's figures count, in its caption and in the standout call-out.
const NOUN = {
  workers: {
    each: (v) => t("Each figure ≈ {v} workers", v),
    standout: (v) => t("{share} of workers here, {national} nationally: {ratio}× the national share.", v),
  },
  residents: {
    each: (v) => t("Each figure ≈ {v} residents", v),
    standout: (v) => t("{share} of residents here, {national} nationally: {ratio}× the national share.", v),
  },
  adults: {
    each: (v) => t("Each figure ≈ {v} residents 15+", v),
    standout: (v) => t("{share} of residents 15+ here, {national} nationally: {ratio}× the national share.", v),
  },
};

// [singular, plural] read-out sentences per category: "1 in 7 workers in X is …" / "3 in 10 workers in X are …".
const SENTENCE = {
  workforce: {
    executive: [(v) => t("{ratio} workers in {city} is a manager", v), (v) => t("{ratio} workers in {city} are managers", v)],
    scholar: [(v) => t("{ratio} workers in {city} is a professional: a doctor, teacher, engineer, lawyer or scientist", v), (v) => t("{ratio} workers in {city} are professionals: doctors, teachers, engineers, lawyers or scientists", v)],
    engineer: [(v) => t("{ratio} workers in {city} is a technician or associate professional", v), (v) => t("{ratio} workers in {city} are technicians or associate professionals", v)],
    clerk: [(v) => t("{ratio} workers in {city} works in an office", v), (v) => t("{ratio} workers in {city} work in offices", v)],
    service: [(v) => t("{ratio} workers in {city} works in services, sales or security", v), (v) => t("{ratio} workers in {city} work in services, sales or security", v)],
    farmer: [(v) => t("{ratio} workers in {city} farms, fishes or works in forestry", v), (v) => t("{ratio} workers in {city} farm, fish or work in forestry", v)],
    builder: [(v) => t("{ratio} workers in {city} builds, installs or repairs", v), (v) => t("{ratio} workers in {city} build, install or repair", v)],
    maker: [(v) => t("{ratio} workers in {city} works in a factory, transport or a warehouse", v), (v) => t("{ratio} workers in {city} work in factories, transport or warehouses", v)],
  },
  age: {
    child: [(v) => t("{ratio} residents in {city} is a child (under 15)", v), (v) => t("{ratio} residents in {city} are children (under 15)", v)],
    young: [(v) => t("{ratio} residents in {city} is young (15–29)", v), (v) => t("{ratio} residents in {city} are young (15–29)", v)],
    midlife: [(v) => t("{ratio} residents in {city} is of working age (30–64)", v), (v) => t("{ratio} residents in {city} are of working age (30–64)", v)],
    elder: [(v) => t("{ratio} residents in {city} is 65 or older", v), (v) => t("{ratio} residents in {city} are 65 or older", v)],
  },
  faith: {
    orthodox: [(v) => t("{ratio} residents in {city} is Orthodox", v), (v) => t("{ratio} residents in {city} are Orthodox", v)],
    catholic: [(v) => t("{ratio} residents in {city} is Catholic", v), (v) => t("{ratio} residents in {city} are Catholic", v)],
    protestant: [(v) => t("{ratio} residents in {city} is Protestant", v), (v) => t("{ratio} residents in {city} are Protestant", v)],
    islam: [(v) => t("{ratio} residents in {city} is Muslim by religion", v), (v) => t("{ratio} residents in {city} are Muslim by religion", v)],
    other: [(v) => t("{ratio} residents in {city} follows another religion", v), (v) => t("{ratio} residents in {city} follow other religions", v)],
    none: [(v) => t("{ratio} residents in {city} declares no religion", v), (v) => t("{ratio} residents in {city} declare no religion", v)],
  },
  education: {
    none: [(v) => t("{ratio} residents 15+ in {city} has not finished primary school", v), (v) => t("{ratio} residents 15+ in {city} have not finished primary school", v)],
    primary: [(v) => t("{ratio} residents 15+ in {city} has finished primary school only", v), (v) => t("{ratio} residents 15+ in {city} have finished primary school only", v)],
    secondary: [(v) => t("{ratio} residents 15+ in {city} has finished secondary school", v), (v) => t("{ratio} residents 15+ in {city} have finished secondary school", v)],
    tertiary: [(v) => t("{ratio} residents 15+ in {city} has a college or university degree", v), (v) => t("{ratio} residents 15+ in {city} have a college or university degree", v)],
  },
  people: {
    serbs: [(v) => t("{ratio} residents in {city} is a Serb", v), (v) => t("{ratio} residents in {city} are Serbs", v)],
    albanians: [(v) => t("{ratio} residents in {city} is an Albanian", v), (v) => t("{ratio} residents in {city} are Albanians", v)],
    hungarians: [(v) => t("{ratio} residents in {city} is a Hungarian", v), (v) => t("{ratio} residents in {city} are Hungarians", v)],
    bosniaks: [(v) => t("{ratio} residents in {city} is a Bosniak", v), (v) => t("{ratio} residents in {city} are Bosniaks", v)],
    slovaks: [(v) => t("{ratio} residents in {city} is a Slovak", v), (v) => t("{ratio} residents in {city} are Slovaks", v)],
    bulgarians: [(v) => t("{ratio} residents in {city} is a Bulgarian", v), (v) => t("{ratio} residents in {city} are Bulgarians", v)],
    other: [(v) => t("{ratio} residents in {city} belongs to another community", v), (v) => t("{ratio} residents in {city} belong to other communities", v)],
  },
};

// Short legend labels (the file's labels are long).
const SHORT = {
  workforce: { executive: t("Managers"), scholar: t("Professionals"), engineer: t("Technicians"), clerk: t("Clerks"),
    service: t("Service & sales"), farmer: t("Farm"), builder: t("Builders"), maker: t("Makers & movers") },
  age: { child: t("Under 15"), young: "15–29", midlife: "30–64", elder: "65+" },
  faith: { orthodox: t("Orthodox"), catholic: t("Catholic"), protestant: t("Protestant"), islam: t("Islam"), other: t("Other"),
    none: t("No religion") },
  education: { none: t("No primary"), primary: t("Primary"), secondary: t("Secondary"), tertiary: t("Degree") },
  people: { serbs: t("Serbs"), albanians: t("Albanians"), hungarians: t("Hungarians"), bosniaks: t("Bosniaks"), slovaks: t("Slovaks"),
    bulgarians: t("Bulgarians"), other: t("Other") },
};

/** Largest-remainder rounding of counts into n figures (the pipeline's method, for rows without figures). */
export function largestRemainder(counts, keys, n) {
  const tot = keys.reduce((a, k) => a + (counts[k] || 0), 0);
  if (!(tot > 0)) return null;
  const raw = keys.map((k) => ((counts[k] || 0) / tot) * n);
  const out = raw.map(Math.floor);
  let left = n - out.reduce((a, v) => a + v, 0);
  const order = raw.map((v, j) => [v - Math.floor(v), j]).sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (let k = 0; k < left; k++) out[order[k][1]]++;
  return Object.fromEntries(keys.map((k, j) => [k, out[j]]));
}

/** "1 in 7", "3 in 10", "fewer than 1 in 1,000". */
export function oneIn(share) {
  if (share == null || !Number.isFinite(share)) return null;
  if (share <= 0) return { text: t("{k} in 10", { k: 0 }), plural: true };
  if (share < 0.001) return { text: t("fewer than 1 in 1,000"), plural: false };
  if (share >= 0.3) {
    const k = Math.round(share * 10);
    return k >= 10 ? { text: t("more than 9 in 10"), plural: true } : { text: t("{k} in 10", { k }), plural: k !== 1 };
  }
  return { text: t("1 in {d}", { d: int(Math.round(1 / share)) }), plural: false };
}

function sentence(rowId, key, share, natShare, city, group) {
  const a = oneIn(share);
  if (!a) return "";
  const forms = SENTENCE[rowId]?.[key];
  const v = { ratio: a.text, city, group };
  let s = forms ? forms[a.plural ? 1 : 0](v) : t("{group}: {ratio} in {city}", v);
  const us = oneIn(natShare);
  if (us) s = t("{sentence} (Serbia: {ratio})", { sentence: s, ratio: us.text });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function rowModel(rowDef, row, nat, groups, figuresN) {
  const keys = (groups[rowDef.id] || []).map((g) => g.key);
  const n = figuresN[rowDef.id] ?? rowDef.n ?? 10;
  const figs = row.figures || largestRemainder(row.counts || {}, keys, n);
  const natFigs = nat?.figures || (nat ? largestRemainder(nat.counts || {}, keys, n) : null);
  return { keys, n, figs, natFigs };
}

// Specialists by row/key from the file (ratios from unrounded shares).
function specMap(city) {
  const m = new Map();
  for (const s of city?.specialists || []) m.set(`${s.row}|${s.key}`, s);
  return m;
}

/** The Citizens rows. data = citizens.json (or null / undefined while loading). */
export function citizensHtml(m, data) {
  const c = m.city;
  if (data === undefined) return `<p class="muted cv-note">${esc(t("Loading the citizen mix…"))}</p>`;
  if (!data || !data.cities) return `<p class="muted cv-note">${esc(t("The citizen mix is not available."))}</p>`;
  const row0 = data.cities[c.id];
  const vintage = data.vintage || "";
  if (!row0) {
    return `<p class="muted cv-note">${esc(t("Census published none of the citizen tables for {city} in the {vintage} release (it leaves out small areas), so there are no citizen figures here.", { city: placeName(c), vintage }))}</p>`;
  }
  const nat = data.national || {};
  const groups = data.groups || {};
  const specs = specMap(row0);
  const label = Object.fromEntries(Object.entries(groups).map(([r, gs]) => [r, Object.fromEntries(gs.map((g) => [g.key, g.label]))]));

  // Headline: mean age, degrees, elders, and the "great person" call-out (the strongest specialist).
  const med = row0.age?.mean, usMed = nat.age?.mean;
  const ba = row0.education?.bachelors_plus, usBa = nat.education?.bachelors_plus;
  const fb = row0.age?.shares?.elder, usFb = nat.age?.shares?.elder;
  const chip = (v, us, fmt, lbl, tip) => (v == null ? "" : `<div class="cv-cz-chip" title="${esc(tip)}"><b>${fmt(v)}</b><span>${esc(lbl)}</span>${us != null ? `<small>${esc(t("Serbia {v}", { v: fmt(us) }))}</small>` : ""}</div>`);
  const top = (row0.specialists || []).find((s) => s.ratio >= (data.rule?.specialist_high ?? 1.5));
  const topRow = ROWS.find((r) => r.id === top?.row);
  const great = top && topRow ? `<div class="cv-great" style="--fc:${esc(CATEGORY_COLOR[top.row]?.[top.key] || "#c9a45c")}">
      <span class="cv-great-fig" data-great="${esc(top.row)}|${esc(top.key)}" aria-hidden="true"></span>
      <div><small>${esc(t("Standout citizens"))}</small><b>${esc(label[top.row]?.[top.key] || top.key)}</b>
      <span>${esc(NOUN[topRow.noun].standout({ share: pct(top.share, 1), national: pct(top.national, 1), ratio: num(top.ratio, 1) }))}</span></div></div>` : "";

  const rows = ROWS.map((rd) => {
    const row = row0[rd.id];
    const head = `<div class="cv-cz-h"><b>${esc(rd.title)}</b><span>${esc(rd.sub)}</span></div>`;
    if (!row) {
      return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}
        <p class="muted cv-note">${esc(t("Census did not publish this table for {city} in the {vintage} release, so this row is left out.", { city: placeName(c), vintage }))}</p></div>`;
    }
    const { keys, n, figs, natFigs } = rowModel(rd, row, nat[rd.id], groups, data.figures || {});
    if (!figs) return `<div class="cv-cz-row missing" data-row="${rd.id}">${head}<p class="muted cv-note">${esc(t("No counts for this row."))}</p></div>`;
    const per = row.total / n;
    const cells = [];
    for (const k of keys) {
      for (let j = 0; j < (figs[k] || 0); j++) {
        const sp = specs.get(`${rd.id}|${k}`);
        const mark = sp ? (sp.ratio >= 1 ? "up" : "down") : "";
        // One tab stop per category (its first figure), not one per figure.
        cells.push(`<span class="cv-fig${mark ? ` ${mark}` : ""}" tabindex="${j ? -1 : 0}" role="img" data-k="${esc(k)}" aria-label="${esc(label[rd.id]?.[k] || k)}"></span>`);
      }
    }
    // Legend: every category, with its share, the national share and a chevron for specialists. Categories that
    // round to no figure are still listed (greyed), so nothing silently disappears.
    const legend = keys.map((k) => {
      const sh = row.shares?.[k], us = nat[rd.id]?.shares?.[k];
      const sp = specs.get(`${rd.id}|${k}`);
      const chev = sp ? `<em class="${sp.ratio >= 1 ? "up" : "down"}" title="${esc(t("{ratio}× the national share", { ratio: num(sp.ratio, 1) }))}">${sp.ratio >= 1 ? "▲" : "▼"}</em>` : "";
      const tip = `${label[rd.id]?.[k] || k}: ${sh != null ? pct(sh, 1) : "–"}${us != null ? ` ${t("(Serbia {v})", { v: pct(us, 1) })}` : ""}${figs[k] ? "" : `. ${t("Rounds to no figure.")}`}`;
      return `<span class="cv-cz-k${figs[k] ? "" : " zero"}" data-k="${esc(k)}" title="${esc(tip)}"><i style="background:${esc(CATEGORY_COLOR[rd.id]?.[k] || "#888")}"></i>${esc(SHORT[rd.id]?.[k] || k)} <small>${sh != null ? pct(sh, 0) : "–"}</small>${chev}</span>`;
    }).join("");
    // National comparison bar (shares), aligned with the figures' order.
    const usBar = nat[rd.id]?.shares ? `<div class="cv-cz-us" title="${esc(t("National mix, same order"))}"><span>${esc(t("SRB"))}</span><div>${keys.map((k) => {
      const s = nat[rd.id].shares[k] || 0;
      return s > 0 ? `<i style="flex:${s};background:${esc(CATEGORY_COLOR[rd.id]?.[k] || "#888")}" title="${esc(t("{group}: {v} in Serbia", { group: SHORT[rd.id]?.[k] || k, v: pct(s, 1) }))}"></i>` : "";
    }).join("")}</div></div>` : "";
    const cap = [NOUN[rd.noun].each({ n: pluralOf(per), v: compact(per) }), t("{v} in all", { v: compact(row.total) }), rd.n && !row.figures ? t("rounded here") : ""]
      .filter(Boolean).join(" · ");
    const extra = rd.id === "age" && med != null
      ? ` · ${usMed != null ? t("mean age {v} (Serbia {national})", { v: num(med, 1), national: num(usMed, 1) }) : t("mean age {v}", { v: num(med, 1) })}` : "";
    const figsLabel = keys.filter((k) => figs[k]).map((k) => t("{count} of {total} {group}", { count: figs[k], total: n, group: SHORT[rd.id]?.[k] || k })).join(", ");
    return `<div class="cv-cz-row" data-row="${rd.id}" style="--n:${n}">${head}
      <div class="cv-figs" role="group" aria-label="${esc(rd.title)}: ${esc(figsLabel)}">${cells.join("")}</div>
      ${usBar}
      <div class="cv-cz-out" aria-live="polite" data-default="${esc(cap + extra)}">${esc(cap + extra)}</div>
      <div class="cv-cz-legend">${legend}</div>
    </div>`;
  }).join("");

  const unreliable = row0.reliable === false
    ? `<p class="cv-warn">${esc(t("Small area: the 1-year survey's margins of error are large here, so read these figures as rough."))}</p>` : "";
  return `
    <div class="cv-cz-top">
      ${chip(med, usMed, (v) => num(v, 1), t("mean age"), t("Mean age of residents, from the census age groups"))}
      ${chip(ba, usBa, (v) => pct(v, 0), t("have a degree"), t("Residents 15+ with a college or university degree"))}
      ${chip(fb, usFb, (v) => pct(v, 0), t("aged 65+"), t("Residents aged 65 and over"))}
    </div>
    ${great}
    ${unreliable}
    <div class="cv-cz${row0.reliable === false ? " unreliable" : ""}">${rows}</div>
    <p class="cv-note">${esc(t("{vintage}, tables C24010, B01001, C08301, C15003 and B05002. Figures are rounded (largest remainder) so each row adds up; hover or tap a figure for its share. ▲▼ = at least 1.5× or at most 0.67× the national share. Commute counts workers, not all residents.", { vintage }))}</p>`;
}


/** Paint the figure canvases and wire the read-outs. */
export function mountCitizens(host, m, data) {
  if (!host || !data?.cities?.[m.city.id]) return;
  const row0 = data.cities[m.city.id];
  const nat = data.national || {};
  const dpr = Math.min(3, Math.max(1, Math.round((devicePixelRatio || 1) * 2) / 2));
  const paintAll = () => {
    host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
      const rid = rowEl.dataset.row;
      rowEl.querySelectorAll(".cv-fig").forEach((el) => {
        const src = figureCanvas(rid, el.dataset.k, 36, dpr);
        const cv = document.createElement("canvas");
        cv.width = src.width;
        cv.height = src.height;
        cv.getContext("2d").drawImage(src, 0, 0);
        el.replaceChildren(cv);
      });
    });
    const g = host.querySelector("[data-great]");
    if (g) {
      const [rid, k] = g.dataset.great.split("|");
      const src = figureCanvas(rid, k, 36, dpr);
      const cv = document.createElement("canvas");
      cv.width = src.width;
      cv.height = src.height;
      cv.getContext("2d").drawImage(src, 0, 0);
      g.replaceChildren(cv);
    }
  };
  paintAll();
  // Once the citizen painter (render/art/people.js) loads, repaint the figures.
  loadPainter().then(() => { if (host.isConnected) paintAll(); });

  host.querySelectorAll(".cv-cz-row[data-row]").forEach((rowEl) => {
    const rid = rowEl.dataset.row;
    const row = row0[rid];
    const out = rowEl.querySelector(".cv-cz-out");
    if (!row || !out) return;
    const show = (k) => {
      rowEl.querySelectorAll("[data-k]").forEach((el) => el.classList.toggle("lit", el.dataset.k === k));
      rowEl.classList.toggle("focus", !!k);
      if (!k) {
        out.textContent = out.dataset.default;
        out.classList.remove("on");
        return;
      }
      const sh = row.shares?.[k], us = nat[rid]?.shares?.[k];
      const parts = [t("{v} here", { v: sh != null ? pct(sh, 1) : "–" })];
      if (us != null) parts.push(t("{v} in Serbia", { v: pct(us, 1) }));
      if (row.counts?.[k] != null) parts.push(t("≈{v} people", { n: pluralOf(row.counts[k]), v: compact(row.counts[k]) }));
      out.innerHTML = `${esc(sentence(rid, k, sh, us, placeName(m.city), SHORT[rid]?.[k] || k))}<small>${esc(parts.join(" · "))}</small>`;
      out.classList.add("on");
    };
    let pinned = null;
    rowEl.addEventListener("pointerover", (e) => {
      const el = e.target.closest("[data-k]");
      if (el && rowEl.contains(el)) show(el.dataset.k);
    });
    rowEl.addEventListener("pointerleave", () => show(pinned));
    rowEl.addEventListener("focusin", (e) => {
      const el = e.target.closest("[data-k]");
      if (el) show(el.dataset.k);
    });
    rowEl.addEventListener("focusout", () => show(pinned));
    // A tap pins the category (phones have no hover); another tap on it lets go.
    rowEl.addEventListener("click", (e) => {
      const el = e.target.closest("[data-k]");
      if (!el) return;
      pinned = pinned === el.dataset.k ? null : el.dataset.k;
      show(pinned);
    });
  });
}
