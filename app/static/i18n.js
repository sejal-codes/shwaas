// Language support (English / Hindi). Strings live in i18n.json; this module only looks them up.

const SUPPORTED = ["en", "hi"];
let strings = {};
let lang = "en";

export async function loadStrings() {
  const response = await fetch("/static/i18n.json");
  if (!response.ok) throw new Error("Could not load translations");
  strings = await response.json();
}

export const getLang = () => lang;

export function t(key, vars = {}) {
  const template = strings[lang]?.[key] ?? strings.en?.[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
}

/** Translate every element in the page that declares a data-i18n* attribute. */
export function applyStatic(root = document) {
  for (const node of root.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of root.querySelectorAll("[data-i18n-placeholder]")) {
    node.setAttribute("placeholder", t(node.dataset.i18nPlaceholder));
  }
  for (const node of root.querySelectorAll("[data-i18n-aria-label]")) {
    node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel));
  }
  document.documentElement.lang = lang;
  document.title = t("app.title");
}

export function setLang(next) {
  if (!SUPPORTED.includes(next)) return;
  lang = next;
  applyStatic();
}
