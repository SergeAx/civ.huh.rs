import { locale } from "./i18n.js";

const nf = (o) => new Intl.NumberFormat(locale, o);
const COMPACT = nf({ notation: "compact", maximumFractionDigits: 1 });
const MONEY = nf({ style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 });
const EUROS = nf({ style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const INT = nf({ maximumFractionDigits: 0 });
const PCT = [0, 1, 2].map((d) => nf({ style: "percent", minimumFractionDigits: d, maximumFractionDigits: d }));

const ok = (n) => n != null && !Number.isNaN(n);

export const compact = (n) => (ok(n) ? COMPACT.format(n) : "–");
export const money = (n) => (ok(n) ? MONEY.format(n) : "–");
export const euros = (n) => (ok(n) ? EUROS.format(n) : "–");
export const int = (n) => (ok(n) ? INT.format(n) : "–");
export const pct = (x, d = 1) => (ok(x) ? PCT[Math.min(2, Math.max(0, d))].format(x) : "–");
export const num = (x, d = 1) => (ok(x) ? nf({ minimumFractionDigits: d, maximumFractionDigits: d }).format(x) : "–");

export function yieldValue(y, v) {
  return y.unit === "eur" ? money(v) : compact(v);
}

export const popShort = compact;

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
