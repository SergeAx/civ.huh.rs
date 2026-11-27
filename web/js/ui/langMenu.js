// Language switcher in the top bar: a menu button (#btn-lang) and its menu (#lang-pop), WAI-ARIA menu pattern.
import { esc } from "../format.js";
import { LANGS, lang, setLang, t } from "../i18n.js";

const short = (l) => l.label.slice(0, 2).toUpperCase();

export function initLangMenu() {
  const btn = document.getElementById("btn-lang");
  const pop = document.getElementById("lang-pop");
  if (!btn || !pop) return { close() {}, get isOpen() { return false; } };
  const cur = LANGS.find((l) => l.id === lang);
  btn.innerHTML = `<span class="lang-code" lang="${esc(cur.id)}">${esc(short(cur))}</span><span class="lbl" lang="${esc(cur.id)}">${esc(cur.label)}</span><span class="caret" aria-hidden="true">▾</span>`;
  btn.setAttribute("aria-label", t("Language: {lang}", { lang: cur.label }));
  btn.title = t("Language");
  pop.innerHTML = LANGS.map((l) => `<button type="button" class="sp-item" role="menuitemradio" tabindex="-1" data-lang="${esc(l.id)}"
    lang="${esc(l.id)}" aria-checked="${l.id === lang}"><span class="lang-code" aria-hidden="true">${esc(short(l))}</span><span>${esc(l.label)}</span></button>`).join("");
  const items = () => [...pop.querySelectorAll("[data-lang]")];

  function position() {
    const r = btn.getBoundingClientRect();
    const w = pop.offsetWidth || 180;
    pop.style.top = r.bottom + 8 + "px";
    pop.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.right - w)) + "px";
  }
  function open(focusLast = false) {
    pop.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    position();
    const list = items();
    (focusLast ? list.at(-1) : list.find((b) => b.dataset.lang === lang) || list[0])?.focus();
  }
  function close(restore = true) {
    if (pop.hidden) return;
    pop.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    if (restore) btn.focus();
  }
  function pick(id) {
    close();
    if (id !== lang) setLang(id);
  }

  btn.addEventListener("click", () => (pop.hidden ? open() : close()));
  btn.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    open(e.key === "ArrowUp");
  });
  pop.addEventListener("click", (e) => {
    const b = e.target.closest("[data-lang]");
    if (b) pick(b.dataset.lang);
  });
  pop.addEventListener("keydown", (e) => {
    const list = items();
    const k = list.indexOf(document.activeElement);
    const move = { ArrowDown: k + 1, ArrowUp: k - 1, Home: 0, End: list.length - 1 }[e.key];
    if (move !== undefined) {
      e.preventDefault();
      list[(move + list.length) % list.length].focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "Tab") {
      close();
    }
  });
  document.addEventListener("pointerdown", (e) => {
    if (!pop.hidden && !pop.contains(e.target) && !btn.contains(e.target)) close(false);
  });
  addEventListener("resize", () => !pop.hidden && position());

  return { close, get isOpen() { return !pop.hidden; } };
}
