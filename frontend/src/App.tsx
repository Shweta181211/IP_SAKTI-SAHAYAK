import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import {
  CancelledError,
  askQuestion,
  compareCategories,
  compareJurisdictions,
  fetchNextSteps,
} from "./api";
import { AnswerView } from "./components/AnswerView";
import { ComparisonView } from "./components/ComparisonView";
import { JurisdictionCompareView } from "./components/JurisdictionCompareView";
import { NextStepsPanel } from "./components/NextStepsPanel";
import { JurisdictionExpander } from "./components/JurisdictionExpander";
import { useVoiceInput } from "./useVoiceInput";
import { SessionList } from "./components/SessionList";
import { useSessions, type Turn } from "./useSessions";
import { printBriefing, rememberAnswer } from "./printBriefing";
import { useShell } from "./Shell";
import { EXAMPLES, FEATURE_CHIPS, STRINGS } from "./i18n";
import type { NextSteps, ResponseStyle } from "./types";

type Jurisdiction = "india" | "international";
// The standalone "compare jurisdictions" mode is gone: the same comparison is
// now reached progressively from an ordinary answer, which costs less and
// reads better. Two routes to one feature is worse than one good route.
type Mode = "ask" | "compare";

// `Turn` and transcript persistence now live in useSessions.ts, which keeps one
// transcript per named consultation rather than a single anonymous blob that
// "End session" destroyed.
const STYLE_KEY = "ipsakti.style.v1";

/** `lockedMode` is the mode this route opens in. It is a starting point, not a
 *  lock: the rail can still switch, because a user who lands on /compare and
 *  then wants to ask a question should not have to find the right URL. */
