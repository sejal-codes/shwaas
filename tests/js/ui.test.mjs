// Behaviour tests for the web UI: the real app.js against index.html in jsdom, with responses captured from
// the real API (tests/js_fixtures.py) and the real map files. Run: npm install && npm test
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { JSDOM, VirtualConsole } from "jsdom";

const STATIC = new URL("../../app/static/", import.meta.url);
const read = (name) => readFileSync(new URL(name, STATIC), "utf8");
const fixture = (name) => JSON.parse(readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));
const I18N = JSON.parse(read("i18n.json"));
const HTML = read("index.html");
const reply = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
let runCounter = 0;

async function waitFor(check, ms = 3000) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    if (check()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error("timed out waiting for condition");
}

async function boot({ routes = {}, geolocation } = {}) {
  const dom = new JSDOM(HTML, { url: "http://localhost/", pretendToBeVisual: true, virtualConsole: new VirtualConsole() });
  const { window } = dom;
  const { document } = window;
  window.HTMLElement.prototype.scrollIntoView = () => {};
  globalThis.document = document;
  globalThis.FormData = window.FormData;
  globalThis.AbortController = window.AbortController; // jsdom elements only accept jsdom's own signals
  globalThis.requestAnimationFrame = (fn) => setTimeout(() => fn(performance.now()), 0);
  globalThis.cancelAnimationFrame = clearTimeout;
  globalThis.matchMedia = (query) => ({ matches: query.includes("reduce"), addEventListener() {}, removeEventListener() {} });
  Object.defineProperty(globalThis, "navigator", { value: { geolocation }, configurable: true });

  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    if (url === "/static/i18n.json") return reply(I18N);
    if (url.startsWith("/static/geo/")) return reply(JSON.parse(read(url.replace("/static/", ""))));
    const body = JSON.parse(options.body);
    calls.push({ url, body });
    const route = routes[url];
    if (!route) throw new Error(`no route for ${url}`);
    return typeof route === "function" ? route(body) : route;
  };

  await import(`../../app/static/app.js?run=${runCounter++}`);
  await waitFor(() => document.querySelectorAll(".bubble--bot").length >= 2);

  const $ = (id) => document.getElementById(id);
  const ui = {
    window, document, calls, $,
    pick(name, value) {
      const input = document.querySelector(`input[name="${name}"][value="${value}"]`);
      input.checked = true;
      input.dispatchEvent(new window.Event("change", { bubbles: true }));
    },
    submit: (id) => $(id).dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })),
    bots: () => [...document.querySelectorAll(".bubble--bot .bubble__text")].map((n) => n.textContent),
    async say(text) {
      const before = document.querySelectorAll(".bubble--bot").length;
      $("chat-input").value = text;
      $("chat-send").click();
      await waitFor(() => document.querySelectorAll(".bubble--bot").length > before);
    },
    async answerHousehold(text = "Me and my wife") {
      await ui.say(text);
      await waitFor(() => !$("chat-actions").hidden);
    },
    async fillHome({ cooking = "gas", city = "Delhi", purifier = "no", household = "Me and my wife" } = {}) {
      await ui.answerHousehold(household);
      ui.pick("windows", "open");
      ui.pick("cooking", cooking);
      ui.pick("heating", "none");
      ui.pick("purifier", purifier);
      if (city) $("city").value = city;
    },
    error: () => ($("error").hidden ? null : $("error").textContent),
  };
  return ui;
}

const standardRoutes = () => ({ "/api/assess": reply(fixture("assess")), "/api/plan": reply(fixture("plan_ok")) });

async function assessed(options) {
  const ui = await boot(options ?? { routes: standardRoutes() });
  await ui.fillHome();
  ui.submit("home-form");
  await waitFor(() => !ui.$("results").hidden && ui.$("results-body").children.length > 0);
  return ui;
}

// ---------------------------------------------------------------- conversation
test("the conversation opens with a greeting and the household question", async () => {
  const ui = await boot();
  assert.deepEqual(ui.bots(), [I18N.en["chat.hello"], I18N.en["chat.ask_who"]]);
  assert.equal(ui.document.documentElement.lang, "en");
  assert.equal(ui.$("results").hidden, true);
});

test("living alone asks nothing about children or elderly people", async () => {
  const ui = await boot();
  await ui.answerHousehold("Only me");
  assert.equal(ui.bots().length, 3);
  assert.equal(ui.bots()[2], I18N.en["chat.done_alone"]);
  assert.equal(ui.$("chat-input").disabled, true);
});

test("'me and my family' asks the explicit question once, and a clear answer ends it", async () => {
  const ui = await boot();
  await ui.say("Me and my family");
  assert.equal(ui.bots().at(-1), I18N.en["chat.ask_dependents"]);
  await ui.say("yes, two kids");
  await waitFor(() => !ui.$("chat-actions").hidden);
  assert.equal(ui.bots().at(-1), I18N.en["chat.done_children"]);
  assert.equal(ui.bots().filter((b) => b === I18N.en["chat.ask_dependents"]).length, 1, "never asked twice");
});

