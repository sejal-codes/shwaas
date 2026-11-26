// Understands free-text answers about who lives at home. Pure functions: no DOM, easy to test.
//
// interpretAnswer("Me and my parents")  -> { understood, alone, children, elderly, needs }
//   children / elderly are true, false, or null (null = unknown, and then `needs` lists what to ask).
// interpretFollowUp("yes, two kids", ["children", "elderly"]) -> { understood, children?, elderly?, askWhich? }
//
// Assumptions (also in the README): parents, grandparents and in-laws count as older adults, and a household that
// lists its members explicitly has no one it did not mention.

const CHILD = new Set([
  "kid", "kids", "child", "children", "son", "sons", "daughter", "daughters", "baby", "babies", "toddler",
  "toddlers", "infant", "infants", "newborn", "newborns", "teen", "teens", "teenager", "teenagers",
  "bachcha", "bachche", "bacche", "bacha", "beta", "beti", "बच्चा", "बच्चे", "बच्चों", "बेटा", "बेटे", "बेटी", "बेटियाँ", "बेटियां",
]);
const ELDER = new Set([
  "parent", "parents", "mother", "father", "mom", "mum", "mommy", "mummy", "dad", "daddy", "papa", "grandparent",
  "grandparents", "grandma", "grandpa", "grandmother", "grandfather", "granny", "grandad", "grandmom", "nana",
  "nani", "dada", "dadi", "elderly", "elders", "senior", "seniors", "mummyji",
  "माता", "पिता", "मम्मी", "पापा", "माँ", "मां", "दादा", "दादी", "नाना", "नानी", "बुजुर्ग", "बुज़ुर्ग", "सास", "ससुर",
]);
const OTHER_ADULT = new Set([
  "wife", "husband", "spouse", "partner", "girlfriend", "boyfriend", "fiance", "fiancee", "roommate", "roommates",
  "roomate", "roomates", "flatmate", "flatmates", "housemate", "housemates", "friend", "friends", "sibling",
  "siblings", "brother", "brothers", "sister", "sisters", "cousin", "cousins", "colleague", "colleagues", "pg",
  "pati", "patni", "पत्नी", "पति", "दोस्त", "भाई", "बहन",
]);
const FAMILY_VAGUE = new Set([
  "family", "families", "household", "everyone", "everybody", "relatives", "relations", "pariwar", "parivar",
  "परिवार", "joint",
]);
const ELDER_PHRASES = [" in laws ", " in law ", " old people ", " old folks ", " old man ", " old woman ", " old lady ", " senior citizen ", " senior citizens ", " older people ", " elderly people "];
const CHILD_PHRASES = [" little ones ", " little one "];
const ALONE_PHRASES = [
  " only me ", " just me ", " me only ", " me alone ", " only myself ", " just myself ", " by myself ", " on my own ",
  " alone ", " solo ", " myself ", " one person ", " just one ", " only one ", " nobody else ", " no one else ",
  " akela ", " akeli ", " akele ", " अकेला ", " अकेली ", " अकेले ", " with nobody ", " with no one ",
];
const ADULTS_ONLY_PHRASES = [" only adults ", " just adults ", " all adults ", " adults only ", " grown ups ", " grownups ", " only grown ups "];
const NUMBER_WORDS = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12 };
const NEGATIONS = new Set(["no", "nope", "nah", "none", "nobody", "neither", "nahi", "nahin", "नहीं", "नही", "not", "without"]);
const YES = new Set(["yes", "yeah", "yep", "yup", "sure", "haan", "han", "हाँ", "हां", "ya", "yea"]);
const SMALL_SIBLING = new Set(["little", "younger", "small", "baby", "kid"]);

