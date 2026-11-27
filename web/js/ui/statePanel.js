import { css } from "../color.js";
import { esc, popShort } from "../format.js";
import { t, placeName } from "../i18n.js";
import { isCapital } from "../world.js";
import { yieldGrid, amenities, industries, gdpRow, popLine, growthSpan, showPanel } from "./infoPanel.js";

/**
 * Opens the panel for state `idx` (index into world.json states / states.json).
 * ctx: {w, nation, states (states.json or null), cities, onClose, onPedia, onCity(city)}
 */
export function openStatePanel(idx, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const geo = w.raw.states[idx] || {};
  // states.json is in the same order as world.json states; fall back to matching by fips.
  let st = ctx.states?.[idx];
  if (st && geo.fips && st.fips && st.fips !== geo.fips) st = ctx.states.find((s) => s.fips === geo.fips);
  st = st || { ...geo };
  const name = placeName(geo.name ? geo : st) || t("District");
  const abbr = st.abbr || geo.abbr || "";
  const count = ctx.states?.length || w.raw.states.length;

  const cities = (ctx.cities || []).filter((c) => (c.states || []).includes(abbr)).slice(0, 8);
  const cityRows = cities.length
    ? `<div class="city-list">${cities
        .map((c) => {
          const multi = (c.states || []).length > 1 ? `<span class="muted"> · ${esc(c.states.join("–"))}</span>` : "";
          return `<button class="city-row" data-city="${esc(c.id)}" title="${esc(placeName(c.full ? { name: c.full, name_lat: c.full_lat } : c))}">
            <span class="cr-name">${isCapital(c) ? "★ " : ""}${esc(placeName(c))}${multi}</span>
            <span class="cr-pop">${popShort(c.population)}</span><span class="cr-go" aria-hidden="true">›</span></button>`;
        })
        .join("")}</div>`
    : `<p class="muted">${esc(t("No cities in this district's data."))}</p>`;

  const hasEcon = st.population != null || st.yields;
  showPanel({
    kind: "state",
    stripe: css(w.stateColor[idx] || [190, 190, 190]),
    title: name,
    sub: `${esc(abbr)}${geo.fips ? ` · ${esc(t("code {code}", { code: geo.fips }))}` : ""}`,
    headExtra: hasEcon ? popLine(st, growthSpan(st, n)) : "",
    sections: [
      st.yields && { title: esc(t("Yields · rank among districts")), html: `<div class="yield-grid">${yieldGrid(nation, st.yields, st.ranks, count)}</div>` },
      hasEcon && { title: esc(t("Amenities & Housing")), html: amenities(st, n) + gdpRow(st) },
      st.jobs && { title: esc(t("Top industries · where people work")), html: industries(st, nation, 8) },
      { title: esc(t("Biggest cities")), html: cityRows },
      !hasEcon && { title: esc(t("Data")), html: `<p class="muted">${esc(t("District statistics are not in this data build (states.json is missing)."))}</p>` },
    ],
    foot: `${esc(nation.gdp_vintage ? t("Source: {source}; GDP: {gdp}.", { source: nation.vintage, gdp: nation.gdp_vintage }) : t("Source: {source}.", { source: nation.vintage }))}
      ${esc(t("Ranks are among the {n} mapped districts (1 = largest).", { n: count }))}`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-city]").forEach((b) => {
        b.onclick = () => {
          const c = ctx.cities.find((x) => x.id === b.dataset.city);
          if (c) ctx.onCity(c);
        };
      });
    },
  });
}
