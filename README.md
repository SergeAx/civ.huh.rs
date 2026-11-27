# srbciv: Serbia as a strategy game, built from real data

A visualizer (not a game) that draws the **real** Serbia, Kosovo and Metohija included, like a turn-based strategy
map: about 3,800 hexes of 3 km, cities with yield banners, lenses, a City View with citizens, and an Almanac that
traces every number to a public source. The interface speaks Russian, Serbian (Cyrillic and Latin) and English.

It is a fork of Andrej Karpathy's [usaciv](https://karpathy.ai/usaciv/) (MIT), which does the same for the United
States: the renderer, the art and the app shell are his; the data pipeline and the translations are this fork's.

## Quick start

You need [uv](https://docs.astral.sh/uv/); it fetches a suitable Python (3.11+) by itself.

```bash
uv run python -m pipeline serve        # http://127.0.0.1:8765
```

The built data (`web/data/`, about 2 MB) is in the repository, so that is all it takes. Add `?lang=ru`, `sr-Cyrl`,
`sr-Latn` or `en` to the address to pick a language; the switcher in the top bar remembers the choice.

## Rebuilding the data

```bash
uv run python -m pipeline all          # download (cached) → process → build web/data/*.json → check
uv run python -m unittest discover -s tests
```

The first run downloads about 380 MB into `data/raw/` (the RGZ registers and CORINE are most of it). The pipeline uses the Python standard
library only, and no source needs an API key. `uv run python -m pipeline list` shows the sources and builders;
`fetch`, `process`, `build` and `check` take source or builder names, and `--offline` works from the cache.

## What the map shows

- **Units.** The map's "states" are Serbia's 30 okruzi (with Grad Beograd), labelled by the vehicle-registration code
  of their seat (BG, NS, NI, PR…). Its "counties" are the 206 municipalities that the statistics report: the 168 RZS
  units outside KiM and Kosovo's 38 municipalities, grouped under the five Serbian okruzi of Kosovo and Metohija.
- **Cities.** One per municipality, at its seat. Belgrade joins its eleven urban gradske opštine; Niš, Novi Sad,
  Požarevac, Vranje and Užice are joined back from theirs.
- **Yields.** Food, Production, Science and Culture count employed residents by NACE section at the census. Gold is
  GDP: RZS publishes gross value added per okrug and ASK for KiM as a whole; it is scaled to GDP by the national ratio,
  and each municipality's share is estimated from its employees in each activity group.
- **Lenses.** Density, mean age, aged 65+, growth since 2011, unemployment, wages, GDP per person, degrees, no primary
  school, largest people, largest faith, believers, forest, farmland and built-up land.
- **Tile improvements.** Motorways and state roads, railways in three tiers (the 200 km/h Belgrade–Novi Sad–Subotica
  line on top), river ports and airports, all from OpenStreetMap.
- **Resources.** Every lignite and gas power plant, hydro, wind and solar plants from 10 MW, and the working lignite,
  copper and lead-zinc mines, with the capacities and output EPS, KOSTT, AERS, ERO and Zijin publish.

### Kosovo and Metohija

RZS has published no figures for KiM since 1999, so KiM comes from the Kosovo Agency of Statistics (2024 census),
by its 38 municipalities. Most Serbs in Leposavić, Zvečan, Zubin Potok and Severna Kosovska Mitrovica boycotted that
census: ASK estimated their population, age and ethnicity, and only those are shown there; the other census tables
of those four municipalities stay blank, never zero. ASK publishes no wages by municipality, so the wage lens is blank
across KiM. The 2011 count is unusable in the north (not enumerated) and in Preševo and Bujanovac (boycotted), so
their growth is blank too.

## Data sources

| Source | Publisher | Used for |
|---|---|---|
| Census 2022, registered employment, wages, GVA by okrug | Statistical Office of the Republic of Serbia (RZS) | Everything outside KiM |
| Census 2024, GDP and wages | Kosovo Agency of Statistics (ASK) | Kosovo and Metohija |
| Register of spatial units | Republic Geodetic Authority (RGZ) | Municipal and okrug boundaries |
| Municipalities of Kosovo, seats, rivers, roads, railways, ports, airports | OpenStreetMap contributors (ODbL) | KiM boundaries, city positions, the map's lines and hubs |
| Power plants and mines | EPS, KOSTT, AERS, ERO, Zijin Mining, OpenStreetMap | Resources |
| CORINE Land Cover 2018 | Copernicus / EEA | Land cover, lakes |
| ETOPO 2022 | NOAA NCEI | Relief |
| Natural Earth 1:10m, Wikidata names | Natural Earth, Wikidata | Neighbouring countries |

The Almanac (top bar) lists every file with its URL, checksum, date and licence.

## How it works

The flow is **source → interim → builder → web/data**, as in usaciv: `pipeline/sources/` turns each publisher's
files into tidy JSON, `pipeline/build/` puts it on the hex grid (`units.py` harmonises the two censuses into one
record per municipality), and `pipeline/check.py` validates `web/data` against `docs/DATA_CONTRACTS.md`. Map
coordinates are "map units" of 120 m, so the 25-unit hexes are 3 km and upstream's art, tuned for 25 km hexes, fits
unchanged. The browser side is plain ES modules and Canvas 2D; `web/js/i18n.js` translates the interface and the
data's English text through the catalogs in `web/js/i18n/`.

## Deployment

The site is static: `uv run python -m pipeline package` assembles it in `dist/srbciv/` (web/ without the dev pages),
and wrangler uploads it to the `civ-huh-rs` Cloudflare Pages project named in `wrangler.toml`:

```bash
uv run python -m pipeline package
bunx wrangler pages deploy --branch master
```

GitHub Actions runs the unit tests and the data check on every push; deploys are manual.

## Not yet ported

Advisors, city districts, wonders, trade routes and military sites: their US sources are gone and their Serbian ones
are still to be written. The code that draws them is in place.

## Licence

The code is MIT-licensed (see [LICENSE](LICENSE)); that covers the code, not the data, whose licences are listed in the
Almanac. The parts of `web/data` derived from OpenStreetMap (rivers, Kosovo's municipal outlines, municipal seats) are
© OpenStreetMap contributors and available under the [ODbL](https://opendatacommons.org/licenses/odbl/). The look is inspired by turn-based 4X
strategy games, but every glyph, icon and texture is original and drawn in code.
