// Turns API responses into DOM. Pure functions of (data, current language), so they can be re-run
// instantly when the language changes.
import { clear, el } from "./dom.js";
import { getLang, t } from "./i18n.js";

const MINUS = "\u2212";
const signed = (n) => (n > 0 ? `+${n}` : n < 0 ? `${MINUS}${Math.abs(n)}` : "0");
const sevLabel = (severity) => t(`severity.${severity}`);

function chip(severity) {
  return el("span", { className: "chip", dataset: { severity }, text: sevLabel(severity) });
}

function gauge(aqi, severity) {
  const marker = el("span", { className: "gauge__marker" });
  const percent = (Math.min(Math.max(aqi, 0), 500) / 500) * 100;
  requestAnimationFrame(() => marker.style.setProperty("--pos", `${percent}%`));
  return el(
    "div",
    { className: "gauge", attrs: { role: "img", "aria-label": t("gauge.label", { aqi, severity: sevLabel(severity) }) } },
    marker,
    el("div", { className: "gauge__bar" }, ...Array.from({ length: 6 }, () => el("span"))),
    el("div", { className: "gauge__scale", attrs: { "aria-hidden": "true" } }, el("span", { text: "0" }), el("span", { text: "500" })),
  );
}

function card(index, ...children) {
  const node = el("div", { className: "card reveal" }, ...children);
  node.style.setProperty("--i", index);
  return node;
}

function bulletList(items) {
  return el("ul", { className: "tips-list" }, ...items.map((text) => el("li", { text })));
}

function tipGroup(titleKey, items) {
  if (!items?.length) return null;
  return el("details", { className: "tips" }, el("summary", { text: t(titleKey) }), bulletList(items));
}

function explanationCard(index, explanation) {
  return card(
    index,
    el("h3", { text: t("explain.title") }),
    el("p", { text: explanation.text }),
    el("p", { className: "muted", text: t(`explain.${explanation.source}`) }),
  );
}

// ------------------------------------------------------------------ assessment
function meterCard(index, { title, value, severity, place, note, estimateLine, showGauge }) {
  return card(
    index,
    el("h3", { text: title }),
    el("div", { className: "meter__value" }, String(value), el("span", { className: "meter__unit", text: "AQI" })),
    place ? el("p", { className: "meter__place" }, el("span", { attrs: { "aria-hidden": "true" }, text: "📍 " }), place) : null,
    estimateLine ? el("p", { className: "meter__place", text: estimateLine }) : null,
    chip(severity),
    showGauge ? gauge(value, severity) : null,
    note ? el("p", { className: "muted", text: note }) : null,
  );
}

function factorsCard(index, factors) {
  if (!factors.length) return null;
  const pills = factors.map((f) => el("li", { className: "pill", text: `${t(`factor.${f.code}`)}: ${signed(f.effect)}` }));
  return card(index, el("h3", { text: t("factors.title") }), el("ul", { className: "pills" }, ...pills));
}

function fixesCard(index, fixes) {
  if (!fixes.length) return null;
  const biggest = Math.max(...fixes.map((f) => f.points_saved));
  const items = fixes.map((fix) => {
    const bar = el("span");
    requestAnimationFrame(() => bar.style.setProperty("--w", `${(fix.points_saved / biggest) * 100}%`));
    return el(
      "li",
      { className: "fix" },
      el("div", { className: "fix__head" }, el("span", { className: "fix__title", text: t(`fix.${fix.code}`) })),
      el("span", { className: "fix__saves", text: t("fix.saves", { n: fix.points_saved }) }),
      el("div", { className: "fix__bar", attrs: { "aria-hidden": "true" } }, bar),
    );
  });
  return card(index, el("h3", { text: t("fixes.title") }), el("ol", { className: "fixes" }, ...items));
}

