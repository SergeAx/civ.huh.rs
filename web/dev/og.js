// The social card: the whole map on the left, drawn by the app's own renderer (trailer/stage.js), and the title on
// the dark right half. document.title turns "ready" when the card is complete, for a headless screenshot.
import { loadStage } from "./trailer/stage.js";

// Drawn at 2x and scaled down: canvas text has no hinting, and supersampling is what keeps it crisp at 1x.
const W = 1200, H = 630, DPR = 2;
const MAP_CENTRE_X = 300; // css px where the middle of Serbia lands
const GOLD = "#e3c272", INK = "#efe4c6", DIM = "#b9ab88";
const SERIF = '"Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif';
const SANS = '"Segoe UI", system-ui, sans-serif';

const stage = await loadStage("../data/");
const { width, height, margin } = stage.data.world;
const rpx = stage.R * ((H - 60) / (height - 2 * margin)); // Serbia's full height, with room for Subotica's banner
const scale = rpx / stage.R;
const cv = Object.assign(document.createElement("canvas"), { width: W * DPR, height: H * DPR });
stage.render(cv, {
  x: width / 2 + (W / 2 - MAP_CENTRE_X) / scale, y: height / 2 - 12 / scale, rpx, dpr: DPR, layers: { roads: true, rail: true },
});

const g = cv.getContext("2d");
g.setTransform(DPR, 0, 0, DPR, 0, 0);
// Fade the map's right edge into the title panel.
const fade = g.createLinearGradient(MAP_CENTRE_X + 170, 0, MAP_CENTRE_X + 330, 0);
fade.addColorStop(0, "rgba(13,42,71,0)");
fade.addColorStop(1, "rgba(13,42,71,1)");
g.fillStyle = fade;
g.fillRect(MAP_CENTRE_X + 170, 0, W, H);

await document.fonts.ready;
const x0 = 650;
g.textBaseline = "alphabetic";
g.fillStyle = GOLD;
g.font = `bold 66px ${SERIF}`;
g.fillText("Serbian", x0, 220);
g.fillText("Civilization", x0, 296);
g.fillStyle = GOLD;
g.fillRect(x0, 326, 420, 2);
g.fillStyle = INK;
g.font = `30px ${SERIF}`;
g.fillText("Српска Цивилизација", x0, 378);
g.fillText("Srpska Civilizacija", x0, 418);
g.fillStyle = DIM;
g.font = `21px ${SANS}`;
g.fillText("Serbia drawn as a strategy map from public data", x0, 492);
g.fillStyle = GOLD;
g.font = `bold 26px ${SERIF}`;
g.fillText("civ.huh.rs", x0, 570);
const out = document.getElementById("card").getContext("2d");
out.imageSmoothingQuality = "high";
out.drawImage(cv, 0, 0, W, H);
document.title = "ready";
