// Motion helpers. Every animation in the app goes through here so "reduce motion" is honoured everywhere.

export function prefersReducedMotion() {
  return typeof globalThis.matchMedia === "function" && globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
export const easeOutCubic = (t) => 1 - (1 - t) ** 3;

/** Resolves after `ms`, or immediately when the person prefers reduced motion. */
export const wait = (ms) => new Promise((resolve) => setTimeout(resolve, prefersReducedMotion() ? 0 : ms));

/** Calls onFrame(easedProgress 0..1) every frame, then resolves. Jumps straight to the end when reduced. */
export function tween(duration, onFrame, ease = easeInOutCubic) {
  if (prefersReducedMotion() || duration <= 0) {
    onFrame(1);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const start = performance.now();
    const step = (now) => {
      const progress = clamp((now - start) / duration, 0, 1);
      onFrame(ease(progress));
      if (progress < 1) requestAnimationFrame(step);
      else resolve();
    };
    requestAnimationFrame(step);
  });
}

export function scrollToNode(node, block = "start") {
  node.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block });
}
