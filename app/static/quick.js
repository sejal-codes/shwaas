// The quick questions about the home: tap an answer and the next question glides into view.
import { t } from "./i18n.js";
import { scrollToNode, wait } from "./motion.js";

export function initQuick({ form, progress, submit }) {
  const beats = [...form.querySelectorAll(".beat")];
  let pointerPick = false;
  let timer = 0;

  const answered = (beat) => Boolean(beat.querySelector('input[type="radio"]:checked'));

  function refresh() {
    beats.forEach((beat) => beat.classList.toggle("is-answered", answered(beat)));
    const done = beats.filter(answered).length;
    progress.textContent = t("quick.progress", { done, total: beats.length });
    progress.classList.toggle("is-complete", done === beats.length);
  }

  async function advance(from) {
    const index = beats.indexOf(from);
    const next = beats.find((beat, i) => i > index && !answered(beat));
    await wait(420);
    scrollToNode(next ?? submit, "center");
  }

  // Only glide on to the next question for taps and clicks; keyboard users stay where they are.
  form.addEventListener("pointerdown", (event) => {
    if (!event.target.closest?.(".pill")) return;
    pointerPick = true;
    clearTimeout(timer);
    timer = setTimeout(() => (pointerPick = false), 700);
  });
  form.addEventListener("change", (event) => {
    const beat = event.target.closest?.(".beat");
    if (!beat || event.target.type !== "radio") return;
    refresh();
    if (pointerPick) advance(beat);
  });

  refresh();
  return { refresh };
}
