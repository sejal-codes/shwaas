// Scroll effects: scenes fade in as they arrive, a thin progress line, and a gentle parallax on the bubble.
import { prefersReducedMotion } from "./motion.js";

export function initScrollEffects() {
  const root = document.documentElement;
  const scenes = document.querySelectorAll(".scene");
  root.classList.add("js");

  if ("IntersectionObserver" in globalThis) {
    const seen = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("is-visible");
          seen.unobserve(entry.target);
        }
      },
      { threshold: 0.08, rootMargin: "0px 0px -6% 0px" },
    );
    scenes.forEach((scene) => seen.observe(scene));
  } else {
    scenes.forEach((scene) => scene.classList.add("is-visible"));
  }

  if (typeof globalThis.addEventListener !== "function") return; // no window to listen to (e.g. a test runner)
  const bar = document.getElementById("scroll-progress");
  let queued = false;
  const update = () => {
    queued = false;
    const max = root.scrollHeight - globalThis.innerHeight;
    const progress = max > 0 ? Math.min(1, Math.max(0, globalThis.scrollY / max)) : 0;
    bar?.style.setProperty("--p", progress.toFixed(4));
    if (!prefersReducedMotion()) root.style.setProperty("--parallax", String(Math.min(globalThis.scrollY, 700)));
  };
  globalThis.addEventListener(
    "scroll",
    () => {
      if (!queued) {
        queued = true;
        requestAnimationFrame(update);
      }
    },
    { passive: true },
  );
  update();
}
