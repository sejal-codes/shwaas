// The household conversation: a text box, a few chat bubbles, and the follow-up logic from household.js.
import { clear, el } from "./dom.js";
import { interpretAnswer, interpretFollowUp, profileFor } from "./household.js";
import { t } from "./i18n.js";
import { wait } from "./motion.js";

const MAX_FAILURES = 2; // after this many misses, offer buttons so nobody gets stuck

export function createChat({ log, input, send, chips, actions, composer, onResult }) {
  let messages = []; // { from: "bot" | "you", key?, vars?, text? }
  let stage = "who"; // who -> followup -> which -> done
  let pending = [];
  let answer = { alone: false, children: null, elderly: null };
  let failures = 0;
  let busy = false;
  let started = false;
  let result = null;

  const bubble = (msg) =>
    el(
      "div",
      { className: `bubble bubble--${msg.from}` },
      el("span", { className: "sr-only", text: `${t(msg.from === "bot" ? "chat.bot_said" : "chat.you_said")} ` }),
      el("span", { className: "bubble__text", text: msg.key ? t(msg.key, msg.vars) : msg.text }),
    );

  function add(msg) {
    messages.push(msg);
    log.append(bubble(msg));
  }

  async function say(key, vars) {
    busy = true;
    const typing = el("div", { className: "typing", attrs: { "aria-hidden": "true" } }, el("span"), el("span"), el("span"));
    log.append(typing);
    await wait(620);
    typing.remove();
    add({ from: "bot", key, vars });
    busy = false;
  }

  const hideChips = () => {
    chips.hidden = true;
    clear(chips);
  };

  function showChips(kind) {
    clear(chips);
    const options =
      kind === "who"
        ? [["chat.opt_alone", { alone: true }], ["chat.opt_others", { others: true }]]
        : [["chat.opt_children", { children: true, elderly: false }], ["chat.opt_elderly", { children: false, elderly: true }],
           ["chat.opt_both", { children: true, elderly: true }], ["chat.opt_neither", { children: false, elderly: false }]];
    for (const [key, value] of options) {
      const button = el("button", { className: "chip-btn", attrs: { type: "button" }, text: t(key) });
      button.addEventListener("click", () => choose(key, value, kind));
      chips.append(button);
    }
    chips.hidden = false;
  }

  async function choose(key, value, kind) {
    if (busy) return;
    add({ from: "you", key });
    hideChips();
    if (kind === "who") {
      await handleWho(
        value.alone
          ? { understood: true, alone: true, children: false, elderly: false, needs: [] }
          : { understood: true, alone: false, children: null, elderly: null, needs: ["children", "elderly"] },
      );
    } else {
      await handleFollowUp({ understood: true, children: value.children, elderly: value.elderly });
    }
  }

  async function finish() {
    const children = answer.children === true;
    const elderly = answer.elderly === true;
    result = { profile: profileFor({ children, elderly }), alone: answer.alone, children, elderly };
    stage = "done";
    const key = answer.alone ? "chat.done_alone" : children && elderly ? "chat.done_both" : elderly ? "chat.done_elderly" : children ? "chat.done_children" : "chat.done_adults";
    await say(key);
    input.disabled = true;
    send.disabled = true;
    composer.classList.add("is-done");
    actions.hidden = false;
    onResult(result);
  }

  async function handleWho(parsed) {
    if (!parsed.understood) {
      failures += 1;
      await say("chat.retry_who");
      if (failures >= MAX_FAILURES) showChips("who");
      return;
    }
    failures = 0;
    answer = { alone: parsed.alone, children: parsed.children, elderly: parsed.elderly };
    if (parsed.alone || parsed.needs.length === 0) return finish();
    pending = parsed.needs;
    stage = "followup";
    await say(pending.length === 2 ? "chat.ask_dependents" : pending[0] === "children" ? "chat.ask_children" : "chat.ask_elderly");
  }

  async function handleFollowUp(parsed) {
    if (parsed.askWhich && stage === "followup") {
      stage = "which";
      await say("chat.ask_which");
      return;
    }
    if (!parsed.understood || parsed.askWhich) {
      failures += 1;
      await say("chat.retry_followup");
      if (failures >= MAX_FAILURES) showChips("followup");
      return;
    }
    for (const need of pending) answer[need] = parsed[need] ?? false;
    return finish();
  }

  async function submit() {
    const text = input.value.replace(/\s+/g, " ").trim().slice(0, 200);
    if (!text || busy || stage === "done") return;
    input.value = "";
    hideChips();
    add({ from: "you", text });
    if (stage === "who") await handleWho(interpretAnswer(text));
    else await handleFollowUp(interpretFollowUp(text, pending));
    if (stage !== "done") input.focus();
  }

  async function reset() {
    if (busy) return;
    stage = "who";
    pending = [];
    answer = { alone: false, children: null, elderly: null };
    failures = 0;
    result = null;
    onResult(null);
    hideChips();
    actions.hidden = true;
    composer.classList.remove("is-done");
    input.disabled = false;
    send.disabled = false;
    await say("chat.reset");
    input.focus();
  }

  send.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      submit();
    }
  });

  return {
    async start() {
      if (started) return;
      started = true;
      await say("chat.hello");
      await say("chat.ask_who");
    },
    reset,
    /** Re-draw every bubble in the current language (no typing animation). */
    rerender() {
      clear(log);
      for (const msg of messages) log.append(bubble(msg));
      if (!chips.hidden) showChips(stage === "who" ? "who" : "followup");
    },
    getResult: () => result,
    focus: () => input.focus(),
  };
}
