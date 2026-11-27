// Map-art extension: tile improvements (Interstates and major highways, railroads, ports, airports),
// military forts and restricted ground, wonders and protected land, and freight trade routes, each as a static layer
// drawn into the cached map (nothing animates; an idle map draws no frames), with a switch in the "Map" menu.
//
// Data: infrastructure.json, military.json, wonders.json and trade.json (loaded eagerly by main.js right after the
// first frame; app.loadData returns the same promise). A missing file (null) leaves its layers off and their switches
// harmless. Defaults: roads, rail, ports & airports, military and wonders on (roads, rail and hubs only from the region
// view in: see each layer's minRpx), trade routes off.
import { createModel } from "./model.js";
import { makeLayers } from "./layers.js";
import { tips } from "./tips.js";
import { t } from "../../i18n.js";

const TOGGLES = [
  { id: "roads", file: "infrastructure", label: t("Roads"), icon: "t-road", def: true, title: t("Motorways and state roads (OpenStreetMap)"), layers: ["roads"] },
  { id: "rail", file: "infrastructure", label: t("Railways"), icon: "t-rail", def: true, title: t("High-speed, main and branch railway lines (OpenStreetMap)"), layers: ["rail"] },
  { id: "hubs", file: "infrastructure", label: t("Ports & airports"), icon: "d-harbor", def: true, title: t("River ports and airports"), layers: ["hubs"] },
  { id: "military", file: "military", label: t("Military"), icon: "m-army", def: true, title: t("Military installations as forts, the largest ranges as restricted ground"), layers: ["forts", "restricted", "plates"] },
  { id: "wonders", file: "wonders", label: t("Wonders"), icon: "w-landmark", def: true, title: t("Most-visited parks, top research universities and curated landmarks"), layers: ["wonders", "protected", "plates"] },
  { id: "trade", file: "trade", label: t("Trade routes"), icon: "t-trade", def: false, title: t("The 40 largest freight flows between districts (FAF5 estimates)"), layers: ["trade"] },
];

export function install(app) {
  const model = createModel(app.w);
  const on = Object.fromEntries(TOGGLES.map((tg) => [tg.id, tg.def]));
  const layers = makeLayers(model, on, { tips, app });
  for (const l of layers) app.registerStaticLayer(l);

  const apply = (name, data) => {
    model.setData(name, data);
    app.requestDraw();
    return data;
  };
  // A switch appears only when its file was built, all at once so the Map menu keeps its order.
  const files = [...new Set(TOGGLES.map((tg) => tg.file))];
  Promise.all(files.map((name) => (app.data[name] !== undefined ? Promise.resolve(app.data[name]) : app.loadData(name))
    .then((d) => apply(name, d), (err) => console.warn(`map layers: ${name} failed to load`, err)))).then((loaded) => {
    const have = new Set(files.filter((_, i) => loaded[i]));
    for (const tg of TOGGLES.filter((x) => have.has(x.file))) {
      app.ui.addMapToggle({
        id: tg.id, label: tg.label, icon: tg.icon, title: tg.title, default: tg.def,
        get: () => on[tg.id],
        set: (v) => {
          on[tg.id] = !!v;
          app.requestDraw();
        },
      });
    }
  });

  // For debugging and the gallery: the model and switches.
  app.mapArt = { model, on, layers };
}
