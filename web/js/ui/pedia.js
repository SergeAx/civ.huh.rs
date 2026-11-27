// The Almanac: what every number means and exactly where it comes from.
import { resolveTables } from "../terrain.js";
import { esc, int, num } from "../format.js";
import { t, locale } from "../i18n.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: t("Energy"), mineral: t("Minerals"), agri: t("Agriculture") };
const plain = new Intl.NumberFormat(locale);

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;
  const h4 = (text) => `<h4>${esc(text)}</h4>`;
  const p = (text) => `<p>${esc(text)}</p>`;
  const i = (text) => `<i>${esc(text)}</i>`;
  const b = (text) => `<b>${esc(text)}</b>`;
  const hexKm = Math.round(data.world.grid.radius * 2 * (data.world.km_per_unit ?? 1) * 10) / 10;

  // Keys are page ids (pedia.open("Yields")); the nav and headings show them translated.
  const pages = {
    "About this map": () => `
      ${h2("pedia", "📖", t("About this map"))}
      <p>${t("This is the real Serbia, drawn like a strategy game. Nothing is invented: every tile, city and number comes from public data, listed under {sources}.", { sources: i(t("Sources")) })}</p>
      ${h4(t("How it's built"))}
      ${p(t("Serbia, Kosovo and Metohija included, is projected (Albers equal-area) and cut into {cols}×{rows} hexes, each {size} km corner to corner. Each hex belongs to the district and municipality under its centre. Terrain comes from elevation samples inside each hex.", {
        cols: data.world.grid.cols, rows: data.world.grid.rows, size: num(hexKm, Number.isInteger(hexKm) ? 0 : 1),
      }))}
      <p>${t("{cities} are the municipalities, placed at their seat; their numbers cover the whole municipality, villages included. Belgrade joins its eleven urban municipalities, and Niš, Novi Sad, Požarevac, Vranje and Užice their city municipalities.", { cities: b(t("Cities")) })}</p>
      ${h4(t("Controls"))}
      ${p(t("Drag or arrow keys / WASD to pan · scroll, +/– or double-click to zoom · click a city or a district to open it · / or ⌘K to search · L to cycle lenses · R to show or hide resources · ? for all shortcuts · Esc to close."))}
      <p>${t("The address bar always holds a link to what you're looking at (lens, selection and view); use {share} to copy it or to download a picture.", { share: i(t("Share")) })}</p>`,
    Yields: () => `
      ${h2("y-production", "⚙️", t("Yields"))}
      <p>${t("Civilization's yields mapped onto real measures. Job-based yields count {residents} employed in an industry (where workers live, not where they work). {gold}: output per year, counted where the work is done.", {
        residents: i(t("residents")), gold: b(t("Gold is GDP")),
      })}</p>
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${
        esc(y.key === "gold" ? t("{yield} (GDP)", { yield: t(y.label) }) : t(y.label))}</b><br>${esc(y.description)}</td></tr>`).join("")}</table>
      ${h4(t("Amenities & housing"))}
      ${p(t("Unemployment = unemployed ÷ economically active residents at the census. Wages are RZS's average net monthly wage of employees, by where they live, in euros; KiM has none by municipality."))}`,
    Districts: () => {
      const source = data.nation.gdp_vintage ? t("{vintage}; GDP from {gdp}", { vintage: data.nation.vintage, gdp: data.nation.gdp_vintage }) : data.nation.vintage;
      const count = data.states?.length || data.world.states?.length || 0;
      return `
      ${h2("terrain", "🗺️", t("Districts"))}
      ${p(t("Click any land hex without a city to open its district. A district's numbers are the district totals and medians from the same tables as the cities ({source}), not the sum of its cities, so rural areas count too.", { source }))}
      <p>${t("{ranks} (“{example}”) compare all districts on the map; 1 is the largest.", { ranks: b(t("Ranks")), example: esc(t("#{rank} of {n}", { rank: 3, n: count })) })}</p>
      ${p(t("Cities that cross district lines are listed under every district they touch, with their whole-city numbers."))}
      ${data.states ? "" : `<p class="muted">${esc(t("This data build has no states.json, so district panels show names and cities only."))}</p>`}`;
    },
    Terrain: () => {
      const tables = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", "🗺️", t("Terrain"))}
      ${p(t("Each hex averages the ETOPO 2022 elevation samples inside it. Relief comes from the mean elevation and roughness (standard deviation) of those samples; shading comes from elevation differences with neighbouring hexes, lit from the north-west."))}
      <h4>${icon("l-forest", "🌲", { size: 16 })} ${esc(t("Land cover"))}</h4>
      ${hasCover
        ? `${p(t("The base colour of each hex is its dominant land-cover group: the largest group among the land samples inside it. Small symbols show the mix: trees scale with the forest share, and fields, reeds, shrubs and grass tufts mark farmland, wetland, scrub and grassland."))}
           <table>${tables.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">${esc(t("This data build has no land-cover layer yet; land is coloured by elevation."))}</p>`}
      ${h4(t("Relief"))}
      <table>${tables.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", "💧", { size: 16 })} ${esc(t("Water"))}</h4>
      <table>${tables.water.filter((x) => x.id > 0).map(row).join("")}</table>
      ${h4(t("Beyond the borders"))}
      <p class="muted">${esc(t("Neighbouring countries are drawn under a light fog: they are shown for context and not mapped in detail."))}</p>`;
    },
    Lenses: () => `
      ${h2("layers", "▤", t("Lenses"))}
      ${p(t("Lenses recolour the map by one measure, built from municipality data ({vintage}). Each hex is sampled at 7 points. A municipality covering some of them is assumed to cover that share of the hex. Small municipalities that no sample hits are added to the hex containing their centre. Income and home value are averaged over the municipalities in a hex, weighted by population.", { vintage: data.lenses.vintage }))}
      ${p(t("The legend shows how many hexes fall at each value. Hover or drag on it to show only that range on the map."))}
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((g) => {
        const ls = data.lenses.lenses.filter((l) => !g.id || l.group === g.id);
        if (!ls.length) return "";
        return `${g.name ? `<h3 class="grp">${icon(`g-${g.id}`, "", { size: 16 })} ${esc(g.name)}</h3>` : ""}${ls.map((l) => {
          const scale = t("Scale: {scale}, {from}–{to} {unit}", {
            scale: l.scale === "log" ? t("logarithmic") : l.scale === "linear" ? t("linear") : l.scale,
            from: plain.format(l.domain[0]), to: plain.format(l.domain[1]), unit: l.unit || "",
          });
          const meta = [scale, l.higher_is === "good" ? t("higher is better") : l.higher_is === "bad" ? t("higher is worse") : "", l.source ? srcName(l.source) : ""];
          return `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">${meta.filter(Boolean).map(esc).join(" · ")}</span></p></div></div>`;
        }).join("")}`;
      }).join("")}`,
    Resources: () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", "⛏️", t("Resources"))}<p class="muted">${esc(t("This data build has no resources layer."))}</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((type) => type.category || "other"))];
      return `
      ${h2("resources", "⛏️", t("Resources"))}
      <p>${t("Resources mark Serbia's biggest power plants, mines and oil & gas fields on the tiles where they are. Only meaningful sites are shown: each type's threshold is in its description. When zoomed out, a hex shows its highest-ranked resource; zoom in to see more. Press {key} to show or hide them.", { key: "<b>R</b>" })}</p>
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] || c)}</h4><table class="res-table">
        <tr><th></th><th>${esc(t("Type"))}</th><th>${esc(t("What counts"))}</th><th>${esc(t("Sites"))}</th></tr>
        ${r.types.filter((type) => (type.category || "other") === c).map((type) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(type.color || "#24384f")};color:${inkOn(type.color)}">${glyph(type, 20)}</span></td>
          <td class="nm"><b>${esc(type.name)}</b>${type.unit ? `<br><span class="muted">${esc(t("value in {unit}", { unit: type.unit }))}</span>` : ""}</td>
          <td>${esc(type.description || "")}<br><span class="muted">${esc(t("Source: {source}", { source: srcName(type.source) }))}</span></td>
          <td class="num">${int(count.get(type.id) || 0)}</td></tr>`).join("")}</table>`).join("")}`;
    },
    Sources: () => `
      ${h2("pedia", "📖", t("Sources"))}
      ${data.sources.map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description)}<br>
        <span class="muted">${esc(s.publisher)} · ${esc(s.license)}${s.vintage ? " · " + esc(s.vintage) : ""} ·
        <a href="${esc(s.homepage)}" target="_blank" rel="noopener">${esc(t("homepage"))}</a></span></p>
        <table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${
          esc(t("{size} MB", { size: num((f.bytes || 0) / 1e6, 1) }))}</td></tr>`).join("")}</table>`).join("")}`,
  };

  const show = (name) => {
    if (!pages[name]) name = "About this map";
    body.innerHTML = pages[name]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((btn) => {
      const on = btn.dataset.page === name;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">${esc(t("Almanac"))}</div>` + Object.keys(pages).map((pg) => `<button data-page="${esc(pg)}">${esc(t(pg))}</button>`).join("");
  nav.onclick = (e) => {
    const btn = e.target.closest("button[data-page]");
    if (btn) show(btn.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "About this map") {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