export function normalize(text) {
  return String(text ?? "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{M}\p{N}]+/gu, " ")
    .trim();
}

const tokensOf = (norm) => (norm ? norm.split(" ") : []);
const hasPhrase = (norm, phrases) => phrases.some((p) => ` ${norm} `.includes(p));

/** "I am a son", "as a mother": the person is describing themselves, not someone they live with. */
function isSelfRole(tokens, i) {
  const prev = tokens[i - 1];
  const before = tokens[i - 2];
  if (["am", "m", "being", "becoming"].includes(prev)) return true;
  if (["a", "an", "the"].includes(prev) && ["am", "m", "as", "being", "become", "becoming"].includes(before)) return true;
  if (["single", "new", "young", "working", "proud"].includes(prev)) return true;
  if ((tokens[i] === "parents" || tokens[i] === "parent") && (prev === "are" || tokens[i + 1] === "of")) return true;
  return false;
}

function countPeople(norm) {
  const num = (s) => (/^\d+$/.test(s) ? Number(s) : NUMBER_WORDS[s]);
  const patterns = [
    /\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve) (?:of us|people|person|persons|member|members|folks|adults|adult)\b/,
    /\b(?:we are|there are|were|family of|group of|total|live with) (\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b/,
  ];
  for (const pattern of patterns) {
    const match = norm.match(pattern);
    if (match && num(match[1]) !== undefined) return num(match[1]);
  }
  return null;
}

/** Looks for words of each kind, returning {children, elderly, other, vague} booleans. */
function scan(norm) {
  const tokens = tokensOf(norm);
  const found = { children: false, elderly: false, other: false, vague: false };
  tokens.forEach((token, i) => {
    if (CHILD.has(token) && !isSelfRole(tokens, i)) found.children = true;
    else if (ELDER.has(token) && !isSelfRole(tokens, i)) found.elderly = true;
    else if (OTHER_ADULT.has(token)) {
      if (["brother", "brothers", "sister", "sisters", "sibling", "siblings"].includes(token) && SMALL_SIBLING.has(tokens[i - 1])) {
        found.children = true;
      } else found.other = true;
    } else if (FAMILY_VAGUE.has(token)) found.vague = true;
  });
  if (hasPhrase(norm, ELDER_PHRASES)) found.elderly = true;
  if (hasPhrase(norm, CHILD_PHRASES)) found.children = true;
  return found;
}

export function interpretAnswer(text) {
  const norm = normalize(text);
  if (!norm) return { understood: false };
  const found = scan(norm);
  const count = countPeople(norm);
  const adultsOnly =
    hasPhrase(norm, ADULTS_ONLY_PHRASES) ||
    /\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|all|only|just) adults?\b/.test(norm);
  const anyMember = found.children || found.elderly || found.other || found.vague || adultsOnly || (count !== null && count > 1);

  if (!anyMember) {
    if (hasPhrase(norm, ALONE_PHRASES) || count === 1) {
      return { understood: true, alone: true, children: false, elderly: false, needs: [] };
    }
    return { understood: false };
  }

  const unknownIsPossible = (found.vague || (count !== null && count > 1)) && !adultsOnly;
  const children = found.children ? true : unknownIsPossible ? null : false;
  const elderly = found.elderly ? true : unknownIsPossible ? null : false;
  const needs = [];
  if (children === null) needs.push("children");
  if (elderly === null) needs.push("elderly");
  return { understood: true, alone: false, children, elderly, needs };
}

/** Reads an answer to "Are there any children or elderly people living with you?" (or a narrower version). */
export function interpretFollowUp(text, needs) {
  const norm = normalize(text);
  if (!norm || !needs?.length) return { understood: false };
  const tokens = tokensOf(norm);
  const result = {};
  const negated = (i) => NEGATIONS.has(tokens[i - 1]) || NEGATIONS.has(tokens[i - 2]);
  let mentioned = false;

  tokens.forEach((token, i) => {
    if (CHILD.has(token) && !isSelfRole(tokens, i)) {
      result.children = !negated(i);
      mentioned = true;
    } else if (ELDER.has(token) && !isSelfRole(tokens, i)) {
      result.elderly = !negated(i);
      mentioned = true;
    }
  });
  if (hasPhrase(norm, ELDER_PHRASES)) {
    result.elderly = !tokens.some((t, i) => NEGATIONS.has(t) && i < 3);
    mentioned = true;
  }
  if (hasPhrase(norm, CHILD_PHRASES)) {
    result.children = true;
    mentioned = true;
  }

  const both = tokens.includes("both") || hasPhrase(norm, [" both of them ", " dono "]);
  const neither = tokens.includes("neither") || hasPhrase(norm, [" no one ", " nobody ", " none of them ", ...ADULTS_ONLY_PHRASES]);
  const startsNegative = NEGATIONS.has(tokens[0]) && !mentioned;
  const saysYes = YES.has(tokens[0]) && !mentioned && !both;

  if (both) Object.assign(result, { children: true, elderly: true });
  if (neither || startsNegative) Object.assign(result, { children: false, elderly: false });
  if (saysYes) {
    if (needs.length === 1) result[needs[0]] = true;
    else return { understood: true, askWhich: true };
  }

  const answered = Object.keys(result).length > 0;
  if (!answered) return { understood: false };
  // Anything they were asked about but did not mention is taken as "no".
  const out = {};
  for (const need of needs) out[need] = result[need] ?? false;
  return { understood: true, ...out };
}

export function profileFor({ children, elderly }) {
  // Both at home: the stricter older-adult rules are used (documented in the README).
  if (elderly) return "elderly";
  if (children) return "family_with_children";
  return "adult";
}
