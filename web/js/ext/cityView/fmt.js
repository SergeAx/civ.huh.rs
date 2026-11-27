// Number formatting for the City View. format.js's Intl formats already roll a value that rounds up over to the
// next unit ("1M", not "1000K", for 999,600 people), so these are its helpers under the old names.
export { compact, money, popShort, yieldValue } from "../../format.js";

// The number to pick a plural form by for a noun after compact(v): from "1.2K" up the noun follows the unit word
// (ru "тыс.", sr "хиљ."), which takes the "many" form, not the raw count's.
export const pluralOf = (v) => (Math.abs(v) >= 1000 ? 1000 : Math.round(v * 10) / 10);
