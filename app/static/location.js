// The location experience: spin a real globe, pick a country, then pick your state on a flat map of it.
// Also owns the search box, which is the keyboard and screen-reader way to do the same thing.
import { clear, el } from "./dom.js";
import { t } from "./i18n.js";
import { clamp, scrollToNode, wait } from "./motion.js";
import { createFlatMap } from "./flatmap.js";
import { createGlobe } from "./globe.js";

const GEO_BASE = "/static/geo/";
const CODE = /^[A-Z0-9]{3}$/;
const MAX_RESULTS = 8;
const round2 = (n) => Math.round(n * 100) / 100;
const fold = (text) => String(text).normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url}`);
  return response.json();
}

export function createLocation(ui, { onChange }) {
  let geo = null;
  let globe = null;
  let flat = null;
  let countries = [];
  let ready = null;
  let mode = "globe";
  let country = null; // the feature that is open in map mode
  let place = null; // the saved choice
  let busy = false;
  let active = -1; // highlighted search result
  let options = [];
  const states = new Map();

  // ---------------------------------------------------------------------- helpers
  function readTheme() {
    const style = getComputedStyle(ui.canvas);
    const read = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
    return {
      oceanLight: read("--globe-ocean-light", "#1d4f8f"),
      oceanDeep: read("--globe-ocean-deep", "#0a1f45"),
      land: read("--globe-land", "#3b5f8c"),
      landHover: read("--globe-land-hover", "#5a86bd"),
      selected: read("--globe-selected", "rgba(94,234,212,0.55)"),
      border: read("--globe-border", "rgba(220,235,255,0.5)"),
      line: read("--globe-line", "rgba(255,255,255,0.12)"),
      glow: read("--globe-glow", "rgba(94,234,212,0.28)"),
      shade: read("--globe-shade", "rgba(2,8,24,0.55)"),
      shine: read("--globe-shine", "rgba(255,255,255,0.16)"),
      rim: read("--globe-rim", "rgba(190,230,255,0.45)"),
      accent: read("--accent", "#5eead4"),
    };
  }

  function setTitle(text) {
    ui.title.textContent = text;
    ui.title.hidden = !text;
  }

  function showTooltip(item, event) {
    if (!item || !event) {
      ui.tooltip.hidden = true;
      return;
    }
    ui.tooltip.textContent = item.properties?.n ?? item.name;
    ui.tooltip.hidden = false;
    const rect = ui.stage.getBoundingClientRect();
    ui.tooltip.style.setProperty("--x", `${clamp(event.clientX - rect.left + 16, 8, rect.width - 190)}px`);
    ui.tooltip.style.setProperty("--y", `${clamp(event.clientY - rect.top + 18, 8, rect.height - 44)}px`);
  }

  function showPicked() {
    if (!place) {
      ui.picked.hidden = true;
      return;
    }
    const label = place.state ? `${place.state}, ${place.country}` : place.country;
    ui.pickedText.textContent = t("location.picked", { place: label });
    ui.picked.hidden = false;
    ui.picked.classList.remove("pop");
    void ui.picked.offsetWidth; // restart the pop-in animation
    ui.picked.classList.add("pop");
  }

  function save(next) {
    place = next;
    showPicked();
    onChange(place);
  }

  // ---------------------------------------------------------------------- loading
  function ensureReady() {
    ready ??= (async () => {
      try {
        const [lib, world] = await Promise.all([import("./vendor/geo.js"), fetchJson(`${GEO_BASE}world.json`)]);
        geo = lib;
        countries = lib.feature(world, Object.values(world.objects)[0]).features;
        flat = createFlatMap({ svg: ui.svg, geo, onHover: showTooltip, onSelect: chooseRegion });
        globe = createGlobe({ canvas: ui.canvas, geo, features: countries, readTheme, onHover: showTooltip, onSelect: chooseCountry });
        if (globe) globe.resize();
        else ui.stage.dataset.globe = "off"; // no canvas support: the search box still reaches every country
        ui.stage.dataset.ready = "true";
        ui.loading.hidden = true;
        return true;
      } catch {
        ui.stage.dataset.ready = "error";
        ui.loading.hidden = false;
        ui.loading.textContent = t("location.error");
        ui.otherDetails.open = true;
        return false;
      }
    })();
    return ready;
  }

  async function loadStates(a3) {
    if (!CODE.test(a3)) throw new Error("bad country code");
    if (!states.has(a3)) states.set(a3, await fetchJson(`${GEO_BASE}states/${a3}.json`));
    return states.get(a3);
  }

  // --------------------------------------------------------------------- choosing
  async function chooseCountry(feature, { focus = true } = {}) {
    if (busy || !(await ensureReady())) return;
    busy = true;
    try {
      showTooltip(null);
      closeResults();
      const { n: name, a: a3 } = feature.properties;
      ui.stage.classList.add("is-flying");
      if (globe) {
        globe.setVisible(true);
        await globe.flyTo(feature);
      }
      let topology = null;
      try {
        topology = await loadStates(a3);
      } catch {
        topology = null;
      }
      if (!topology) {
        setTitle(t("map.error", { country: name }));
        saveCountryOnly(feature);
        ui.stage.classList.remove("is-flying");
        return;
      }
      country = feature;
      flat.show({ topology, object: Object.values(topology.objects)[0] });
      if (place?.a3 === a3 && place.state) flat.select(place.state, { notify: false });
      mode = "map";
      ui.stage.dataset.mode = "map";
      ui.svg.setAttribute("aria-label", t("map.label", { country: name }));
      ui.back.hidden = false;
      ui.hint.hidden = true;
      setTitle(t("map.pick", { country: name }));
      if (focus) ui.title.focus({ preventScroll: true });
      await wait(700);
      globe?.setVisible(false);
      ui.stage.classList.remove("is-flying");
    } finally {
      busy = false;
    }
  }

  function saveCountryOnly(feature) {
    const { n, a, x, y } = feature.properties;
    save({ country: n, a3: a, state: null, latitude: round2(y), longitude: round2(x) });
  }

  function chooseRegion({ name, lat, lon }) {
    save({ country: country.properties.n, a3: country.properties.a, state: name, latitude: round2(lat), longitude: round2(lon) });
  }

  async function backToGlobe() {
    if (busy || mode === "globe") return;
    busy = true;
    try {
      mode = "globe";
      ui.stage.dataset.mode = "globe";
      ui.back.hidden = true;
      ui.hint.hidden = false;
      setTitle("");
      globe?.setVisible(true);
      await wait(100);
      await globe?.resetView();
      await wait(500);
      flat.destroy();
      country = null;
    } finally {
      busy = false;
    }
  }

  // ----------------------------------------------------------------------- search
  function closeResults() {
    ui.results.hidden = true;
    ui.search.setAttribute("aria-expanded", "false");
    ui.search.removeAttribute("aria-activedescendant");
    active = -1;
  }

  function highlight(index) {
    active = index;
    [...ui.results.children].forEach((node, i) => node.setAttribute("aria-selected", String(i === index)));
    if (index >= 0) ui.search.setAttribute("aria-activedescendant", `place-option-${index}`);
    else ui.search.removeAttribute("aria-activedescendant");
    ui.results.children[index]?.scrollIntoView({ block: "nearest" });
  }

  function search(query) {
    const needle = fold(query).trim();
    if (!needle) return closeResults();
    const pool =
      mode === "map"
        ? flat.names().map((name) => ({ label: name, state: name }))
        : countries.map((feature) => ({ label: feature.properties.n, feature }));
    options = pool
      .map((item) => ({ item, at: fold(item.label).indexOf(needle) }))
      .filter(({ at }) => at >= 0)
      .sort((a, b) => a.at - b.at || a.item.label.localeCompare(b.item.label))
      .slice(0, MAX_RESULTS)
      .map(({ item }) => item);
    clear(ui.results);
    if (!options.length) {
      ui.results.append(el("li", { className: "finder__none", attrs: { role: "presentation" }, text: t("location.search.none") }));
    }
    options.forEach((item, i) => {
      const li = el("li", { className: "finder__option", attrs: { role: "option", id: `place-option-${i}`, "aria-selected": "false" }, text: item.label });
      li.addEventListener("mousedown", (event) => event.preventDefault()); // keep focus in the box
      li.addEventListener("click", () => pick(item));
      ui.results.append(li);
    });
    ui.results.hidden = false;
    ui.search.setAttribute("aria-expanded", "true");
    ui.count.textContent = options.length ? t("location.search.count", { n: options.length }) : t("location.search.none");
    highlight(options.length ? 0 : -1);
  }

  async function pick(item) {
    ui.search.value = "";
    closeResults();
    if (item.feature) {
      scrollToNode(ui.stage, "center");
      await chooseCountry(item.feature, { focus: false });
    } else if (flat) {
      flat.select(item.state);
      await flat.focusRegion(item.state);
    }
  }

  ui.search.addEventListener("focus", () => ensureReady());
  ui.search.addEventListener("input", async () => {
    if (await ensureReady()) search(ui.search.value);
  });
  ui.search.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (ui.results.hidden) return;
      event.preventDefault();
      const n = options.length;
      if (n) highlight((active + (event.key === "ArrowDown" ? 1 : -1) + n) % n);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (options[active]) pick(options[active]);
    } else if (event.key === "Escape") {
      closeResults();
    }
  });
  ui.search.addEventListener("blur", () => setTimeout(closeResults, 120));

  // ---------------------------------------------------------------------- controls
  ui.zoomIn.addEventListener("click", () => (mode === "map" ? flat.zoomBy(1.6) : globe?.zoomBy(1.4)));
  ui.zoomOut.addEventListener("click", () => (mode === "map" ? flat.zoomBy(1 / 1.6) : globe?.zoomBy(1 / 1.4)));
  ui.reset.addEventListener("click", () => (mode === "map" ? flat.reset() : globe?.resetView()));
  ui.back.addEventListener("click", backToGlobe);
  ui.pickedChange.addEventListener("click", () => {
    scrollToNode(ui.stage, "center");
    ui.search.focus();
  });

  // -------------------------------------------------------------------------- API
  return {
    /** Load the globe only once the person scrolls to it, so the page stays light. */
    watch() {
      if (!("IntersectionObserver" in globalThis)) {
        ensureReady();
        return;
      }
      new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) ensureReady();
            globe?.setVisible(entry.isIntersecting && mode === "globe");
          }
        },
        { threshold: 0.12 },
      ).observe(ui.scene);
    },
    ensureReady,
    getLocation() {
      if (!place) return null;
      const location = { country: place.country, latitude: place.latitude, longitude: place.longitude };
      if (place.state) location.state = place.state;
      return location;
    },
    /** Forget the choice (used when the person switches to a typed city or device location). */
    clear() {
      place = null;
      showPicked();
      flat?.clearSelection();
      globe?.setSelected(null);
    },
    focusTarget: () => ui.search,
    refreshText() {
      showPicked();
      if (mode === "map" && country) {
        const name = country.properties.n;
        setTitle(t("map.pick", { country: name }));
        ui.svg.setAttribute("aria-label", t("map.label", { country: name }));
      }
      if (ui.search.value) search(ui.search.value);
    },
    refreshTheme: () => globe?.refreshTheme(),
    get mode() {
      return mode;
    },
  };
}
