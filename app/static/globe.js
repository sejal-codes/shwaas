// An interactive 3D globe on a canvas. Countries are real geography: hover and click are found by asking which
// country contains the point under the pointer (d3-geo), not by pixel colours.
import { clamp, prefersReducedMotion, tween } from "./motion.js";

const MIN_ZOOM = 1;
const MAX_ZOOM = 14;
const FLY_MAX_ZOOM = 40;
const TAP_SLOP = 5; // px of movement that turns a tap into a drag

export function createGlobe({ canvas, geo, features, readTheme, onHover, onSelect }) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const { geoOrthographic, geoPath, geoGraticule10, geoContains, geoBounds } = geo;
  const projection = geoOrthographic().clipAngle(90).precision(0.5);
  const path = geoPath(projection, ctx);
  const graticule = geoGraticule10();
  const sphere = { type: "Sphere" };
  const boxes = features.map((feature) => ({ feature, box: geoBounds(feature) }));
  const controller = new AbortController();
  const { signal } = controller;

  let theme = readTheme();
  let width = 0;
  let height = 0;
  let base = 1; // sphere radius in px at zoom 1
  let zoom = 1;
  let rotation = [-72, -18]; // [lambda, phi]
  let hovered = null;
  let selected = null;
  let velocity = [0, 0];
  let autoRotate = true;
  let idleSince = performance.now();
  let visible = true;
  let flying = false;
  let engaged = false; // wheel only zooms once the person has clicked the globe, so page scrolling is never hijacked
  let frameId = 0;
  let lastDraw = 0;
  let dirty = true;
  let disposed = false;
  const pointers = new Map();
  let drag = null;
  let pinch = null;

  // ------------------------------------------------------------------ geometry
  function inBox([[west, south], [east, north]], lon, lat) {
    if (lat < south || lat > north) return false;
    return west <= east ? lon >= west && lon <= east : lon >= west || lon <= east;
  }

  function countryAt(x, y) {
    const point = projection.invert([x, y]);
    if (!point) return null; // off the sphere
    for (const { feature, box } of boxes) {
      if (inBox(box, point[0], point[1]) && geoContains(feature, point)) return feature;
    }
    return null;
  }

  // -------------------------------------------------------------------- drawing
  function fillSphere(style) {
    ctx.beginPath();
    path(sphere);
    ctx.fillStyle = style;
    ctx.fill();
  }

  function draw() {
    lastDraw = performance.now();
    const radius = base * zoom;
    projection.rotate(rotation).scale(radius).translate([width / 2, height / 2]);
    ctx.clearRect(0, 0, width, height);

    if (zoom < 2.5) {
      const halo = ctx.createRadialGradient(width / 2, height / 2, radius * 0.96, width / 2, height / 2, radius * 1.2);
      halo.addColorStop(0, theme.glow);
      halo.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, width, height);
    }

    const ocean = ctx.createRadialGradient(width / 2 - radius * 0.35, height / 2 - radius * 0.42, radius * 0.1, width / 2, height / 2, radius * 1.15);
    ocean.addColorStop(0, theme.oceanLight);
    ocean.addColorStop(1, theme.oceanDeep);
    fillSphere(ocean);

    if (zoom <= 2.5) {
      ctx.beginPath();
      path(graticule);
      ctx.strokeStyle = theme.line;
      ctx.lineWidth = 0.6;
      ctx.stroke();
    }

    ctx.beginPath();
    for (const feature of features) path(feature);
    ctx.fillStyle = theme.land;
    ctx.fill("evenodd");
    ctx.strokeStyle = theme.border;
    ctx.lineWidth = zoom > 4 ? 1.1 : 0.7;
    ctx.stroke();

    if (hovered && hovered !== selected) {
      ctx.beginPath();
      path(hovered);
      ctx.fillStyle = theme.landHover;
      ctx.fill("evenodd");
      ctx.strokeStyle = theme.accent;
      ctx.lineWidth = 1.8;
      ctx.stroke();
    }
    if (selected) {
      ctx.beginPath();
      path(selected);
      ctx.fillStyle = theme.selected;
      ctx.fill("evenodd");
      ctx.strokeStyle = theme.accent;
      ctx.lineWidth = 2.4;
      ctx.stroke();
    }

    if (zoom > 3) return; // the rim and highlights are off-screen when zoomed in, so skip the extra passes
    // depth: darker toward the rim, a soft highlight, and a thin rim light
    const shade = ctx.createRadialGradient(width / 2, height / 2, radius * 0.45, width / 2, height / 2, radius);
    shade.addColorStop(0, "rgba(0,0,0,0)");
    shade.addColorStop(1, theme.shade);
    fillSphere(shade);
    const shine = ctx.createRadialGradient(width / 2 - radius * 0.4, height / 2 - radius * 0.45, 0, width / 2 - radius * 0.4, height / 2 - radius * 0.45, radius * 0.9);
    shine.addColorStop(0, theme.shine);
    shine.addColorStop(1, "rgba(255,255,255,0)");
    fillSphere(shine);
    ctx.beginPath();
    path(sphere);
    ctx.strokeStyle = theme.rim;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // ----------------------------------------------------------------- frame loop
  const wantsAuto = () => autoRotate && visible && !flying && zoom < 1.2 && !prefersReducedMotion() && !document.hidden;

  function schedule() {
    if (!frameId && !disposed && visible) frameId = requestAnimationFrame(frame);
  }

  function frame(now) {
    frameId = 0;
    let moving = false;
    const dragging = drag?.moved || pinch;
    if (!dragging && !flying) {
      if (Math.abs(velocity[0]) + Math.abs(velocity[1]) > 0.02) {
        rotation = [rotation[0] + velocity[0], clamp(rotation[1] + velocity[1], -90, 90)];
        velocity = [velocity[0] * 0.94, velocity[1] * 0.94];
        moving = true;
      } else {
        velocity = [0, 0];
      }
      if (wantsAuto() && now - idleSince > 3500 && !hovered && now - lastDraw >= 32) {
        rotation = [rotation[0] - 0.006 * Math.min(now - lastDraw, 48), rotation[1]]; // a gentle idle spin at ~30fps
        moving = true;
      }
    }
    if (dirty || moving) {
      draw();
      dirty = false;
    }
    if (moving || wantsAuto()) schedule();
  }

  /** Ask for a repaint; many calls within one frame cost a single draw. */
  function redraw() {
    dirty = true;
    schedule();
  }

  const touch = () => {
    idleSince = performance.now();
  };

  // -------------------------------------------------------------------- sizing
  function resize() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    let ratio = Math.min(globalThis.devicePixelRatio || 1, 2);
    while (ratio > 1 && rect.width * rect.height * ratio * ratio > 2_400_000) ratio -= 0.25;
    width = Math.round(rect.width);
    height = Math.round(rect.height);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    base = (Math.min(width, height) / 2) * 0.9;
    redraw();
  }

  // ------------------------------------------------------------------- pointers
  const local = (event) => {
    const rect = canvas.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  };

  function setHover(feature, event) {
    if (feature === hovered) {
      if (feature) onHover?.(feature, event);
      return;
    }
    hovered = feature;
    canvas.style.cursor = feature ? "pointer" : "grab";
    onHover?.(feature, event);
    redraw();
  }

  canvas.addEventListener(
    "pointerdown",
    (event) => {
      canvas.setPointerCapture?.(event.pointerId);
      pointers.set(event.pointerId, local(event));
      engaged = true;
      velocity = [0, 0];
      touch();
      if (pointers.size === 1) {
        const [x, y] = local(event);
        drag = { x, y, startX: x, startY: y, moved: false };
      } else if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = { distance: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, zoom };
        drag = null;
      }
    },
    { signal },
  );

  canvas.addEventListener(
    "pointermove",
    (event) => {
      const position = local(event);
      if (pointers.has(event.pointerId)) pointers.set(event.pointerId, position);
      if (pinch && pointers.size >= 2) {
        const [a, b] = [...pointers.values()];
        zoom = clamp((pinch.zoom * Math.hypot(a[0] - b[0], a[1] - b[1])) / pinch.distance, MIN_ZOOM, MAX_ZOOM);
        touch();
        redraw();
        return;
      }
      if (drag) {
        const [x, y] = position;
        if (!drag.moved && Math.hypot(x - drag.startX, y - drag.startY) > TAP_SLOP) {
          drag.moved = true;
          setHover(null, event);
          canvas.style.cursor = "grabbing";
        }
        if (drag.moved) {
          const k = 0.32 / zoom;
          const dx = (x - drag.x) * k;
          const dy = (y - drag.y) * k;
          rotation = [rotation[0] + dx, clamp(rotation[1] - dy, -90, 90)];
          velocity = [velocity[0] * 0.5 + dx * 0.5, velocity[1] * 0.5 - dy * 0.5];
          touch();
          redraw();
        }
        drag.x = x;
        drag.y = y;
        return;
      }
      if (event.pointerType === "mouse" || event.pointerType === "pen") setHover(countryAt(position[0], position[1]), event);
    },
    { signal },
  );

  function endPointer(event) {
    const wasTap = drag && !drag.moved && pointers.size === 1;
    const [x, y] = local(event);
    pointers.delete(event.pointerId);
    if (pointers.size < 2) pinch = null;
    if (pointers.size === 0) {
      drag = null;
      canvas.style.cursor = hovered ? "pointer" : "grab";
    }
    if (wasTap && event.type === "pointerup") {
      const country = countryAt(x, y);
      if (country) onSelect?.(country);
    }
    if (prefersReducedMotion()) velocity = [0, 0];
    touch();
    redraw();
  }
  canvas.addEventListener("pointerup", endPointer, { signal });
  canvas.addEventListener("pointercancel", endPointer, { signal });
  canvas.addEventListener("pointerleave", (event) => { if (!drag) setHover(null, event); }, { signal });
  canvas.addEventListener("blur", () => { engaged = false; }, { signal });
  canvas.addEventListener("pointerenter", () => { canvas.style.cursor = "grab"; }, { signal });

  canvas.addEventListener(
    "wheel",
    (event) => {
      if (!engaged && !event.ctrlKey && !event.metaKey) return; // let the page scroll
      event.preventDefault();
      zoom = clamp(zoom * Math.exp(-event.deltaY * 0.0016), MIN_ZOOM, MAX_ZOOM);
      touch();
      redraw();
    },
    { signal, passive: false },
  );
  document.addEventListener("pointerdown", (event) => { if (!canvas.contains(event.target)) engaged = false; }, { signal });

  const KEYS = { ArrowLeft: [8, 0], ArrowRight: [-8, 0], ArrowUp: [0, 6], ArrowDown: [0, -6] };
  canvas.addEventListener(
    "keydown",
    (event) => {
      if (KEYS[event.key]) {
        rotation = [rotation[0] + KEYS[event.key][0] / zoom, clamp(rotation[1] + KEYS[event.key][1] / zoom, -90, 90)];
      } else if (event.key === "+" || event.key === "=") zoom = clamp(zoom * 1.3, MIN_ZOOM, MAX_ZOOM);
      else if (event.key === "-" || event.key === "_") zoom = clamp(zoom / 1.3, MIN_ZOOM, MAX_ZOOM);
      else return;
      event.preventDefault();
      touch();
      redraw();
    },
    { signal },
  );

  const resizeObserver = typeof ResizeObserver === "function" ? new ResizeObserver(resize) : null;
  resizeObserver?.observe(canvas);
  document.addEventListener("visibilitychange", () => (document.hidden ? null : schedule()), { signal });

  // --------------------------------------------------------------- public methods
  async function flyTo(feature, { duration = 1500 } = {}) {
    flying = true;
    autoRotate = false;
    velocity = [0, 0];
    selected = feature;
    setHover(null);
    const target = [-feature.properties.x, -feature.properties.y];
    const probe = geoOrthographic().clipAngle(90).rotate(target).translate([width / 2, height / 2]).scale(base);
    const [[x0, y0], [x1, y1]] = geoPath(probe).bounds(feature);
    const fit = (0.66 * Math.min(width, height)) / Math.max(x1 - x0, y1 - y0, 4);
    const targetZoom = clamp(fit, 1.3, FLY_MAX_ZOOM);
    const from = rotation.slice();
    const zoomFrom = zoom;
    const delta = ((target[0] - from[0] + 540) % 360) - 180; // the short way round
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
    await tween(
      duration,
      (t) => {
        // t is linear 0..1 (also jumps straight to 1 when motion is reduced): turn first, dive second, overlapping
        const turn = ease(clamp(t / 0.7, 0, 1));
        const dive = ease(clamp((t - 0.2) / 0.8, 0, 1));
        rotation = [from[0] + delta * turn, from[1] + (target[1] - from[1]) * turn];
        zoom = Math.exp(Math.log(zoomFrom) + (Math.log(targetZoom) - Math.log(zoomFrom)) * dive);
        draw();
      },
      (t) => t,
    );
    flying = false;
    redraw();
  }

  async function resetView({ duration = 900 } = {}) {
    flying = true;
    const zoomFrom = zoom;
    selected = null;
    await tween(duration, (t) => {
      zoom = zoomFrom + (1 - zoomFrom) * t;
      draw();
    });
    flying = false;
    autoRotate = true;
    touch();
    redraw();
  }

  return {
    resize,
    flyTo,
    resetView,
    zoomBy(factor) {
      zoom = clamp(zoom * factor, MIN_ZOOM, MAX_ZOOM);
      touch();
      redraw();
    },
    setVisible(value) {
      visible = value;
      if (value) schedule();
    },
    setSelected(feature) {
      selected = feature;
      redraw();
    },
    refreshTheme() {
      theme = readTheme();
      redraw();
    },
    /** For tests and keyboard helpers: what country is at this canvas position? */
    countryAt,
    rotateTo(lon, lat) {
      rotation = [-lon, -lat];
      redraw();
    },
    get zoom() {
      return zoom;
    },
    dispose() {
      disposed = true;
      controller.abort();
      resizeObserver?.disconnect();
      cancelAnimationFrame(frameId);
    },
  };
}
