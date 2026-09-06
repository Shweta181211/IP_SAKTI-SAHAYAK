/**
 * Pure-logic checks for the session helpers.
 *
 * `titleFor` and `relativeDay` decide what a user sees in the rail, and both are
 * plain functions over data - so they are worth pinning without a browser or a
 * test runner. Run with:
 *
 *     node src/useSessions.test.mjs
 *
 * The hook itself (localStorage, React state) is exercised by using the app;
 * these are the parts where a silent mistake would be invisible rather than
 * obvious.
 */

// Mirrors of the implementations in useSessions.ts. Kept in sync deliberately:
// this file is a guard on the RULES (truncation length, ellipsis, fallbacks),
// not a substitute for the module, which cannot be imported here without a TS
// build step.
const TITLE_CHARS = 34;

function titleFor(session) {
  if (session.title) return session.title;
  const first = session.turns[0];
  const text =
    first?.kind === "comparison" ? first.comparison?.product : first?.answer?.question;
  if (!text) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > TITLE_CHARS ? `${clean.slice(0, TITLE_CHARS).trimEnd()}…` : clean;
}

function relativeDay(ts, lang = "en") {
  const then = new Date(ts);
  const today = new Date();
  const startOf = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(today) - startOf(then)) / 86400000);
  if (days <= 0) return lang === "hi" ? "आज" : "today";
  if (days === 1) return lang === "hi" ? "कल" : "yesterday";
  return then.toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", {
    day: "numeric",
    month: "short",
  });
}

let failures = 0;
function check(name, ok, detail = "") {
  if (!ok) failures++;
  console.log(`  [${ok ? "PASS" : "FAIL"}] ${name}${detail ? "  - " + detail : ""}`);
}

const answerTurn = (question) => ({ id: 1, kind: "answer", answer: { question } });

console.log("SESSION LIST - titles and dates");

check(
  "a short question is the title verbatim",
  titleFor({ turns: [answerTurn("What is ABS?")] }) === "What is ABS?",
);

const long = titleFor({
  turns: [answerTurn("Can a classical churna from a First Schedule text be patented?")],
});
check("a long question is truncated with an ellipsis", long.endsWith("…"), long);
check("truncation stays within the budget", long.length <= TITLE_CHARS + 1, `${long.length}`);
check("truncation does not leave a trailing space", !/\s…$/.test(long), long);

check(
  "whitespace and newlines are collapsed",
  titleFor({ turns: [answerTurn("What   is\n\nABS?")] }) === "What is ABS?",
);

check(
  "a comparison thread is titled by its product",
  titleFor({ turns: [{ id: 1, kind: "comparison", comparison: { product: "ashwagandha extract" } }] }) ===
    "ashwagandha extract",
);

check("an empty thread has no title", titleFor({ turns: [] }) === "");
check(
  "an explicit title always wins",
  titleFor({ title: "Pinned", turns: [answerTurn("something else")] }) === "Pinned",
);

const DAY = 86400000;
check("today reads as 'today'", relativeDay(Date.now()) === "today");
check("yesterday reads as 'yesterday'", relativeDay(Date.now() - DAY) === "yesterday");
check(
  "older reads as a date, not a distance",
  !["today", "yesterday"].includes(relativeDay(Date.now() - 5 * DAY)),
  relativeDay(Date.now() - 5 * DAY),
);
check("Hindi labels are translated", relativeDay(Date.now(), "hi") === "आज");

console.log(failures ? `\n${failures} FAILURES\n` : "\nall passed\n");
process.exit(failures ? 1 : 0);
