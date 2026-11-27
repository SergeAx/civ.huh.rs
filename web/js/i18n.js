// UI language. English strings are the message ids (gettext style): t("Search") looks the phrase up in the
// language's catalog and falls back to the English itself, so an untranslated string still reads. Serbian Latin
// has no catalog of its own: it is the Cyrillic catalog transliterated, as Serbian publishers do.

export const LANGS = [
  { id: "ru", label: "Русский", locale: "ru-RU" },
  { id: "sr-Cyrl", label: "Српски", locale: "sr-Cyrl-RS" },
  { id: "sr-Latn", label: "Srpski", locale: "sr-Latn-RS" },
  { id: "en", label: "English", locale: "en-GB" },
];
const STORE_KEY = "civ.lang";

function pick() {
  const ids = LANGS.map((l) => l.id);
  const fromUrl = new URLSearchParams(location.search).get("lang");
  if (ids.includes(fromUrl)) return fromUrl;
  try {
    const saved = localStorage.getItem(STORE_KEY);
    if (ids.includes(saved)) return saved;
  } catch {}
  for (const tag of navigator.languages || [navigator.language || ""]) {
    const t = tag.toLowerCase();
    if (t.startsWith("sr")) return t.includes("latn") ? "sr-Latn" : "sr-Cyrl";
    if (/^(ru|uk|be)\b/.test(t)) return "ru";
    if (t.startsWith("en")) return "en";
  }
  return "ru";
}

export const lang = pick();
export const locale = LANGS.find((l) => l.id === lang).locale;
document.documentElement.lang = lang;

// ui catalogs hold the code's strings, data catalogs the English text the pipeline writes into web/data.
const base = lang === "ru" ? "ru" : lang.startsWith("sr") ? "sr" : null;
const catalog = base
  ? { ...(await import(`./i18n/${base}.js`)).default, ...(await import(`./i18n/${base}.data.js`)).default }
  : {};

const CYR = {
  А: "A", Б: "B", В: "V", Г: "G", Д: "D", Ђ: "Đ", Е: "E", Ж: "Ž", З: "Z", И: "I", Ј: "J", К: "K", Л: "L", Љ: "Lj",
  М: "M", Н: "N", Њ: "Nj", О: "O", П: "P", Р: "R", С: "S", Т: "T", Ћ: "Ć", У: "U", Ф: "F", Х: "H", Ц: "C", Ч: "Č",
  Џ: "Dž", Ш: "Š",
};
for (const [c, l] of Object.entries(CYR)) CYR[c.toLowerCase()] = l.toLowerCase();

/** Serbian Cyrillic → Latin. A digraph letter is all caps (LJ, NJ, DŽ) when the next letter is a capital too. */
export function toLatin(s) {
  if (!s) return s;
  let out = "";
  for (let i = 0; i < s.length; i++) {
    const l = CYR[s[i]];
    if (l === undefined) { out += s[i]; continue; }
    const next = s[i + 1];
    out += l.length > 1 && next && next !== next.toLowerCase() ? l.toUpperCase() : l;
  }
  return out;
}

const script = lang === "sr-Latn" ? toLatin : (s) => s;
const plural = new Intl.PluralRules(locale);

function fill(s, vars) {
  return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : s;
}

/**
 * Translate an English UI string. `{name}` placeholders are filled from `vars`. A catalog entry may be an object of
 * plural forms ({one, few, many, other}), chosen by `vars.n`.
 */
export function t(s, vars) {
  let msg = catalog[s] ?? s;
  if (typeof msg === "object") msg = msg[plural.select(vars?.n ?? 0)] ?? msg.other;
  return fill(script(msg), vars);
}

/** A place's name in the UI script: Cyrillic for ru and sr-Cyrl, Latin for sr-Latn and en. */
export function placeName(o) {
  if (!o) return "";
  const cyr = o.name_cyr || o.name;
  return lang === "ru" || lang === "sr-Cyrl" ? cyr : o.name_lat || toLatin(cyr);
}

export function setLang(id) {
  try { localStorage.setItem(STORE_KEY, id); } catch {}
  const url = new URL(location.href);
  url.searchParams.set("lang", id);
  location.assign(url);
}

const TEXT_KEYS = new Set(["name", "label", "description", "rule", "note", "unit", "vintage", "gdp_vintage", "title", "used_for", "text", "publisher", "rules"]);

/** Translate, in place, the English text fields of data the pipeline wrote (lens and table names, rules, notes...).
 * Place names are untouched: they are Cyrillic and have no catalog entry, and placeName() picks their script. */
export function localizeData(node) {
  if (Array.isArray(node)) {
    for (const v of node) if (v && typeof v === "object") localizeData(v);
    return node;
  }
  if (!node || typeof node !== "object") return node;
  for (const [k, v] of Object.entries(node)) {
    if (typeof v === "string" && TEXT_KEYS.has(k)) node[k] = t(v);
    else if (Array.isArray(v) && TEXT_KEYS.has(k)) node[k] = v.map((x) => (typeof x === "string" ? t(x) : localizeData(x)));
    else if (v && typeof v === "object" && TEXT_KEYS.has(k)) node[k] = localizeMap(v);
    else if (v && typeof v === "object" && k !== "values") localizeData(v);
  }
  return node;
}

/** The string values of a flat {key: English} map, translated (industry labels, rule texts); others kept. */
export const localizeMap = (m) => (m ? Object.fromEntries(Object.entries(m).map(([k, v]) => [k, typeof v === "string" ? t(v) : v])) : m);
