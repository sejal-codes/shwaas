// Split the simplified states layer into one small TopoJSON file per country (loaded on demand by the app).
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import mapshaper from "mapshaper";

const SIMPLIFY = process.argv[2] ?? "12%";
const fc = JSON.parse(readFileSync("states.simplified.geojson", "utf8"));
const byCountry = new Map();
for (const f of fc.features) {
  if (!f.geometry) continue;
  const list = byCountry.get(f.properties.a) ?? [];
  list.push(f);
  byCountry.set(f.properties.a, list);
}
rmSync("out/states", { recursive: true, force: true });
mkdirSync("out/states", { recursive: true });
mkdirSync("tmp", { recursive: true });
for (const [a, features] of byCountry) {
  writeFileSync(`tmp/${a}.geojson`, JSON.stringify({ type: "FeatureCollection", features }));
  await mapshaper.runCommands(`-i tmp/${a}.geojson -o out/states/${a}.json format=topojson quantization=10000`);
}
console.log("wrote", byCountry.size, "country files");
