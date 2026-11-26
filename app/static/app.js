// Wires the page together: reads the forms, calls the API, renders the answers.
import { ApiError, postJson } from "./api.js";
import { applyStatic, getLang, loadStrings, setLang, t } from "./i18n.js";
import { createChat } from "./chat.js";
import { createLocation } from "./location.js";
import { scrollToNode } from "./motion.js";
import { initQuick } from "./quick.js";
import { renderAdvice, renderAssessment } from "./render.js";
import { initScrollEffects } from "./scroll.js";

const TRAVEL_KINDS = new Set(["school_run", "work_commute", "medical", "errand"]);
const REQUIRED_CHOICES = [
  ["windows", "short.windows"],
  ["cooking", "short.cooking"],
  ["heating", "short.heating"],
  ["purifier", "short.purifier"],
];

const state = { coords: null, context: null, assessData: null, planData: null, lastPlanInput: null, busy: false };
const $ = (id) => document.getElementById(id);
let chat = null; // the household conversation
let quick = null; // the quick home questions
let locator = null; // the globe and map

// ------------------------------------------------------------------ small UI helpers
function showError(message) {
  const box = $("error");
  box.textContent = message;
  box.hidden = false;
  box.scrollIntoView({ block: "nearest" });
}

function clearError() {
  const box = $("error");
  box.hidden = true;
  box.textContent = "";
}

const reveal = (id) => ($(id).hidden = false);

async function run(button, task) {
  if (state.busy) return;
  state.busy = true;
  button?.setAttribute("aria-busy", "true");
  $("status").textContent = t("loading");
  clearError();
  try {
    await task();
  } catch (error) {
    showError(error instanceof ApiError ? error.message : t("error.generic"));
  } finally {
    state.busy = false;
    button?.removeAttribute("aria-busy");
    $("status").textContent = "";
  }
}

const post = (path, body) => postJson(path, body, { networkMessage: t("error.network"), genericMessage: t("error.generic") });

// ------------------------------------------------------------------------ home form
function collectHome() {
  const form = $("home-form");
  const data = new FormData(form);
  const missing = [];
  const focusers = [];

  const household = chat.getResult();
  if (!household) {
    missing.push(t("short.who"));
    focusers.push(() => chat.focus());
  }
  const city = $("city").value.trim();
  const location = locator.getLocation() ?? state.coords ?? (city.length >= 2 ? { city } : null);
  if (!location) {
    missing.push(t("short.location"));
    focusers.push(() => locator.focusTarget().focus());
  }
  for (const [name, key] of REQUIRED_CHOICES) {
    if (!data.get(name)) {
      missing.push(t(key));
      focusers.push(() => form.querySelector(`input[name="${name}"]`).focus());
    }
  }
  if (missing.length) return { ok: false, message: t("error.missing", { list: missing.join(", ") }), focus: focusers[0] };

  const cooking = data.get("cooking");
  const checked = (name) => form.elements[name].checked;
  return {
    ok: true,
    context: {
      home: {
        profile: household.profile,
        windows: data.get("windows"),
        cooking,
        heating: data.get("heating"),
        has_purifier: data.get("purifier") === "yes",
        has_kitchen_exhaust: cooking !== "electric" && checked("has_kitchen_exhaust"),
        burns_incense: checked("burns_incense"),
        indoor_smoking: checked("indoor_smoking"),
      },
      location,
    },
  };
}

function showAssessment() {
  const { outdoor } = state.assessData;
  renderAssessment($("results-body"), state.assessData);
  document.body.dataset.severity = outdoor.severity;
  reveal("results");
  reveal("plan-section");
}