test("naming parents is enough: no follow-up, treated as elders at home", async () => {
  const ui = await boot();
  await ui.answerHousehold("Me and my parents");
  assert.equal(ui.bots().at(-1), I18N.en["chat.done_elderly"]);
  assert.equal(ui.bots().length, 3);
});

test("unclear answers get a gentle retry, then tappable options so nobody is stuck", async () => {
  const ui = await boot();
  await ui.say("hmm");
  assert.equal(ui.bots().at(-1), I18N.en["chat.retry_who"]);
  await ui.say("banana");
  assert.equal(ui.$("chat-chips").hidden, false);
  ui.$("chat-chips").querySelector("button").click(); // "Just me"
  await waitFor(() => !ui.$("chat-actions").hidden);
  assert.equal(ui.bots().at(-1), I18N.en["chat.done_alone"]);
});

test("'Change my answer' starts the question again", async () => {
  const ui = await boot();
  await ui.answerHousehold("Only me");
  ui.$("chat-change").click();
  await waitFor(() => ui.bots().at(-1) === I18N.en["chat.reset"]);
  assert.equal(ui.$("chat-input").disabled, false);
  assert.equal(ui.$("chat-actions").hidden, true);
});

// ------------------------------------------------------------- form + location
test("an incomplete form lists what is missing, focuses the first thing and calls nothing", async () => {
  const ui = await boot();
  ui.submit("home-form");
  for (const key of ["short.who", "short.location", "short.windows", "short.cooking", "short.heating", "short.purifier"]) {
    assert.ok(ui.error().includes(I18N.en[key]), key);
  }
  assert.equal(ui.document.activeElement.id, "chat-input");
  assert.equal(ui.calls.length, 0);
});

test("the exhaust question only appears for gas or wood cooking, and is never sent for electric", async () => {
  const ui = await boot({ routes: standardRoutes() });
  assert.equal(ui.$("exhaust-field").hidden, true);
  ui.pick("cooking", "gas");
  assert.equal(ui.$("exhaust-field").hidden, false);
  ui.document.querySelector('input[name="has_kitchen_exhaust"]').checked = true;
  await ui.fillHome({ cooking: "electric" });
  assert.equal(ui.$("exhaust-field").hidden, true);
  ui.submit("home-form");
  await waitFor(() => ui.calls.length === 1);
  assert.equal(ui.calls[0].body.home.has_kitchen_exhaust, false);
});

test("a valid submit sends every answer, including the purifier, and shows the results", async () => {
  const ui = await boot({ routes: standardRoutes() });
  await ui.fillHome({ purifier: "yes" });
  ui.submit("home-form");
  await waitFor(() => !ui.$("results").hidden && ui.$("results-body").children.length > 0);
  assert.deepEqual(ui.calls[0].body, {
    home: { profile: "adult", windows: "open", cooking: "gas", heating: "none",
            has_purifier: true, has_kitchen_exhaust: false, burns_incense: false, indoor_smoking: false },
    location: { city: "Delhi" },
    language: "en",
  });
  const data = fixture("assess");
  assert.ok(ui.$("results-body").textContent.includes(String(data.outdoor.aqi)));
  assert.equal(ui.document.body.dataset.severity, data.outdoor.severity);
  assert.equal(ui.$("plan-section").hidden, false);
});

test("the household answer decides the profile that is sent", async () => {
  for (const [text, profile] of [["Me and my kids", "family_with_children"], ["Me and my parents", "elderly"], ["Only me", "adult"]]) {
    const ui = await boot({ routes: standardRoutes() });
    await ui.fillHome({ household: text });
    ui.submit("home-form");
    await waitFor(() => ui.calls.length === 1);
    assert.equal(ui.calls[0].body.home.profile, profile, text);
  }
});

