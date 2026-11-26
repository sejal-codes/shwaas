// The flat map of one country, with every state or province as a real, selectable shape.
// Zoom and pan with wheel/drag/pinch or the buttons; hover and tap are handled on the shapes themselves.
import { clear } from "./dom.js";
import { coreOf } from "./core.js";
import { clamp, easeInOutCubic, tween } from "./motion.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const VIEW_W = 1000;
const VIEW_H = 700;
const PAD = 40;
const MAX_ZOOM = 30;
const TAP_SLOP = 5;

const make = (tag, attrs = {}) => {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, String(value));
  return node;
};

export function createFlatMap({ svg, geo, onHover, onSelect }) {
  const { geoMercator, geoPath, feature, mesh } = geo;
  svg.setAttribute("viewBox", `0 0 ${VIEW_W} ${VIEW_H}`);

  let view = { k: 1, x: 0, y: 0 };
  let regions = []; // { name, lat, lon, node, d, bounds }
  let viewport = null;
  let hoverLayer = null;
  let selectLayer = null;
  let path = null;
  let contentBounds = null;
  let hovered = null;
  let selected = null;
  let engaged = false;
  let drag = null;
  let pinch = null;
  const pointers = new Map();
  let controller = new AbortController();

  // ----------------------------------------------------------------- viewport
  const unitsPerPixel = () => {
    const rect = svg.getBoundingClientRect();
    const scale = Math.min(rect.width / VIEW_W, rect.height / VIEW_H) || 1;
    return { rect, scale, offsetX: (rect.width - VIEW_W * scale) / 2, offsetY: (rect.height - VIEW_H * scale) / 2 };
  };

  const toUnits = (clientX, clientY) => {
    const { rect, scale, offsetX, offsetY } = unitsPerPixel();
    return [(clientX - rect.left - offsetX) / scale, (clientY - rect.top - offsetY) / scale];
  };

  function applyView() {
    if (!viewport) return;
    // keep at least a fifth of the country on screen so nobody pans it away entirely
    if (contentBounds) {
      const [[x0, y0], [x1, y1]] = contentBounds;
      view.x = clamp(view.x, VIEW_W * 0.2 - x1 * view.k, VIEW_W * 0.8 - x0 * view.k);
      view.y = clamp(view.y, VIEW_H * 0.2 - y1 * view.k, VIEW_H * 0.8 - y0 * view.k);
    }
    viewport.setAttribute("transform", `translate(${view.x.toFixed(2)} ${view.y.toFixed(2)}) scale(${view.k.toFixed(4)})`);
  }

  function zoomAt(factor, px = VIEW_W / 2, py = VIEW_H / 2) {
    const k = clamp(view.k * factor, 1, MAX_ZOOM);
    view = { k, x: px - ((px - view.x) * k) / view.k, y: py - ((py - view.y) * k) / view.k };
    applyView();
  }

  async function animateTo(target, duration = 650) {
    const from = { ...view };
    await tween(duration, (t) => {
      view = { k: from.k + (target.k - from.k) * t, x: from.x + (target.x - from.x) * t, y: from.y + (target.y - from.y) * t };
      applyView();
    }, easeInOutCubic);
  }

  // ----------------------------------------------------------------- hover/select
  function showLayer(layer, region) {
    layer.setAttribute("d", region ? region.d : "");
  }

  function setHover(region, event) {
    if (region === hovered) {
      if (region) onHover?.(region, event);
      return;
    }
    hovered = region;
    showLayer(hoverLayer, region && region !== selected ? region : null);
    svg.style.cursor = region ? "pointer" : "grab";
    onHover?.(region, event);
  }

  function select(region, { notify = true } = {}) {
    if (!viewport) return; // no map is showing
    selected = region;
    regions.forEach((r) => r.node.classList.toggle("is-selected", r === region));
    showLayer(selectLayer, region);
    showLayer(hoverLayer, null);
    selectLayer.classList.remove("pulse");
    void selectLayer.getBoundingClientRect(); // restart the pulse animation
    if (region) selectLayer.classList.add("pulse");
    if (region && notify) onSelect?.({ name: region.name, lat: region.lat, lon: region.lon });
  }

  const regionOf = (target) => {
    const node = target?.closest?.(".region");
    return node ? regions.find((r) => r.node === node) ?? null : null;
  };

  // --------------------------------------------------------------------- build
  function show({ topology, object }) {
    destroy();
    controller = new AbortController();
    const { signal } = controller;
    const collection = feature(topology, object);
    const features = collection.features.filter((f) => f.geometry);
    const { geometry, centre } = coreOf(features, geo);

    const projection = geoMercator().rotate([-centre[0], 0]).fitExtent([[PAD, PAD], [VIEW_W - PAD, VIEW_H - PAD]], geometry);
    path = geoPath(projection);
    view = { k: 1, x: 0, y: 0 };

    viewport = make("g", { class: "viewport" });
    const regionLayer = make("g", { class: "regions" });
    regions = features
      .map((f) => {
        const d = path(f);
        if (!d) return null;
        const node = make("path", { class: "region", d, "data-name": f.properties.n });
        return { name: f.properties.n, lat: f.properties.y, lon: f.properties.x, node, d, bounds: path.bounds(f) };
      })
      .filter(Boolean);
    regions.forEach((r) => regionLayer.append(r.node));

    const borders = make("path", { class: "borders", d: path(mesh(topology, object, (a, b) => a !== b)) ?? "" });
    const outline = make("path", { class: "outline", d: path(mesh(topology, object, (a, b) => a === b)) ?? "" });
    hoverLayer = make("path", { class: "hl hl--hover" });
    selectLayer = make("path", { class: "hl hl--selected" });
    viewport.append(regionLayer, borders, outline, hoverLayer, selectLayer);
    svg.append(viewport);

    const all = path.bounds(collection);
    contentBounds = Number.isFinite(all[0][0]) ? all : null;
    applyView();
    svg.style.cursor = "grab";

    // ---- pointer handling on the svg (shapes are found with the pointer's own hit-test)
    svg.addEventListener("pointerdown", (event) => {
      svg.setPointerCapture?.(event.pointerId);
      pointers.set(event.pointerId, [event.clientX, event.clientY]);
      engaged = true;
      if (pointers.size === 1) drag = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, moved: false, target: regionOf(event.target) };
      else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = { distance: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, k: view.k };
        drag = null;
      }
    }, { signal });

    svg.addEventListener("pointermove", (event) => {
      if (pointers.has(event.pointerId)) pointers.set(event.pointerId, [event.clientX, event.clientY]);
      if (pinch && pointers.size >= 2) {
        const [a, b] = [...pointers.values()];
        const mid = toUnits((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
        zoomAt(clamp((pinch.k * Math.hypot(a[0] - b[0], a[1] - b[1])) / pinch.distance, 1, MAX_ZOOM) / view.k, mid[0], mid[1]);
        return;
      }
      if (drag) {
        if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > TAP_SLOP) {
          drag.moved = true;
          setHover(null, event);
          svg.style.cursor = "grabbing";
        }
        if (drag.moved) {
          const { scale } = unitsPerPixel();
          view.x += (event.clientX - drag.x) / scale;
          view.y += (event.clientY - drag.y) / scale;
          applyView();
        }
        drag.x = event.clientX;
        drag.y = event.clientY;
        return;
      }
      if (event.pointerType !== "touch") setHover(regionOf(event.target), event);
    }, { signal });

    const end = (event) => {
      const tap = drag && !drag.moved && pointers.size === 1 && event.type === "pointerup";
      const target = drag?.target;
      pointers.delete(event.pointerId);
      if (pointers.size < 2) pinch = null;
      if (pointers.size === 0) {
        drag = null;
        svg.style.cursor = hovered ? "pointer" : "grab";
      }
      if (tap && target) select(target);
    };
    svg.addEventListener("pointerup", end, { signal });
    svg.addEventListener("pointercancel", end, { signal });
    svg.addEventListener("pointerleave", (event) => { if (!drag) setHover(null, event); }, { signal });
    svg.addEventListener("wheel", (event) => {
      if (!engaged && !event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const [px, py] = toUnits(event.clientX, event.clientY);
      zoomAt(Math.exp(-event.deltaY * 0.0018), px, py);
    }, { signal, passive: false });
    document.addEventListener("pointerdown", (event) => { if (!svg.contains(event.target)) engaged = false; }, { signal });
    return { count: regions.length };
  }

  function destroy() {
    controller.abort();
    pointers.clear();
    drag = null;
    pinch = null;
    hovered = null;
    selected = null;
    regions = [];
    viewport = null;
    clear(svg);
  }

  const byName = (name) => regions.find((r) => r.name === name) ?? null;

  return {
    show,
    destroy,
    select: (name, options) => {
      const region = byName(name);
      if (region) select(region, options);
      return region;
    },
    clearSelection: () => select(null),
    /** Glide so a region fills the view (used when it is chosen from the search box). */
    async focusRegion(name) {
      const region = byName(name);
      if (!region) return;
      const [[x0, y0], [x1, y1]] = region.bounds;
      const k = clamp(0.55 * Math.min(VIEW_W / Math.max(x1 - x0, 8), VIEW_H / Math.max(y1 - y0, 8)), 1, MAX_ZOOM);
      await animateTo({ k, x: VIEW_W / 2 - ((x0 + x1) / 2) * k, y: VIEW_H / 2 - ((y0 + y1) / 2) * k });
    },
    zoomBy: (factor) => zoomAt(factor),
    reset: () => animateTo({ k: 1, x: 0, y: 0 }),
    names: () => regions.map((r) => r.name),
    get selectedName() {
      return selected?.name ?? null;
    },
  };
}