export default function App({ lockedMode = "ask" }: { lockedMode?: Mode }) {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>(lockedMode);
  const [searchParams] = useSearchParams();
  const location = useLocation();
  // Language, log consent and health are session-wide and owned by Root, so
  // the header and this page cannot disagree about them. `setUiLang` is not
  // taken: the language switch lives in the Shell header and nowhere else, so
  // there is exactly one control for it on screen.
  const { uiLang, logConsent, setLogConsent, health, healthChecked } = useShell();
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("india");
  const [menuOpen, setMenuOpen] = useState(false);

  /* The rail is resizable and can be put away, the way a chat tool's sidebar
     is. Both are remembered: a reader who has set the rail to their liking
     should not have to set it again on the next question.

     Width is clamped in the setter rather than only in CSS, so a corrupted or
     hand-edited stored value cannot leave the rail off-screen with no way to
     drag it back. */
  const RAIL_MIN = 200;
  const RAIL_MAX = 460;
  const [railWidth, setRailWidth] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem("ipsakti.rail.w"));
      return v >= RAIL_MIN && v <= RAIL_MAX ? v : 272;
    } catch {
      return 272;
    }
  });
  const [railHidden, setRailHidden] = useState<boolean>(() => {
    try {
      return localStorage.getItem("ipsakti.rail.hidden") === "1";
    } catch {
      return false;
    }
  });
  const dragging = useRef(false);

  useEffect(() => {
    try {
      localStorage.setItem("ipsakti.rail.w", String(railWidth));
      localStorage.setItem("ipsakti.rail.hidden", railHidden ? "1" : "0");
    } catch {
      /* a private window just means the rail resets next time */
    }
  }, [railWidth, railHidden]);

  /* Listeners go on the window, not the handle: a fast drag outruns the
     handle's own box and the rail would stop following the pointer. */
  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragging.current) return;
      e.preventDefault();
      setRailWidth(Math.min(RAIL_MAX, Math.max(RAIL_MIN, e.clientX)));
    };
    const up = () => {
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);
  // Consent to retain the QUESTION TEXT in the server's audit log. Off by
  // default and remembered per browser: the operational record that makes the
  // system auditable holds no user content either way, so this is a genuine
  // choice rather than a formality. See backend/app/audit.py.
  // Phrasing only. Kept per browser because it is a reading preference, not a
  // property of any one answer.
  const [style, setStyle] = useState<ResponseStyle>(() => {
    try {
      return (localStorage.getItem(STYLE_KEY) as ResponseStyle) || "legal";
    } catch {
      return "legal";
    }
  });
  // Next steps are fetched per turn, on request. Keyed by turn id so each
  // answer keeps its own, and nothing is fetched for turns nobody asked about.
  const [nextSteps, setNextSteps] = useState<Record<number, NextSteps>>({});
  const [stepsLoading, setStepsLoading] = useState<number | null>(null);
  const [busySide, setBusySide] = useState<number | null>(null);
  const [busyCompare, setBusyCompare] = useState<number | null>(null);

  const {
    sessions,
    activeId,
    turns,
    setTurns,
    startSession,
    openSession,
    removeSession,
    clearSessions,
  } = useSessions();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Held so the Stop button can abort the in-flight request. A ref, not state:
  // changing it must not re-render, and `submit` needs the current value
  // without taking it as a dependency.
  const abortRef = useRef<AbortController | null>(null);

  const t = STRINGS[uiLang];

  // Voice input -- browser-native, feature-detected. The mic stays hidden on
  // browsers without support rather than showing a button that would fail.
  const voice = useVoiceInput((transcript) => {
    setInput((prev) => (prev.trim() ? `${prev.trim()} ${transcript}` : transcript));
    requestAnimationFrame(() => inputRef.current?.focus());
  });

  useEffect(() => {
    try {
      localStorage.setItem(STYLE_KEY, style);
    } catch {
      /* same */
    }
  }, [style]);

  useEffect(() => {
    setMode(lockedMode);
  }, [lockedMode]);

  useEffect(() => {
    const j = searchParams.get("j");
    if (j === "india" || j === "international") setJurisdiction(j);
  }, [searchParams]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, loading]);

  // Prior questions travel with each request; the server resolves follow-ups
  // into standalone questions. Only answers carry conversational context —
  // a comparison is a self-contained lookup.
  const answerTurns = useMemo(() => turns.filter((tn) => tn.answer), [turns]);
  const last = answerTurns[answerTurns.length - 1]?.answer;
  const pendingClarification = last?.clarifying_question ?? null;

  const submit = useCallback(
    async (text: string, forceMode?: Mode, forceJurisdiction?: Jurisdiction) => {
      const typed = text.trim();
      if (!typed || loading) return;
      const activeMode = forceMode ?? mode;
      const activeJurisdiction = forceJurisdiction ?? jurisdiction;

      setInput("");
      setLoading(true);
      setError(null);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        if (activeMode === "compare") {
          const comparison = await compareCategories(typed, controller.signal, logConsent);
          setTurns((prev) => [...prev, { id: Date.now(), kind: "comparison", comparison }]);
        } else {
          const history = answerTurns.map(
            (tn) => tn.answer!.resolved_question ?? tn.answer!.question,
          );
          const answer = await askQuestion(
            typed, activeJurisdiction, history, controller.signal, logConsent, style,
          );
          rememberAnswer(answer);
          setTurns((prev) => [...prev, { id: Date.now(), kind: "answer", answer }]);
        }
      } catch (e) {
        // A cancel is something the user asked for, not a failure to report.
        if (e instanceof CancelledError) {
          setInput(typed);
        } else {
          setError(e instanceof Error ? e.message : "Something went wrong.");
          setInput(typed); // give their typing back rather than losing it
        }
      } finally {
        abortRef.current = null;
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [answerTurns, jurisdiction, loading, logConsent, mode, style],
  );

  useEffect(() => {
    const fromState = (location.state as { question?: string } | null)?.question;
    const q = searchParams.get("q") || fromState;
    if (!q || loading) return;
    const token = `boot:${lockedMode}:${q}`;
    try {
      if (sessionStorage.getItem(token)) return;
      sessionStorage.setItem(token, "1");
    } catch {
      /* a private window just means the question may repeat on reload */
    }
    const j = searchParams.get("j");
    void submit(q, lockedMode, j === "international" ? "international" : undefined);
  }, [searchParams, location.state, lockedMode, loading, submit]);

  function cancelRequest() {
    abortRef.current?.abort();
  }

  /**
   * Open a fresh consultation.
   *
   * This used to DELETE the transcript. Now the finished thread stays in the
   * list and a new one opens beside it, so nothing a user asked is thrown away
   * by the button they press to move on.
   */
  function newConsultation() {
    abortRef.current?.abort();
    startSession();
    setInput("");
    setError(null);
    setMode("ask");
    inputRef.current?.focus();
  }

  function switchSession(id: string) {
    if (id === activeId) return;
    abortRef.current?.abort();
    setInput("");
    setError(null);
    openSession(id);
  }

  /** Fetch suggestions for one turn, on demand. The ANSWER is posted back, not
   *  the question: this step must not retrieve, or it could introduce
   *  obligations the answer never established. */
  const requestNextSteps = useCallback(
    async (turn: Turn) => {
      if (nextSteps[turn.id] || stepsLoading === turn.id) return;
      setStepsLoading(turn.id);
      try {
        const payload = turn.jurisdictionComparison
          ? { comparison: turn.jurisdictionComparison }
          : turn.kind === "jurisdictions"
            ? { comparison: turn.jurisdictions }
            : { answer: turn.answer };
        const data = await fetchNextSteps(payload, style);
        setNextSteps((prev) => ({ ...prev, [turn.id]: data }));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not fetch suggestions.");
      } finally {
        setStepsLoading(null);
      }
    },
    [nextSteps, stepsLoading, style],
  );

  /** Reveal the OTHER jurisdiction for a turn already answered.
   *  A second generation, asked for explicitly — nobody pays for a side they
   *  did not want to see. */
  const revealOther = useCallback(
    async (turn: Turn) => {
      if (!turn.answer || turn.international || busySide === turn.id) return;
      setBusySide(turn.id);
      try {
        const asked = turn.answer.resolved_question ?? turn.answer.question;
        const other =
          turn.answer.jurisdiction === "international" ? "india" : "international";
        const otherAnswer = await askQuestion(
          asked, other, [], undefined, logConsent, style,
        );
        setTurns((prev) =>
          prev.map((tn) =>
            tn.id === turn.id ? { ...tn, international: otherAnswer } : tn,
          ),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not fetch the other jurisdiction.");
      } finally {
        setBusySide(null);
      }
    },
    [busySide, logConsent, setTurns, style],
  );

  /** Compare the two answers already on screen. Both are POSTed back, so this
   *  is one synthesis call and it describes exactly what the reader can see —
   *  not two freshly generated answers that might differ. */
  const compareSides = useCallback(
    async (turn: Turn) => {
      if (!turn.answer || !turn.international || busyCompare === turn.id) return;
      setBusyCompare(turn.id);
      try {
        const asked = turn.answer.resolved_question ?? turn.answer.question;
        const isPrimaryNational = turn.answer.jurisdiction !== "international";
        const comparison = await compareJurisdictions(asked, undefined, logConsent, {
          national: isPrimaryNational ? turn.answer : turn.international,
          international: isPrimaryNational ? turn.international : turn.answer,
        });
        setTurns((prev) =>
          prev.map((tn) =>
            tn.id === turn.id ? { ...tn, jurisdictionComparison: comparison } : tn,
          ),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not build the comparison.");
      } finally {
        setBusyCompare(null);
      }
    },
    [busyCompare, logConsent, setTurns],
  );

  function removeTurn(id: number) {
    setTurns((prev) => prev.filter((tn) => tn.id !== id));
  }

  // Whether the treaty corpus is actually loaded, straight from /health.
  const internationalChunks = health?.chunks_by_jurisdiction?.international ?? 0;
  const internationalReady = internationalChunks > 0;

  // If the corpus goes away between sessions (a rebuild, a fresh clone) a
  // jurisdiction of "international" could otherwise persist in component state
  // and send every question to an endpoint that will refuse it.
  useEffect(() => {
    if (healthChecked && !internationalReady && jurisdiction === "international") {
      setJurisdiction("india");
    }
  }, [healthChecked, internationalReady, jurisdiction]);

  const askPlaceholder = pendingClarification ? t.placeholderClarify : t.placeholderAsk;

  return (
    <div
      className="consult-page min-h-[calc(100vh-56px)]"
      data-rail={railHidden ? "hidden" : "shown"}
      style={{ ["--rail-w" as string]: `${railWidth}px` }}
    >
      {/* Outside <header> on purpose. The header carries backdrop-blur,
          and a backdrop-filter makes an element the containing block for
          its position:fixed descendants - which pinned the rail inside the
          header instead of down the side of the page. */}
      {menuOpen && (
        <div className="consult-scrim" onClick={() => setMenuOpen(false)} aria-hidden />
      )}
      {/* Always rendered. On a wide screen CSS makes this the standing
          rail; below that breakpoint `data-open` turns it back into the
          overlay the `⋯` button controls. One list, not two. */}
      {/* Shown only when the rail is away: without it there is no way back. */}
      <button
        type="button"
        onClick={() => setRailHidden(false)}
        className="rail-restore"
        aria-label={t.consultations}
        title={t.consultations}
      >
        <span aria-hidden>›</span>
      </button>

      {/* A sibling of the panel, not a child: the panel scrolls with
          overflow-x hidden, which clipped a grip hanging off its edge and left
          nothing to grab. Positioned against the same --rail-w. */}
      <div
        className="rail-grip"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize the panel"
        onMouseDown={(e) => {
          e.preventDefault();
          dragging.current = true;
          document.body.style.cursor = "col-resize";
          document.body.style.userSelect = "none";
        }}
        onDoubleClick={() => setRailWidth(272)}
      />

      <div className="consult-menu" data-open={menuOpen} aria-label={t.menu}>
        <div className="rail-head">
          <button
            type="button"
            onClick={() => setRailHidden(true)}
            className="rail-hide"
            aria-label={t.menu}
            title={t.menu}
          >
            <span aria-hidden>‹</span>
          </button>
        </div>

            <SessionList
              sessions={sessions}
              activeId={activeId}
              lang={uiLang}
              labels={{
                newConsultation: t.newConsultation,
                consultations: t.consultations,
                questionsCount: t.questionsCount,
                questionCount: t.questionCount,
                untitledSession: t.untitledSession,
                deleteSession: t.deleteSession,
                deleteAll: t.deleteAll,
                deleteAllConfirm: t.deleteAllConfirm,
                deleteAllYes: t.deleteAllYes,
                deleteAllNo: t.deleteAllNo,
              }}
              onNew={() => {
                newConsultation();
                setMenuOpen(false);
              }}
              onOpen={(id) => {
                switchSession(id);
                setMenuOpen(false);
              }}
              onRemove={removeSession}
              onClearAll={() => {
                clearSessions();
                setMenuOpen(false);
              }}
            />

            {/* Cream on the dark panel, matching SessionList above it -
                this menu deliberately keeps the old rail's ground. */}
            <div className="mt-3 border-t border-paper/10 pt-3">
              <p className="mb-1.5 text-[length:var(--t-micro)] font-medium text-paper">{t.sectionPrivacy}</p>
              <label className="flex cursor-pointer items-start gap-2 text-[length:var(--t-micro)] text-paper/75">
                <input
                  type="checkbox"
                  checked={logConsent}
                  onChange={(e) => setLogConsent(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 accent-haldi"
                />
                <span>{t.saveQuestion}</span>
              </label>
              <p className="mt-1 text-[length:var(--t-micro)] leading-relaxed text-paper/45">{t.saveQuestionHint}</p>
            </div>

        <p className="mt-3 border-t border-paper/10 pt-3 text-[length:var(--t-micro)] leading-relaxed text-paper/45">
          {t.disclaimer}
        </p>
      </div>
      {/* One column, no rail.
          The controls that lived in a permanent sidebar now sit where the
          decision is actually made - mode, jurisdiction and wording as pills
          directly above the composer - and the things set once per session
          (history, privacy) are behind the header menu. The interface language
          toggle is not reproduced here at all: Shell already owns it, and two
          copies of one preference is two sources of truth. */}
      {/* ==================== MAIN PANE ==================== */}
      <div className="ruled flex min-h-[calc(100vh-56px)] flex-col">
        <header className="consult-topbar sticky top-[56px] z-10 flex items-center justify-between gap-3 border-b border-rule bg-paper/95 px-6 py-3 backdrop-blur">
          {last && !last.abstained ? (
            <button
              type="button"
              onClick={() => printBriefing(last)}
              title={t.exportBriefingHint}
              className="rounded-[3px] border border-rule px-2.5 py-1 text-[length:var(--t-meta)] font-medium text-ink-faint transition-colors duration-150 hover:border-indigo-dye hover:bg-indigo-wash hover:text-indigo-dye focus-visible:focus-ring"
            >
              {t.exportBriefing}
            </button>
          ) : turns.length === 0 ? (
            /* The hero below already prints the tagline as its kicker; two
               copies a centimetre apart read as a rendering fault. */
            <span />
          ) : (
            <span className="eyebrow">{t.tagline}</span>
          )}

          <div className="relative flex items-center gap-3">
            {turns.length > 0 && (
              <>
                <span className="eyebrow hidden sm:inline">
                  {turns.length} {t.sessionCount}
                </span>
                {/* No longer destructive: the thread is filed in the rail and
                    a fresh one opens beside it. So it reads as "new", and it
                    drops the clay hover, which in this palette means a limit or
                    a refusal rather than an ordinary action. */}
                <button
                  onClick={newConsultation}
                  title="File this consultation and start a fresh one"
                  className="rounded-[3px] border border-rule px-2.5 py-1 text-[length:var(--t-meta)] font-medium text-ink-faint transition-colors duration-150 hover:border-haldi hover:bg-haldi-wash hover:text-haldi focus-visible:focus-ring"
                >
                  {t.newConsultation}
                </button>
              </>
            )}

            {/* Everything that used to be permanently open in the rail but is
                set once per session rather than per question. Kept behind one
                control so the page reads as a chat, not a settings form. */}
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-expanded={menuOpen}
              aria-haspopup="true"
              title={t.menu}
              className="consult-menu-btn"
            >
              <span aria-hidden>⋯</span>
            </button>

          </div>
        </header>

        <main className="mx-auto w-full max-w-sheet flex-1 px-6 py-8">
          {turns.length === 0 && !loading && (
            /* Back on paper, at the landing page's SCALE.
               Two dark treatments were tried here and both were rejected: one
               reproduced the home page's hero verbatim, the other cramped a
               dark ledger above the composer in small type. What was actually
               wanted was the home page's generosity - big, clear, plenty of
               air - not its ground and not its ornament. So this is the
               original paper empty state with the type scaled up and the
               spacing opened out. */
            <section className="mx-auto max-w-3xl pb-4 pt-0 text-center">
              {/* Leaf BESIDE the headline, the pair centred as one unit.
                  Stacked above it the leaf cost ~80px of vertical room, which
                  is the room the fourth card row needs - so both had to stay
                  small. Beside it the mark occupies width the centred headline
                  was not using, and that height comes back as size: the leaf
                  goes 74px -> 118px and the headline 2.55rem -> 3.05rem while
                  everything still clears the composer. */}
              {/* Side by side only where there is width for it. At 390px the
                  leaf leaves ~270px for the headline, which sets it in six
                  cramped lines - so below `sm` it stacks and the heading
                  centres, the way it did before the leaf moved. */}
              <div className="mx-auto flex max-w-4xl flex-col items-center justify-center gap-3 sm:flex-row sm:gap-9">
                <svg className="consult-leaf" viewBox="0 0 200 240" aria-hidden>
                  <ellipse cx="100" cy="128" rx="54" ry="78" fill="none" stroke="currentColor" strokeWidth="2.2" opacity="0.45" />
                  <path d="M100 28 C70 88 70 148 100 212 C130 148 130 88 100 28 Z" fill="currentColor" />
                  <path d="M100 28 V212" fill="none" stroke="#fdfaf2" strokeWidth="2" opacity="0.5" />
                </svg>
                <h2 className="max-w-[24ch] text-center font-display sm:max-w-[20ch] sm:text-left text-[length:var(--t-title)] font-normal leading-[1.12] tracking-[-0.018em] text-ink">
                  {t.emptyTitle}
                </h2>
              </div>
              <p className="mx-auto mt-3 max-w-[66ch] text-[length:var(--t-body)] leading-[1.65] text-ink-soft">
                {t.emptySubtitle}
              </p>

              <div className="mt-3 flex flex-wrap justify-center gap-2.5">
                {FEATURE_CHIPS.map((chip) => (
                  <span
                    key={chip.en}
                    className="inline-flex items-center gap-2 rounded-full border border-rule bg-white/60 px-3.5 py-1.5 text-[length:var(--t-micro)] text-ink-soft"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-neem" aria-hidden />
                    {uiLang === "hi" ? chip.hi : chip.en}
                  </span>
                ))}
              </div>

              <p className="eyebrow mt-4">{t.tryAsking}</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex.questionEn}
                    onClick={() => {
                      setMode(ex.mode);
                      submit(uiLang === "hi" ? ex.questionHi : ex.questionEn, ex.mode);
                    }}
                    className="card example-chip lift px-4 py-3.5 text-left hover:border-indigo-dye focus-visible:focus-ring"
                  >
                    <span className="eyebrow block text-haldi">
                      {uiLang === "hi" ? ex.labelHi : ex.labelEn}
                    </span>
                    <span className="mt-1.5 block text-[length:var(--t-meta)] leading-snug text-ink-soft">
                      {uiLang === "hi" ? ex.questionHi : ex.questionEn}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className="space-y-6">
            {turns.map((turn, i) =>
              turn.kind === "comparison" && turn.comparison ? (
                <div
                  key={turn.id}
                  className="msg-in border-t border-rule pt-5 first:border-t-0 first:pt-0"
                >
                  <div className="mb-3 flex justify-end">
                    <button
                      onClick={() => removeTurn(turn.id)}
                      className="eyebrow text-ink-faint hover:text-clay"
                      title="Remove"
                    >
                      ✕
                    </button>
                  </div>
                  <ComparisonView result={turn.comparison} />
                </div>
              ) : turn.kind === "jurisdictions" && turn.jurisdictions ? (
                <div key={turn.id} className="msg-in">
                  <JurisdictionCompareView
                    comparison={turn.jurisdictions}
                    labels={{
                      national: t.sideNational,
                      international: t.sideInternational,
                      comparison: t.compareJurisdictionsHint,
                      silent: t.sideSilent,
                      guard: t.comparisonGuard,
                      unavailable: t.comparisonUnavailable,
                    }}
                  />
                  <NextStepsPanel
                    data={nextSteps[turn.id] ?? null}
                    loading={stepsLoading === turn.id}
                    onRequest={() => requestNextSteps(turn)}
                    labels={{
                      title: t.nextStepsTitle,
                      ask: t.nextStepsAsk,
                      thinking: t.nextStepsThinking,
                      none: t.nextStepsNone,
                      guard: t.nextStepsGuard,
                      india: t.sideNational,
                      international: t.sideInternational,
                    }}
                  />
                </div>
              ) : turn.answer ? (
                <div key={turn.id} className="msg-in">
                  <AnswerView
                    answer={turn.answer}
                    defaultOpen={i === turns.length - 1}
                    onRemove={() => removeTurn(turn.id)}
                  />
                  {!turn.answer.abstained && internationalReady && (
                    <JurisdictionExpander
                      primary={
                        turn.answer.jurisdiction === "international"
                          ? "international"
                          : "national"
                      }
                      other={
                        turn.answer.jurisdiction === "international"
                          ? "national"
                          : "international"
                      }
                      otherAnswer={turn.international}
                      comparison={turn.jurisdictionComparison}
                      loadingOther={busySide === turn.id}
                      loadingComparison={busyCompare === turn.id}
                      onReveal={() => revealOther(turn)}
                      onCompare={() => compareSides(turn)}
                      labels={{
                        india: t.sideNational,
                        international: t.sideInternational,
                        reveal: t.revealOther,
                        revealing: t.revealingOther,
                        compare: t.compareBoth,
                        comparing: t.comparingBoth,
                        comparisonHeading: t.comparisonHeading,
                        silent: t.sideSilent,
                        guard: t.comparisonGuard,
                        unavailable: t.comparisonUnavailable,
                      }}
                    />
                  )}
                  {!turn.answer.abstained && (
                    <NextStepsPanel
                      data={nextSteps[turn.id] ?? null}
                      loading={stepsLoading === turn.id}
                      onRequest={() => requestNextSteps(turn)}
                      labels={{
                        title: t.nextStepsTitle,
                        ask: t.nextStepsAsk,
                        thinking: t.nextStepsThinking,
                        none: t.nextStepsNone,
                        guard: t.nextStepsGuard,
                        india: t.sideNational,
                        international: t.sideInternational,
                      }}
                    />
                  )}
                </div>
              ) : null,
            )}
          </div>

          {loading && (
            <section className="mt-8 max-w-3xl border-t border-rule pt-6">
              {/* The skeleton is the shape of the answer that is coming: four
                  stations on the same rule, pulsing down the trail in order. A
                  generic spinner would tell the user nothing; this previews the
                  structure and makes a 15-second wait legible. */}
              <ol className="space-y-5">
                {[0, 1, 2, 3].map((i) => (
                  <li
                    key={i}
                    className="trail-line trail-sweep relative pl-11"
                    style={{ "--i": i } as React.CSSProperties}
                  >
                    <span className="absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-full border border-rule bg-paper text-[length:var(--t-meta)] font-semibold text-ink-faint/50">
                      {i + 1}
                    </span>
                    <div className="h-2.5 w-24 rounded-[2px] bg-paper-deep" />
                    <div className="mt-2.5 h-2.5 w-full rounded-[2px] bg-paper-deep" />
                    <div className="mt-1.5 h-2.5 w-4/5 rounded-[2px] bg-paper-deep" />
                  </li>
                ))}
              </ol>
              <div className="mt-6 flex items-center justify-between gap-4">
                <p className="eyebrow">
                  {mode === "compare"
                    ? t.comparingStage
                    : t.classifyingStage}
                </p>
                <button
                  type="button"
                  onClick={cancelRequest}
                  className="shrink-0 rounded-[3px] border border-rule px-2.5 py-1 text-[length:var(--t-micro)] text-ink-soft transition-colors duration-150 hover:border-clay/60 hover:bg-clay-wash hover:text-clay focus-visible:focus-ring"
                >
                  {t.stop}
                </button>
              </div>
            </section>
          )}

          {error && (
            <div className="card mt-8 max-w-3xl border-clay/40 bg-clay-wash p-4">
              <p className="eyebrow text-clay">{t.couldNotComplete}</p>
              <p className="mt-1 text-[length:var(--t-meta)] text-ink">{error}</p>
              <button onClick={() => setError(null)} className="eyebrow mt-2 text-clay hover:underline">
                {t.dismiss}
              </button>
            </div>
          )}

          <div ref={bottomRef} />
        </main>

        {/* ---------------- Composer ---------------- */}
        <div className="consult-composer sticky bottom-0 border-t border-rule bg-paper/95 backdrop-blur">
          <div className="mx-auto max-w-sheet px-6 py-3">
            {pendingClarification && mode === "ask" && (
              <div className="mb-2 flex items-start gap-2 border-l-2 border-haldi bg-haldi-wash px-3 py-1.5">
                <span className="eyebrow shrink-0 text-haldi">{t.replyingTo}</span>
                <p className="text-[length:var(--t-micro)] leading-snug text-ink-soft">{pendingClarification}</p>
              </div>
            )}

            {/* The three decisions that change what comes back, sitting where
                they are made rather than in a sidebar you stop looking at.
                Jurisdiction appears only in ask mode, because a category
                comparison is an Indian-law view by construction. */}
            <div className="consult-pills">
              <PillGroup
                label={t.sectionMode}
                value={mode}
                options={[
                  { value: "ask", label: t.modeAsk },
                  { value: "compare", label: t.modeCompare },
                ]}
                onChange={(v) => {
                  setError(null);
                  setMode(v as typeof mode);
                }}
              />
              {mode === "ask" && (
                <PillGroup
                  label={t.sectionJurisdiction}
                  value={jurisdiction}
                  options={[
                    { value: "india", label: t.jurisdictionIndia },
                    {
                      value: "international",
                      label: t.jurisdictionIntl,
                      disabled: !internationalReady,
                    },
                  ]}
                  onChange={(v) => {
                    if (v === "international" && !internationalReady) {
                      setError(t.jurisdictionIntlUnavailable);
                      return;
                    }
                    setError(null);
                    setJurisdiction(v as typeof jurisdiction);
                  }}
                />
              )}
              <PillGroup
                label={t.sectionStyle}
                value={style}
                options={[
                  { value: "legal", label: t.styleLegal },
                  { value: "plain", label: t.stylePlain },
                ]}
                onChange={(v) => setStyle(v as typeof style)}
              />
            </div>

            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="eyebrow normal-case tracking-normal">{t.infoNotAdvice}</span>
              <span className="eyebrow hidden normal-case tracking-normal text-ink-faint sm:inline">
                {mode === "compare" ? t.hintCompare : t.hintEnter}
              </span>
            </div>

            <div className="card flex items-end gap-1.5 p-1.5">
              <textarea
                id="q"
                ref={inputRef}
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit(input);
                  }
                }}
                placeholder={mode === "compare" ? t.placeholderCompare : askPlaceholder}
                className="min-h-[2.75rem] w-full resize-none bg-transparent px-3 py-2 font-serif text-[length:var(--t-body)] leading-relaxed text-ink placeholder:text-ink-faint/70 focus:outline-none"
              />

              {voice.supported && (
                <>
                  <button
                    type="button"
                    onClick={voice.toggleListening}
                    title={t.micTooltip}
                    aria-label={t.micTooltip}
                    className={`mic-btn flex h-10 w-10 shrink-0 items-center justify-center rounded-[3px] border border-rule text-ink-faint hover:bg-paper-deep hover:text-ink ${
                      voice.listening ? "mic-btn--active" : ""
                    }`}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className="h-[19px] w-[19px]">
                      <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" />
                      <path d="M19 11a7 7 0 0 1-14 0M12 19v3" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={voice.toggleLang}
                    title={t.micLangTooltip}
                    aria-label={t.micLangTooltip}
                    className="mic-btn flex h-10 shrink-0 items-center justify-center rounded-[3px] border border-rule px-2 text-[length:var(--t-micro)] font-semibold tracking-wide text-ink-faint hover:bg-paper-deep hover:text-ink"
                  >
                    {voice.lang === "hi-IN" ? "हिं" : "EN"}
                  </button>
                </>
              )}

              <button
                onClick={() => submit(input)}
                disabled={loading || !input.trim()}
                className="send-btn shrink-0 rounded-[3px] bg-ink px-4 py-2.5 text-[length:var(--t-meta)] font-medium text-paper transition-all duration-150 hover:bg-ink-soft focus-visible:focus-ring disabled:opacity-35 disabled:hover:bg-ink"
              >
                {loading ? t.sendLoading : mode === "compare" ? t.sendCompare : t.sendAsk}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


/** One labelled segmented control.
 *
 * A shared component rather than three hand-rolled button rows: the rail's
 * three groups had drifted into three slightly different markups, and the
 * jurisdiction one carried a disabled state the others had to reimplement.
 */
function PillGroup({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string; disabled?: boolean }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="consult-pill-group">
      <span className="consult-pill-label">{label}</span>
      <div className="consult-pill-track" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            aria-disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={`consult-pill ${value === o.value ? "is-on" : ""} ${
              o.disabled ? "is-off" : ""
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