async function assess({ focusResults }) {
  state.assessData = await post("/api/assess", { ...state.context, language: getLang() });
  showAssessment();
  if (focusResults) {
    $("results-title").focus();
    $("results-title").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// ------------------------------------------------------------------------ plan form
function currentTiming() {
  return $("plan-form").elements.timing.value;
}

function showPlanResult(focus) {
  const data = state.planData;
  $("plan-question").hidden = true;
  $("fallback-form").hidden = true;
  $("advice").hidden = true;

  if (data.status === "ok") {
    renderAdvice($("advice-body"), data);
    reveal("advice");
    if (focus) {
      $("advice-title").focus();
      $("advice-title").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } else if (data.status === "needs_clarification") {
    $("plan-question").textContent = data.question;
    $("plan-question").hidden = false;
    if (focus) $("plan-text").focus();
  } else {
    $("fallback-form").hidden = false;
    if (focus) $("fallback-kind").focus();
  }
}

async function requestPlan(input, { focus }) {
  const body = {
    ...state.context,
    language: getLang(),
    timing: input.timing,
    ...(input.plan ? { plan: input.plan } : { plan_text: input.text }),
  };
  state.planData = await post("/api/plan", body);
  state.lastPlanInput = input;
  showPlanResult(focus);
}

function onPlanSubmit(event) {
  event.preventDefault();
  const text = $("plan-text").value.trim();
  const timing = currentTiming();
  if (!timing) {
    showError(t("error.timing"));
    document.querySelector('#plan-form input[name="timing"]').focus();
    return;
  }
  if (!text) {
    showError(t("error.plan"));
    $("plan-text").focus();
    return;
  }
  clearError();
  run($("plan-btn"), () => requestPlan({ text, timing }, { focus: true }));
}

function onFallbackSubmit(event) {
  event.preventDefault();
  const timing = currentTiming();
  if (!timing) {
    showError(t("error.timing"));
    document.querySelector('#plan-form input[name="timing"]').focus();
    return;
  }
  const kind = $("fallback-kind").value;
  const distance = Number($("fallback-distance").value || 0);
  if (TRAVEL_KINDS.has(kind) && !(distance > 0 && distance <= 200)) {
    showError(t("error.distance"));
    $("fallback-distance").focus();
    return;
  }
  clearError();
  run($("fallback-btn"), () => requestPlan({ timing, plan: { kind, distance_km: distance } }, { focus: true }));
}

// -------------------------------------------------------------------------- location
function useDeviceLocation() {
  if (!navigator.geolocation) return showError(t("error.geo"));
  navigator.geolocation.getCurrentPosition(
    ({ coords }) => {
      state.coords = {
        latitude: Math.round(coords.latitude * 100) / 100, // rounded for privacy
        longitude: Math.round(coords.longitude * 100) / 100,
      };
      clearError();
      locator.clear(); // a device location replaces any place picked on the map
      $("city").value = "";
      $("city").hidden = true;
      $("geo-btn").hidden = true;
      $("geo-active").hidden = false;
      $("geo-clear").focus();
    },
    () => showError(t("error.geo")),
    { timeout: 10_000, maximumAge: 600_000 },
  );
}

function showCityInput() {
  state.coords = null;
  $("city").hidden = false;
  $("geo-btn").hidden = false;
  $("geo-active").hidden = true;
}

function clearDeviceLocation() {
  showCityInput();
  $("city").focus();
}

/** A place was picked on the globe/map: it replaces any typed city or device location. */
function onPlaceChosen(place) {
  if (!place) return;
  showCityInput();
  $("city").value = "";
}

// ---------------------------------------------------------------------------- language
function syncLanguageButton() {
  $("lang-toggle").lang = getLang() === "en" ? "hi" : "en";
}

function onLanguageToggle() {
  setLang(getLang() === "en" ? "hi" : "en");
  syncLanguageButton();
  chat.rerender();
  quick.refresh();
  locator.refreshText();
  if (!state.assessData) return;
  // Re-label instantly from the data we already have, then refresh the AI wording in the new language.
  showAssessment();
  if (state.planData) showPlanResult(false);
  run($("lang-toggle"), async () => {
    await assess({ focusResults: false });
    if (state.lastPlanInput) await requestPlan(state.lastPlanInput, { focus: false });
  });
}

// -------------------------------------------------------------------------------- init
function toggleExhaustQuestion() {
  const cooking = $("home-form").elements.cooking.value;
  $("exhaust-field").hidden = cooking !== "gas" && cooking !== "biomass";
}

function onAssessSubmit(event) {
  event.preventDefault();
  const result = collectHome();
  if (!result.ok) {
    showError(result.message);
    result.focus?.();
    return;
  }
  state.context = result.context;
  state.planData = null;
  state.lastPlanInput = null;
  $("advice").hidden = true;
  run($("assess-btn"), () => assess({ focusResults: true }));
}

async function init() {
  try {
    await loadStrings();
  } catch {
    $("error").textContent = "Could not load the page text. Please refresh.";
    $("error").hidden = false;
    return;
  }
  setLang("en");
  syncLanguageButton();
  initScrollEffects();

  chat = createChat({
    log: $("chat-log"),
    input: $("chat-input"),
    send: $("chat-send"),
    chips: $("chat-chips"),
    actions: $("chat-actions"),
    composer: $("chat-composer"),
    onResult: () => {},
  });
  quick = initQuick({ form: $("home-form"), progress: $("quick-progress"), submit: $("assess-btn") });
  locator = createLocation(
    {
      scene: $("scene-location"), stage: $("stage"), canvas: $("globe"), svg: $("flatmap"), tooltip: $("tooltip"),
      title: $("stage-title"), loading: $("stage-loading"), hint: $("globe-hint"), back: $("map-back"),
      zoomIn: $("zoom-in"), zoomOut: $("zoom-out"), reset: $("map-reset"), search: $("place-search"),
      results: $("place-results"), count: $("place-count"), picked: $("location-picked"),
      pickedText: $("picked-text"), pickedChange: $("picked-change"), otherDetails: $("other-location"),
    },
    { onChange: onPlaceChosen },
  );
  locator.watch();
  globalThis.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => locator.refreshTheme());
  toggleExhaustQuestion();
  chat.start();
  $("chat-next").addEventListener("click", () => scrollToNode($("scene-location")));
  $("chat-change").addEventListener("click", () => chat.reset());
  $("city").addEventListener("input", () => {
    if ($("city").value.trim()) locator.clear(); // typing a city replaces a place picked on the map
  });

  $("home-form").addEventListener("submit", onAssessSubmit);
  $("home-form").addEventListener("change", (event) => {
    if (event.target.name === "cooking") toggleExhaustQuestion();
  });
  $("plan-form").addEventListener("submit", onPlanSubmit);
  $("fallback-form").addEventListener("submit", onFallbackSubmit);
  $("geo-btn").addEventListener("click", useDeviceLocation);
  $("geo-clear").addEventListener("click", clearDeviceLocation);
  $("lang-toggle").addEventListener("click", onLanguageToggle);
}

init();
