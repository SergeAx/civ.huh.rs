# AGENTS.md

"Serbian Civilization" (https://civ.huh.rs): a fork of Andrej Karpathy's usaciv that draws Serbia, Kosovo and
Metohija included, as a strategy-game map from public data. Read `README.md`, then `docs/DATA_CONTRACTS.md` starting
with its "Serbian edition" section: the data files keep upstream's key names (`states` are okruzi, `counties` are
municipalities).

## Working rules

- Visual changes (map art, styles, layout, the social card): serve the site locally, give the user the URL and a
  screenshot, and wait for their OK before committing or deploying.
- Deploy only when the user asks.
- The pipeline is Python standard library only, run through `uv`. Downloads go through `Source.download` with the
  pipeline's own User-Agent; never impersonate a browser or use other tricks to get past a refusal.
- Missing data is `null`, never `0`; a gap is stated in the lens note or the Almanac, not filled with a guess.
- Before committing: `uv run python -m unittest discover -s tests` passes and `uv run python -m pipeline check`
  reports no FAIL and no WARN.
- Never read the untracked dotenv file in the repository root: it holds the Cloudflare token, and wrangler loads it
  by itself.

### Kosovo and Metohija

The map takes the Serbian point of view: KiM's municipalities sit under the five Serbian okruzi (25–29), places have
their Serbian names (Cyrillic canonical), Kosovo's road numbers are not shown, and Priština's airport is
"Аеродром Приштина". Its figures come from the Kosovo Agency of Statistics (RZS publishes none since 1999). In
Leposavić, Zvečan, Zubin Potok and Severna Kosovska Mitrovica most Serbs boycotted the 2024 census, so only
population, age and ethnicity (which include ASK's estimate) are used there; the rest stays blank.

### Languages

The UI speaks ru, sr-Cyrl, sr-Latn and en (`web/js/i18n.js`). English strings are the message ids. `web/js/i18n/ru.js`
and `sr.js` translate the code's strings; `ru.data.js` and `sr.data.js` translate the English text the pipeline
writes into `web/data`, applied once at load. Serbian is written in Cyrillic only: Latin is transliterated. Every new
UI or data string needs both translations.

## Run, rebuild, deploy

```bash
uv run python -m pipeline serve                 # http://127.0.0.1:8765, add ?lang=ru|sr-Cyrl|sr-Latn|en
uv run python -m pipeline all                   # fetch (cached in data/raw, ~380 MB) → process → build → check
uv run python -m pipeline package               # dist/srbciv/
bunx wrangler pages deploy --branch master      # Pages project civ-huh-rs → civ.huh.rs
```

`master` is the production branch. Cloudflare project settings (branches, domains) are changed by the user in the
dashboard. The social card is re-made by hand after data or art changes: README, "Deployment".

## Not ported yet

- **Advisors** (`web/js/ext/advisors`, left out in `web/js/ext/index.js`): upstream's dashboards are US-specific and
  untranslated.
- **City districts** (`districts.json`): RZS registered employment by workplace and NACE section (`rzs_economy`)
  could give the location quotients upstream took from BLS QCEW.
- **Wonders, trade routes, military sites**: no Serbian sources yet. Their drawing code is in place, and their Map-menu
  switches appear once their data files are built.
- **Gaps in the existing layers**:
  - Not in OSM, so not placed: the Pupin wind farm, Kolubara's Field G and Radljevo pits, and CHP Sremska Mitrovica.
  - Vinča waste-to-energy is left out, as the art has no icon for it.
  - Oil fields are skipped: OSM has only unnamed wells.
  - Only Belgrade and Priština publish airport passengers, and nobody publishes per-port cargo.
