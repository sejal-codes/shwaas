// Which parts of a country frame its first map view, checked against every real country file.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import * as geo from "../../app/static/vendor/geo.js";
import { coreOf } from "../../app/static/core.js";

const DIR = new URL("../../app/static/geo/states/", import.meta.url);
const load = (code) => {
  const topology = JSON.parse(readFileSync(new URL(`${code}.json`, DIR), "utf8"));
  return geo.feature(topology, Object.values(topology.objects)[0]).features.filter((f) => f.geometry);
};

test("every country keeps most of its land in view and frames quickly", () => {
  const codes = readdirSync(DIR).map((f) => f.slice(0, -5));
  assert.equal(codes.length, 242);
  for (const code of codes) {
    const started = performance.now();
    const core = coreOf(load(code), geo);
    assert.ok(core.keptArea >= 0.8, `${code} keeps ${(core.keptArea * 100).toFixed(0)}% of its area`);
    assert.ok(performance.now() - started < 500, `${code} is fast enough`);
  }
});

test("wide countries are never cut short", () => {
  for (const code of ["RUS", "CAN", "IDN", "CHL", "IND", "CHN", "BRA", "AUS"]) {
    const core = coreOf(load(code), geo);
    assert.equal(core.kept, core.total, `${code} shows all of its polygons`);
  }
});

test("far-away overseas territories do not shrink the first view", () => {
  const france = coreOf(load("FRA"), geo);
  assert.ok(france.kept < france.total, "French Guiana, Reunion and friends are left out of the first view");
  assert.ok(france.keptArea > 0.8 && france.centre[0] > -5 && france.centre[0] < 10, "framed on mainland France");
});
