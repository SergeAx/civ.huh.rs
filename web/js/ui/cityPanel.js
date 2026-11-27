import { css } from "../color.js";
import { esc } from "../format.js";
import { t, placeName } from "../i18n.js";
import { isCapital } from "../world.js";
import { yieldGrid, amenities, industries, gdpRow, popLine, growthSpan, showPanel, hidePanel } from "./infoPanel.js";

/**
 * ctx: {w, nation, onClose, onPedia, onState(stateIndex)}
 */
export function openCityPanel(city, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const owner = city.cell != null ? w.raw.owner[city.cell] : -1;
  const col = css(w.stateColor[owner] || [190, 190, 190]);

  // The city's districts as links to their district panels.
  const states = (city.states || [])
    .map((abbr) => ({ abbr, i: w.raw.states.findIndex((s) => s.abbr === abbr) }))
    .map(({ abbr, i }) => (i >= 0 && ctx.onState
      ? `<button class="chip" data-state="${i}" title="${esc(t("Open {name}", { name: placeName(w.raw.states[i]) }))}">${esc(abbr)}</button>`
      : `<span class="chip">${esc(abbr)}</span>`))
    .join("");

  const growth = growthSpan(city, n);
  const name = placeName(city);
  const source = nation.gdp_vintage
    ? t("Source: {source}; GDP: {gdp}.", { source: nation.vintage, gdp: nation.gdp_vintage })
    : t("Source: {source}.", { source: nation.vintage });

  showPanel({
    kind: "city",
    stripe: col,
    title: name,
    titleHtml: `${isCapital(city) ? `<span class="cap" title="${esc(t("National capital"))}">★</span> ` : ""}${esc(name)}`,
    sub: `${esc(city.full ? placeName({ name: city.full, name_lat: city.full_lat }) : "")}${states ? `<div class="chips">${states}</div>` : ""}`,
    headExtra: popLine(city, growth),
    sections: [
      { title: esc(t("Yields")), html: `<div class="yield-grid">${yieldGrid(nation, city.yields)}</div>` },
      { title: esc(t("Amenities & Housing")), html: amenities(city, n) + gdpRow(city) },
      { title: esc(t("City districts · where people work")), html: industries(city, nation) },
    ],
    foot: `${esc(source)}
      ${esc(t("Green ×N = this industry's share of jobs is N× the national share."))}`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => ctx.onState(+b.dataset.state)));
    },
  });
}

export const closeCityPanel = hidePanel;