test("choosing a country and state on the map saves them as the location", async () => {
  const ui = await boot({ routes: standardRoutes() });
  await ui.fillHome({ city: "" });
  const search = ui.$("place-search");
  search.value = "India";
  search.dispatchEvent(new ui.window.Event("input", { bubbles: true }));
  await waitFor(() => ui.$("place-results").children.length > 0);
  search.dispatchEvent(new ui.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await waitFor(() => ui.$("stage").dataset.mode === "map");
  assert.equal(ui.$("flatmap").querySelectorAll(".region").length, 36, "India's real states and territories are drawn");
  assert.ok(ui.$("stage-title").textContent.includes("India"));

  search.value = "karna";
  search.dispatchEvent(new ui.window.Event("input", { bubbles: true }));
  await waitFor(() => ui.$("place-results").children.length > 0);
  search.dispatchEvent(new ui.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await waitFor(() => !ui.$("location-picked").hidden);
  assert.equal(ui.$("picked-text").textContent, "You’re in Karnataka, India.");
  assert.equal(ui.$("flatmap").querySelector(".region.is-selected").dataset.name, "Karnataka");

  ui.submit("home-form");
  await waitFor(() => ui.calls.length === 1);
  const { location } = ui.calls[0].body;
  assert.equal(location.country, "India");
  assert.equal(location.state, "Karnataka");
  assert.ok(Number.isFinite(location.latitude) && Number.isFinite(location.longitude) && !("city" in location));
});

test("typing a city afterwards replaces the map choice", async () => {
  const ui = await boot({ routes: standardRoutes() });
  await ui.fillHome({ city: "" });
  const search = ui.$("place-search");
  const type = async (text) => {
    search.value = text;
    search.dispatchEvent(new ui.window.Event("input", { bubbles: true }));
    await waitFor(() => ui.$("place-results").children.length > 0);
    search.dispatchEvent(new ui.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  };
  await type("India");
  await waitFor(() => ui.$("stage").dataset.mode === "map");
  await type("karna");
  await waitFor(() => !ui.$("location-picked").hidden);
  ui.$("city").value = "Mumbai";
  ui.$("city").dispatchEvent(new ui.window.Event("input", { bubbles: true }));
  assert.equal(ui.$("location-picked").hidden, true);
  ui.submit("home-form");
  await waitFor(() => ui.calls.length === 1);
  assert.deepEqual(ui.calls[0].body.location, { city: "Mumbai" });
});

test("device location is rounded, replaces the city box, and can be cleared", async () => {
  const geolocation = { getCurrentPosition: (ok) => ok({ coords: { latitude: 12.97161, longitude: 77.59456 } }) };
  const ui = await boot({ routes: standardRoutes(), geolocation });
  await ui.fillHome({ city: "" });
  ui.$("geo-btn").click();
  assert.equal(ui.$("city").hidden, true);
  ui.submit("home-form");
  await waitFor(() => ui.calls.length === 1);
  assert.deepEqual(ui.calls[0].body.location, { latitude: 12.97, longitude: 77.59 });
  ui.$("geo-clear").click();
  assert.equal(ui.$("city").hidden, false);
});

test("a denied location permission falls back to typing a city", async () => {
  const ui = await boot({ geolocation: { getCurrentPosition: (_ok, fail) => fail(new Error("denied")) } });
  ui.$("geo-btn").click();
  assert.equal(ui.error(), I18N.en["error.geo"]);
});

// ------------------------------------------------------- unchanged flows: plan etc.
test("a flexible plan shows travel options, a Best badge and a better time", async () => {
  const ui = await assessed();
  ui.$("plan-text").value = "buy vegetables";
  ui.pick("timing", "flexible");
  ui.submit("plan-form");
  await waitFor(() => !ui.$("advice").hidden);
  const rows = ui.$("advice-body").querySelectorAll("tbody tr");
  assert.ok(rows.length >= 2 && rows[0].textContent.includes(I18N.en["travel.best"]));
  assert.ok(ui.$("advice-body").textContent.includes("11:00"));
});

test("a vague plan shows one question; an offline AI reader falls back to a plain form", async () => {
  const ui = await assessed({ routes: { "/api/assess": reply(fixture("assess")), "/api/plan": (b) => reply(b.plan ? fixture("plan_fixed_school") : fixture("plan_clarify")) } });
  ui.$("plan-text").value = "going out";
  ui.pick("timing", "fixed");
  ui.submit("plan-form");
  await waitFor(() => !ui.$("plan-question").hidden);
  assert.equal(ui.$("plan-question").textContent, "Where are you going?");
});

test("the plan needs a timing choice and some text", async () => {
  const ui = await assessed();
  ui.$("plan-text").value = "buy vegetables";
  ui.submit("plan-form");
  assert.equal(ui.error(), I18N.en["error.timing"]);
  ui.pick("timing", "fixed");
  ui.$("plan-text").value = "  ";
  ui.submit("plan-form");
  assert.equal(ui.error(), I18N.en["error.plan"]);
});

test("Hindi relabels the conversation, the form and the results at once", async () => {
  const ui = await assessed();
  ui.$("lang-toggle").click();
  assert.equal(ui.document.documentElement.lang, "hi");
  assert.equal(ui.bots()[0], I18N.hi["chat.hello"]);
  assert.equal(ui.$("env-title").textContent, I18N.hi["env.title"]);
  assert.ok(ui.$("results-body").textContent.includes(I18N.hi["severity.very_poor"]));
  await waitFor(() => ui.calls.length === 2);
  assert.equal(ui.calls[1].body.language, "hi");
});

test("text from the server is shown as text, never as HTML", async () => {
  const evil = fixture("assess");
  evil.explanation.text = '<img src=x onerror="window.pwned=1"><script>window.pwned=1</script>';
  evil.location = "<b>Delhi</b>";
  const ui = await assessed({ routes: { "/api/assess": reply(evil) } });
  assert.equal(ui.$("results-body").querySelector("img, script, b"), null);
});

test("server and network errors are explained, and the button is never left busy", async () => {
  const ui = await boot({ routes: { "/api/assess": reply({ error: "We could not find that place. Try a nearby city." }, 502) } });
  await ui.fillHome({ city: "Nowhereville" });
  ui.submit("home-form");
  await waitFor(() => ui.error() !== null);
  assert.equal(ui.error(), "We could not find that place. Try a nearby city.");
  assert.equal(ui.$("assess-btn").hasAttribute("aria-busy"), false);
});
