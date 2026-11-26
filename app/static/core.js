// Which parts of a country should frame the first view of its map?
// Far-flung territories (Alaska, Hawaii, French Guiana...) should not shrink the main landmass, so we find where
// most of the country's land is concentrated and frame that. Everything stays on the map and reachable by pan/zoom.

const RADIUS = 38; // degrees around the main concentration of land
const toDegrees = (radians) => (radians * 180) / Math.PI;

export function coreOf(features, geo) {
  const { geoArea, geoCentroid, geoDistance } = geo;
  const polygons = [];
  for (const f of features) {
    const g = f.geometry;
    if (g.type === "Polygon") polygons.push({ type: "Polygon", coordinates: g.coordinates });
    else if (g.type === "MultiPolygon") g.coordinates.forEach((coordinates) => polygons.push({ type: "Polygon", coordinates }));
  }
  const items = polygons.map((geometry) => ({ geometry, area: geoArea(geometry), centre: geoCentroid(geometry) }));
  const within = (from, radius) => items.filter((p) => toDegrees(geoDistance(p.centre, from)) <= radius);

  // 1) the polygon whose neighbourhood holds the most land
  let best = items[0];
  let bestArea = -1;
  for (const candidate of items) {
    const land = within(candidate.centre, RADIUS).reduce((sum, p) => sum + p.area, 0);
    if (land > bestArea) {
      bestArea = land;
      best = candidate;
    }
  }
  // 2) the middle of that neighbourhood, and how far it reaches
  const cluster = within(best.centre, RADIUS);
  const middle = geoCentroid({ type: "MultiPolygon", coordinates: cluster.map((p) => p.geometry.coordinates) });
  const reach = Math.max(...cluster.map((p) => toDegrees(geoDistance(p.centre, middle))));
  // 3) frame everything within a little more than that reach, so wide countries (Russia) are not cut short
  const radius = Math.max(RADIUS, reach * 1.25);
  const core = within(middle, radius);
  return {
    geometry: { type: "MultiPolygon", coordinates: core.map((p) => p.geometry.coordinates) },
    centre: middle,
    total: items.length,
    kept: core.length,
    keptArea: core.reduce((sum, p) => sum + p.area, 0) / items.reduce((sum, p) => sum + p.area, 0),
  };
}
