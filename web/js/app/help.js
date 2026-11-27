// Keyboard & mouse cheat-sheet.
import { icon } from "../ui/icon.js";
import { esc } from "../format.js";
import { t } from "../i18n.js";

const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const MOD = isMac ? "⌘" : "Ctrl";

const ROWS = [
  [t("Move"), [
    [[t("Drag"), "←↑→↓", "WASD"], t("Pan the map")],
    [[t("Scroll"), "+", "–"], t("Zoom in and out")],
    [[t("Double-click")], t("Zoom in on a spot")],
    [[t("Two fingers")], t("Pinch to zoom, drag to pan (touch)")],
    [[t("Minimap")], t("Click or drag to jump")],
  ]],
  [t("Explore"), [
    [[t("Click city")], t("Open the city screen")],
    [[t("Click land")], t("Open that district")],
    [["/", `${MOD} K`], t("Search cities and districts")],
    [["L", "Shift L"], t("Next / previous lens")],
    [[t("Legend")], t("Hover or drag the scale to show only that range")],
    [["R"], t("Show or hide resources")],
  ]],
  [t("Panels"), [
    [["?"], t("This help")],
    [["Esc"], t("Close help, search, Almanac, then the panel")],
  ]],
];

export function initHelp() {
  const modal = document.getElementById("help");
  if (!modal) return { open() {}, close() {}, get isOpen() { return false; } };
  const card = modal.querySelector(".help-card");
  let restore = null;
  card.innerHTML = `
    <button class="icon-btn help-close" data-close aria-label="${esc(t("Close help"))}">${icon("close", "✕", { size: 13 })}</button>
    <h2 id="help-title">${icon("help", "?", { size: 22 })}<span>${esc(t("Controls"))}</span></h2>
    <div class="help-cols">${ROWS.map(([title, rows]) => `
      <section><h3>${esc(title)}</h3>${rows.map(([keys, what]) => `
        <div class="help-row"><span class="keys">${keys.map((k) => `<kbd>${esc(k)}</kbd>`).join("")}</span><span>${esc(what)}</span></div>`).join("")}
      </section>`).join("")}</div>
    <p class="help-foot">${t("Every number traces back to public data: open the {almanac} for sources.", { almanac: `<b>${esc(t("Almanac"))}</b>` })}
      ${esc(t("The link in the address bar always reopens this exact view."))}
      ${t("A Serbian edition of {usaciv}, Andrej Karpathy's map of the United States.", { usaciv: `<a href="https://karpathy.ai/usaciv/" target="_blank" rel="noopener">usaciv</a>` })}</p>`;

  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restore && document.contains(restore)) restore.focus();
    restore = null;
  };
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  });
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault(); // the only focusable control is the close button
    card.querySelector("[data-close]").focus();
  });

  return {
    open() {
      if (!modal.hidden) return;
      restore = document.activeElement;
      modal.hidden = false;
      card.querySelector("[data-close]").focus();
    },
    close,
    toggle() { modal.hidden ? this.open() : close(); },
    get isOpen() { return !modal.hidden; },
  };
}
