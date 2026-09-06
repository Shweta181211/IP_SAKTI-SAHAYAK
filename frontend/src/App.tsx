import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CancelledError,
  askQuestion,
  compareCategories,
  fetchHealth,
} from "./api";
import { AnswerView } from "./components/AnswerView";
import { ComparisonView } from "./components/ComparisonView";
import { useVoiceInput } from "./useVoiceInput";
import { SessionList } from "./components/SessionList";
import { useSessions } from "./useSessions";
import { EXAMPLES, FEATURE_CHIPS, STRINGS, type UiLang } from "./i18n";
import type { Health } from "./types";

type Jurisdiction = "india" | "international";
type Mode = "ask" | "compare";

// `Turn` and transcript persistence now live in useSessions.ts, which keeps one
// transcript per named consultation rather than a single anonymous blob that
// "End session" destroyed.
const CONSENT_KEY = "ipsakti.logconsent.v1";
const UI_LANG_KEY = "ipsakti.uilang.v1";

export default function App() {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("ask");
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("india");
  const [uiLang, setUiLang] = useState<UiLang>(() => {
    try {
      return (localStorage.getItem(UI_LANG_KEY) as UiLang) || "en";
    } catch {
      return "en";
    }
  });
  const [railOpen, setRailOpen] = useState(false);
  // Consent to retain the QUESTION TEXT in the server's audit log. Off by
  // default and remembered per browser: the operational record that makes the
  // system auditable holds no user content either way, so this is a genuine
  // choice rather than a formality. See backend/app/audit.py.
  const [logConsent, setLogConsent] = useState<boolean>(() => {
    try {
      return localStorage.getItem(CONSENT_KEY) === "true";
    } catch {
      return false;
    }
  });
  const {
    sessions,
    activeId,
    turns,
    setTurns,
    startSession,
    openSession,
    removeSession,
  } = useSessions();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthChecked, setHealthChecked] = useState(false);
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
    fetchHealth().then((h) => {
      setHealth(h);
      setHealthChecked(true);
    });
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(CONSENT_KEY, String(logConsent));
    } catch {
      /* a remembered preference is a convenience, never a requirement */
    }
  }, [logConsent]);

  useEffect(() => {
    try {
      localStorage.setItem(UI_LANG_KEY, uiLang);
    } catch {
      /* same */
    }
  }, [uiLang]);

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
    async (text: string, forceMode?: Mode) => {
      const typed = text.trim();
      if (!typed || loading) return;
      const activeMode = forceMode ?? mode;

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
            typed, jurisdiction, history, controller.signal, logConsent,
          );
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
    [answerTurns, jurisdiction, loading, logConsent, mode],
  );

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

  function removeTurn(id: number) {
    setTurns((prev) => prev.filter((tn) => tn.id !== id));
  }

  const askPlaceholder = pendingClarification ? t.placeholderClarify : t.placeholderAsk;
  const statusReady = healthChecked && !!health;
  const statusError = healthChecked && !health;

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[300px_1fr]">
      {/* ==================== LEFT RAIL ==================== */}
      <aside className="rail flex flex-col text-paper/90 lg:sticky lg:top-0 lg:h-screen lg:overflow-y-auto">
        <div className="flex items-center justify-between px-6 pt-6 lg:hidden">
          <span className="font-serif text-[16px] font-semibold text-paper">
            IP-SAKTI <span className="text-haldi">Sahayak</span>
          </span>
          <button
            onClick={() => setRailOpen((v) => !v)}
            className="rounded-[3px] border border-paper/20 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-paper/80"
          >
            {t.menu} {railOpen ? "▴" : "▾"}
          </button>
        </div>

        <div className={`${railOpen ? "block" : "hidden"} px-6 pb-6 pt-6 lg:block lg:pt-7`}>
          {/* ---- brand ---- */}
          <div className="mb-7 hidden lg:block">
            <svg className="brand-motif mb-2.5 h-8 w-28" viewBox="0 0 120 40" aria-hidden="true">
              <path
                className="motif-path"
                d="M2 34 C 20 10, 40 10, 58 22 C 76 34, 96 34, 118 8"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
              />
              <path className="motif-leaf" d="M20 24 C 24 16, 30 14, 34 18 C 30 22, 24 24, 20 24 Z" fill="currentColor" />
              <path className="motif-leaf" d="M64 26 C 68 18, 74 16, 78 20 C 74 24, 68 26, 64 26 Z" fill="currentColor" />
              <path className="motif-leaf" d="M92 18 C 96 10, 102 8, 106 12 C 102 16, 96 18, 92 18 Z" fill="currentColor" />
            </svg>
            <h1 className="font-serif text-[21px] font-medium leading-tight text-paper">
              IP-SAKTI<br />Sahayak
            </h1>
            <p className="mt-2 max-w-[26ch] text-[12.5px] leading-relaxed text-paper/55">
              {t.tagline}
            </p>
          </div>

          {/* ---- consultations ---- */}
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
            }}
            onNew={newConsultation}
            onOpen={switchSession}
            onRemove={removeSession}
          />

          {/* ---- 1. mode ---- */}
          <div className="border-t border-paper/10 py-4">
            <div className="mb-2 flex items-baseline gap-2 text-[13px] font-medium text-paper">
              <span className="font-serif text-haldi">1</span>
              <span>{t.sectionMode}</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {([
                ["ask", t.modeAsk],
                ["compare", t.modeCompare],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={mode === value}
                  onClick={() => setMode(value)}
                  className="rail-card rounded-[3px] border border-paper/15 bg-white/[0.04] px-2.5 py-3 text-left text-[12px] leading-snug text-paper/65"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* ---- 2. jurisdiction (ask mode only) ---- */}
          {mode === "ask" && (
            <div className="border-t border-paper/10 py-4">
              <div className="mb-2 flex items-baseline gap-2 text-[13px] font-medium text-paper">
                <span className="font-serif text-haldi">2</span>
                <span>{t.sectionJurisdiction}</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {(["india", "international"] as const).map((j) => {
                  const unavailable = j === "international";
                  const selected = jurisdiction === j;
                  return (
                    <button
                      key={j}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      aria-disabled={unavailable}
                      title={unavailable ? t.jurisdictionIntlNote : t.jurisdictionIndiaNote}
                      onClick={() => {
                        if (!unavailable) setJurisdiction(j);
                      }}
                      className={`rail-card rounded-[3px] border px-2.5 py-3 text-left text-[12px] leading-snug ${
                        unavailable
                          ? "cursor-not-allowed border-paper/10 text-paper/30"
                          : "border-paper/15 bg-white/[0.04] text-paper/65"
                      }`}
                      style={
                        unavailable
                          ? {
                              backgroundImage:
                                "repeating-linear-gradient(135deg, transparent 0 5px, rgba(245,238,221,0.06) 5px 6px)",
                            }
                          : undefined
                      }
                    >
                      {j === "india" ? t.jurisdictionIndia : t.jurisdictionIntl}
                    </button>
                  );
                })}
              </div>
              {jurisdiction === "international" && (
                <p className="mt-2 text-[11px] leading-relaxed text-paper/45">
                  {t.jurisdictionIntlNote}
                </p>
              )}
            </div>
          )}

          {/* ---- privacy ---- */}
          <div className="border-t border-paper/10 py-4">
            <p className="mb-2 text-[13px] font-medium text-paper">{t.sectionPrivacy}</p>
            <label className="flex cursor-pointer items-start gap-2 text-[13px] text-paper/75">
              <input
                type="checkbox"
                checked={logConsent}
                onChange={(e) => setLogConsent(e.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 accent-haldi"
              />
              <span>{t.saveQuestion}</span>
            </label>
            <p className="mt-1.5 text-[11px] leading-relaxed text-paper/45">{t.saveQuestionHint}</p>
          </div>

          {/* ---- interface language ---- */}
          <div className="border-t border-paper/10 py-4">
            <p className="mb-2 text-[13px] font-medium text-paper">{t.sectionLang}</p>
            <div role="radiogroup" aria-label={t.sectionLang} className="flex overflow-hidden rounded-[3px] border border-paper/20">
              {([
                ["en", "English"],
                ["hi", "हिंदी"],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={uiLang === value}
                  onClick={() => setUiLang(value)}
                  className={`flex-1 px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                    uiLang === value ? "bg-haldi text-ink" : "bg-transparent text-paper/60 hover:text-paper"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {voice.supported && (
              <p className="mt-1.5 text-[11px] leading-relaxed text-paper/45">
                🎙 {t.micTooltip}: EN / हिंदी — {t.micLangTooltip.toLowerCase()}.
              </p>
            )}
          </div>

          {/* ---- footer ---- */}
          <div className="mt-auto border-t border-paper/10 pt-4">
            <span className="mb-3 inline-block rounded-[2px] border border-paper/20 px-2.5 py-1 text-[11px] tracking-wide text-neem-wash/80">
              {t.jurisdictionBadge}
            </span>
            <p className="text-[11px] leading-relaxed text-paper/45">{t.disclaimer}</p>
          </div>
        </div>
      </aside>

      {/* ==================== MAIN PANE ==================== */}
      <div className="flex min-h-screen flex-col bg-paper">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-rule bg-paper/95 px-6 py-3 backdrop-blur">
          <span className="flex items-center gap-1.5" title={statusReady ? "Backend connected" : "Backend unreachable"}>
            <span
              className={`h-1.5 w-1.5 rounded-full status-dot ${
                statusReady ? "bg-neem" : statusError ? "bg-clay status-dot--pending" : "bg-haldi status-dot--pending"
              }`}
              aria-hidden
            />
            <span className="eyebrow">
              {statusReady
                ? `${health!.chunks_in_vector_db.toLocaleString()} ${t.statusOnline}`
                : statusError
                  ? t.statusOffline
                  : t.statusConnecting}
            </span>
          </span>

          <div className="flex items-center gap-3">
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
                  className="rounded-[3px] border border-rule px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-faint transition-colors duration-150 hover:border-haldi hover:bg-haldi-wash hover:text-haldi focus-visible:focus-ring"
                >
                  {t.newConsultation}
                </button>
              </>
            )}
          </div>
        </header>

        <main className="mx-auto w-full max-w-sheet flex-1 px-6 py-8">
          {turns.length === 0 && !loading && (
            <section className="mx-auto max-w-2xl pt-6 text-center">
              <h2 className="font-serif text-[23px] leading-snug text-ink">{t.emptyTitle}</h2>
              <p className="mt-2.5 text-[13.5px] leading-relaxed text-ink-soft">{t.emptySubtitle}</p>

              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {FEATURE_CHIPS.map((chip) => (
                  <span
                    key={chip.en}
                    className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-white/60 px-3 py-1 text-[11.5px] text-ink-soft"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-neem" aria-hidden />
                    {uiLang === "hi" ? chip.hi : chip.en}
                  </span>
                ))}
              </div>

              <p className="eyebrow mt-6">{t.tryAsking}</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex.questionEn}
                    onClick={() => {
                      setMode(ex.mode);
                      submit(uiLang === "hi" ? ex.questionHi : ex.questionEn, ex.mode);
                    }}
                    className="card example-chip lift px-3 py-2.5 text-left hover:border-indigo-dye focus-visible:focus-ring"
                  >
                    <span className="eyebrow block text-haldi">
                      {uiLang === "hi" ? ex.labelHi : ex.labelEn}
                    </span>
                    <span className="mt-1 block text-[12.5px] leading-snug text-ink-soft">
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
              ) : turn.answer ? (
                <div key={turn.id} className="msg-in">
                  <AnswerView
                    answer={turn.answer}
                    defaultOpen={i === turns.length - 1}
                    onRemove={() => removeTurn(turn.id)}
                  />
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
                    <span className="absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-full border border-rule bg-paper text-[13px] font-semibold text-ink-faint/50">
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
                  {mode === "compare" ? t.comparingStage : t.classifyingStage}
                </p>
                <button
                  type="button"
                  onClick={cancelRequest}
                  className="shrink-0 rounded-[3px] border border-rule px-2.5 py-1 text-[12px] text-ink-soft transition-colors duration-150 hover:border-clay/60 hover:bg-clay-wash hover:text-clay focus-visible:focus-ring"
                >
                  {t.stop}
                </button>
              </div>
            </section>
          )}

          {error && (
            <div className="card mt-8 max-w-3xl border-clay/40 bg-clay-wash p-4">
              <p className="eyebrow text-clay">{t.couldNotComplete}</p>
              <p className="mt-1 text-[14px] text-ink">{error}</p>
              <button onClick={() => setError(null)} className="eyebrow mt-2 text-clay hover:underline">
                {t.dismiss}
              </button>
            </div>
          )}

          <div ref={bottomRef} />
        </main>

        {/* ---------------- Composer ---------------- */}
        <div className="sticky bottom-0 border-t border-rule bg-paper/95 backdrop-blur">
          <div className="mx-auto max-w-sheet px-6 py-3">
            {pendingClarification && mode === "ask" && (
              <div className="mb-2 flex items-start gap-2 border-l-2 border-haldi bg-haldi-wash px-3 py-1.5">
                <span className="eyebrow shrink-0 text-haldi">{t.replyingTo}</span>
                <p className="text-[12.5px] leading-snug text-ink-soft">{pendingClarification}</p>
              </div>
            )}

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
                className="min-h-[2.75rem] w-full resize-none bg-transparent px-3 py-2 font-serif text-[15px] leading-relaxed text-ink placeholder:text-ink-faint/70 focus:outline-none"
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
                    className="mic-btn flex h-10 shrink-0 items-center justify-center rounded-[3px] border border-rule px-2 text-[11.5px] font-semibold tracking-wide text-ink-faint hover:bg-paper-deep hover:text-ink"
                  >
                    {voice.lang === "hi-IN" ? "हिं" : "EN"}
                  </button>
                </>
              )}

              <button
                onClick={() => submit(input)}
                disabled={loading || !input.trim()}
                className="send-btn shrink-0 rounded-[3px] bg-ink px-4 py-2.5 text-[13px] font-medium text-paper transition-all duration-150 hover:bg-ink-soft focus-visible:focus-ring disabled:opacity-35 disabled:hover:bg-ink"
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
