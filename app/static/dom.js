// Tiny DOM helpers. Text is only ever inserted as text nodes, never as HTML (no XSS surface).

export function el(tag, { className, text, attrs, dataset } = {}, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  for (const [name, value] of Object.entries(attrs ?? {})) node.setAttribute(name, String(value));
  Object.assign(node.dataset, dataset ?? {});
  for (const child of children) if (child) node.append(child);
  return node;
}

export const clear = (node) => node.replaceChildren();
