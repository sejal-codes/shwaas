// Trim Natural Earth down to the few properties the app needs, so simplification stays fast and files stay small.
import { readFileSync, writeFileSync } from "node:fs";
import { geoCentroid } from "d3-geo";

const admin0 = JSON.parse(readFileSync("ne_50m_admin_0_countries.geojson", "utf8"));
const admin1 = JSON.parse(readFileSync("ne_10m_admin_1_states_provinces.geojson", "utf8"));
const r2 = (n) => Math.round(n * 100) / 100;

const countries = [];
const known = new Set();
for (const f of admin0.features) {
  const p = f.properties;
  const a = p.ADM0_A3;
  if (!a || !f.geometry) continue;
  const c = geoCentroid(f);
  const x = Number.isFinite(p.LABEL_X) ? p.LABEL_X : c[0];
  const y = Number.isFinite(p.LABEL_Y) ? p.LABEL_Y : c[1];
  known.add(a);
  countries.push({ type: "Feature", properties: { a, n: p.NAME_EN || p.NAME || p.ADMIN, x: r2(x), y: r2(y) }, geometry: f.geometry });
}
writeFileSync("countries.prep.geojson", JSON.stringify({ type: "FeatureCollection", features: countries }));

const states = [];
let skipped = 0;
for (const f of admin1.features) {
  const p = f.properties;
  const a = p.adm0_a3;
  const name = p.name || p.name_en;
  if (!known.has(a) || !name || !f.geometry) { skipped++; continue; }
  const c = geoCentroid(f);
  const x = Number.isFinite(p.longitude) ? p.longitude : c[0];
  const y = Number.isFinite(p.latitude) ? p.latitude : c[1];
  states.push({ type: "Feature", properties: { a, n: name, x: r2(x), y: r2(y) }, geometry: f.geometry });
}
writeFileSync("states.prep.geojson", JSON.stringify({ type: "FeatureCollection", features: states }));
console.log("countries:", countries.length, "states:", states.length, "skipped:", skipped);
