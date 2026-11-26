// The household-answer interpreter. Pure logic, so these run without a browser.
import assert from "node:assert/strict";
import { test } from "node:test";
import { interpretAnswer as ask, interpretFollowUp as follow, profileFor } from "../../app/static/household.js";

const shape = (r) => [r.alone, r.children, r.elderly, r.needs];

test("living alone, in many words, asks nothing more", () => {
  for (const text of ["Only me", "just me", "I live alone", "by myself", "On my own", "alone", "me only", "I live with nobody",
                      "Just myself!", "one person", "I'm solo", "Akela", "अकेला", "अकेली रहती हूँ"]) {
    assert.deepEqual(shape(ask(text)), [true, false, false, []], text);
  }
});

test("'me and my family' is vague, so both children and elderly must be asked", () => {
  for (const text of ["Me and my family", "family", "with my family", "my whole family", "everyone", "joint family", "मैं और मेरा परिवार"]) {
    assert.deepEqual(shape(ask(text)), [false, null, null, ["children", "elderly"]], text);
  }
});

test("naming parents or grandparents is enough: older adults, no children, no follow-up", () => {
  for (const text of ["Me and my parents", "my mom and dad", "I live with my grandparents", "with my mother", "me, my father and my in-laws", "माता पिता के साथ"]) {
    assert.deepEqual(shape(ask(text)), [false, false, true, []], text);
  }
});

test("naming children is enough: children, no elderly, no follow-up", () => {
  for (const text of ["Me and my kids", "my wife and two children", "me, my husband and our baby", "my son and daughter", "newborn twins and me", "me and my little brother", "मैं और मेरे बच्चे"]) {
    assert.deepEqual(shape(ask(text)), [false, true, false, []], text);
  }
});

test("naming only other adults means adults only", () => {
  for (const text of ["Me and my wife", "me and my husband", "two roommates and me", "me and my partner", "I live with friends", "my brother and I", "adults only", "just adults"]) {
    assert.deepEqual(shape(ask(text)), [false, false, false, []], text);
  }
});

test("both children and older adults named", () => {
  assert.deepEqual(shape(ask("me, my wife, our two kids and my parents")), [false, true, true, []]);
  assert.deepEqual(shape(ask("kids and grandma")), [false, true, true, []]);
});

test("a vague 'family' plus one specific group only asks about the missing group", () => {
  assert.deepEqual(shape(ask("my family, including my grandma")), [false, null, true, ["children"]]);
  assert.deepEqual(shape(ask("me and my family with two kids")), [false, true, null, ["elderly"]]);
});

test("head counts are understood", () => {
  assert.deepEqual(shape(ask("we are 4")), [false, null, null, ["children", "elderly"]]);
  assert.deepEqual(shape(ask("three of us")), [false, null, null, ["children", "elderly"]]);
  assert.deepEqual(shape(ask("family of five")), [false, null, null, ["children", "elderly"]]);
  assert.deepEqual(shape(ask("just 1 person")), [true, false, false, []]);
  assert.deepEqual(shape(ask("two adults")), [false, false, false, []]);
});

test("describing yourself is not the same as living with someone", () => {
  assert.deepEqual(shape(ask("I'm a single parent with two kids")), [false, true, false, []]);
  assert.deepEqual(shape(ask("I am a son living with my wife")), [false, false, false, []]);
  assert.deepEqual(shape(ask("we are parents of a toddler")), [false, true, false, []]);
});

test("things it cannot understand are reported, not guessed", () => {
  for (const text of ["", "   ", "hmm", "asdf", "what?", "tomorrow", "42 degrees"]) {
    assert.equal(ask(text).understood, false, JSON.stringify(text));
  }
  assert.equal(ask(null).understood, false);
});

test("punctuation, capitals and spacing do not matter", () => {
  assert.deepEqual(shape(ask("  ME   &  my   PARENTS!!! ")), [false, false, true, []]);
});

// ---------------------------------------------------------------- follow-up answers
const BOTH = ["children", "elderly"];

test("'no' to the combined question means neither", () => {
  for (const text of ["no", "Nope", "none", "nobody", "neither", "not really", "just adults", "only adults", "nahi", "नहीं"]) {
    assert.deepEqual(follow(text, BOTH), { understood: true, children: false, elderly: false }, text);
  }
});

test("naming who it is answers the question; the unmentioned group is a no", () => {
  assert.deepEqual(follow("yes, two kids", BOTH), { understood: true, children: true, elderly: false });
  assert.deepEqual(follow("my mother is 70", BOTH), { understood: true, children: false, elderly: true });
  assert.deepEqual(follow("kids and grandpa", BOTH), { understood: true, children: true, elderly: true });
  assert.deepEqual(follow("both", BOTH), { understood: true, children: true, elderly: true });
  assert.deepEqual(follow("just my daughter", BOTH), { understood: true, children: true, elderly: false });
});

test("negations apply to the right group", () => {
  assert.deepEqual(follow("no kids but my mom lives with us", BOTH), { understood: true, children: false, elderly: true });
  assert.deepEqual(follow("kids yes, no elderly", BOTH), { understood: true, children: true, elderly: false });
});

test("a bare 'yes' to the combined question asks which; to a single question it just answers", () => {
  assert.deepEqual(follow("yes", BOTH), { understood: true, askWhich: true });
  assert.deepEqual(follow("yeah", ["children"]), { understood: true, children: true });
  assert.deepEqual(follow("no", ["elderly"]), { understood: true, elderly: false });
});

test("a single-topic follow-up only returns that topic", () => {
  assert.deepEqual(follow("yes, one child", ["children"]), { understood: true, children: true });
  assert.deepEqual(follow("nobody like that", ["elderly"]), { understood: true, elderly: false });
});

test("unclear follow-ups are reported", () => {
  for (const text of ["", "maybe", "hmm", "what do you mean"]) assert.equal(follow(text, BOTH).understood, false, text);
  assert.equal(follow("yes", []).understood, false);
});

test("profile mapping", () => {
  assert.equal(profileFor({ children: false, elderly: false }), "adult");
  assert.equal(profileFor({ children: true, elderly: false }), "family_with_children");
  assert.equal(profileFor({ children: false, elderly: true }), "elderly");
  assert.equal(profileFor({ children: true, elderly: true }), "elderly", "stricter rules when both are at home");
});