export function renderAssessment(root, data) {
  clear(root);
  const { outdoor, indoor, fixes, explanation, location } = data;
  const alert = outdoor.alert
    ? el("p", { className: "notice notice--warn reveal", attrs: { role: "alert" }, text: t("alert.danger") })
    : null;
  const meters = el(
    "div",
    { className: "grid-2" },
    meterCard(1, { title: t("outdoor.title"), value: outdoor.aqi, severity: outdoor.severity, place: location, showGauge: true }),
    meterCard(2, {
      title: t("indoor.title"),
      value: indoor.score,
      severity: indoor.severity,
      estimateLine: t("indoor.estimate", { score: indoor.score, low: indoor.low, high: indoor.high }),
      note: t("indoor.note"),
      showGauge: true,
    }),
  );
  for (const node of [alert, meters, factorsCard(3, indoor.factors), fixesCard(4, fixes), explanationCard(5, explanation)]) {
    if (node) root.append(node);
  }
}

// ---------------------------------------------------------------------- advice
function maskCard(index, mask) {
  const children = [el("h3", { text: t("mask.title") }), el("p", { text: t(`mask.${mask.level}`) })];
  if (mask.level !== "none") children.push(el("p", { className: "muted", text: t("mask.reduction", { n: mask.exposure_reduction_pct }) }));
  if (mask.fit_tips.length) children.push(bulletList(mask.fit_tips));
  return card(index, ...children);
}

function travelCard(index, travel) {
  if (!travel?.options.length) return null;
  const head = el(
    "tr",
    {},
    ...["travel.mode", "travel.time", "travel.exposure", "travel.co2"].map((key) => el("th", { attrs: { scope: "col" }, text: t(key) })),
  );
  const rows = travel.options.map((option, position) => {
    const label = el("td", {}, t(`mode.${option.mode}`));
    if (position === 0) label.append(" ", el("span", { className: "badge", text: t("travel.best") }));
    const row = el(
      "tr",
      {},
      label,
      el("td", { text: option.minutes }),
      el("td", { text: option.exposure_aqi_hours.toFixed(1) }),
      el("td", { text: option.co2_saved_vs_car_kg.toFixed(2) }),
    );
    if (position === 0) row.dataset.best = "";
    return row;
  });
  const wrap = el(
    "div",
    { className: "table-wrap", attrs: { tabindex: 0, role: "region", "aria-label": t("travel.caption") } },
    el("table", {}, el("caption", { text: t("travel.caption") }), el("thead", {}, head), el("tbody", {}, ...rows)),
  );
  const notes = [];
  if (travel.car_is_fallback) notes.push(el("p", { className: "notice notice--warn", text: t("travel.car_fallback") }));
  if (travel.no_safe_option) notes.push(el("p", { className: "notice notice--warn", text: t("travel.no_safe") }));
  return card(index, el("h3", { text: t("travel.title") }), wrap, ...notes);
}

export function renderAdvice(root, data) {
  clear(root);
  const { advice, explanation } = data;
  const timeCard = advice.better_time
    ? card(
        2,
        el("p", {
          text: t("time.better", {
            hour: advice.better_time.hour,
            pct: advice.better_time.improvement_pct,
            aqi: advice.better_time.forecast_aqi,
            now: advice.better_time.current_aqi,
          }),
        }),
      )
    : null;
  const altCard = advice.optional_alternative
    ? card(3, el("h3", { text: t("alt.title") }), el("p", { text: advice.optional_alternative }))
    : null;
  const tips = [
    tipGroup("tips.duration", advice.duration_tips),
    tipGroup("tips.before_after", advice.before_after_tips),
    tipGroup("tips.recovery", advice.recovery_tips),
  ].filter(Boolean);
  const langNote = getLang() !== "en" && t("tips.lang_note") ? el("p", { className: "muted", text: t("tips.lang_note") }) : null;
  const tipsCard = tips.length ? card(4, ...tips, langNote) : null;

  for (const node of [maskCard(1, advice.mask), timeCard, travelCard(2, advice.travel), altCard, tipsCard, explanationCard(5, explanation)]) {
    if (node) root.append(node);
  }
}
