import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { askQuestion, compareCategories, fetchHealth } from "./api";
import { AnswerView } from "./components/AnswerView";
import { ComparisonView } from "./components/ComparisonView";
import type { Answer, ComparisonResult, Health } from "./types";

type Jurisdiction = "india" | "international";
type Mode = "ask" | "compare";

/** One exchange in the transcript. Either an answer or a comparison. */
interface Turn {
  id: number;
  kind: "answer" | "comparison";
  answer?: Answer;
  comparison?: ComparisonResult;
}

const EXAMPLES: { label: string; question: string; mode: Mode }[] = [
  { label: "The flagship", mode: "ask",
    question: "Can a classical churna from a First Schedule text be patented?" },
  { label: "Registration process", mode: "ask",
    question: "How do I register a Geographical Indication for an Ayurvedic product?" },
  { label: "Biodiversity / ABS", mode: "ask",
    question: "What is Access and Benefit Sharing and when do I need NBA approval?" },
  { label: "Compare categories", mode: "compare",
    question: "An ashwagandha churna made to a First Schedule formula, but standardised for withanolide content" },
];

const STORAGE_KEY = "ipsakti.turns.v2";
const MAX_STORED = 20;

export default function App() {
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<Mode>("ask");
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("india");
  const [turns, setTurns] = useState<Turn[]>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as Turn[]) : [];
    } catch {
      return [];
    }
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetchHealth().then(setHealth);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(turns.slice(-MAX_STORED)));
    } catch {
      /* history is a convenience, never a requirement */
    }
  }, [turns]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, loading]);

  // Prior questions travel with each request; the server resolves follow-ups
  // into standalone questions. Only answers carry conversational context —
  // a comparison is a self-contained lookup.
  const answerTurns = useMemo(() => turns.filter((t) => t.answer), [turns]);
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
      try {
        if (activeMode === "compare") {
          const comparison = await compareCategories(typed);
          setTurns((prev) => [...prev, { id: Date.now(), kind: "comparison", comparison }]);
        } else {
          const history = answerTurns.map(
            (t) => t.answer!.resolved_question ?? t.answer!.question,
          );
          const answer = await askQuestion(typed, jurisdiction, history);
          setTurns((prev) => [...prev, { id: Date.now(), kind: "answer", answer }]);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
        setInput(typed); // give their typing back rather than losing it
      } finally {
        setLoading(false);
        inputRef.current?.focus();
      }
    },
    [answerTurns, jurisdiction, loading, mode],
  );

  function endSession() {
    setTurns([]);
    setInput("");
    setError(null);
    setMode("ask");
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    inputRef.current?.focus();
  }

  function removeTurn(id: number) {
    setTurns((prev) => prev.filter((t) => t.id !== id));
  }

  const askPlaceholder = pendingClarification
    ? "Type your answer…"
    : "e.g. Can a classical churna from a First Schedule text be patented?";

  return (
    <div className="flex min-h-screen flex-col">
      {/* ---------------- Masthead ---------------- */}
      <header className="sticky top-0 z-20 border-b border-rule bg-paper-deep/95 backdrop-blur">
        <div className="mx-auto flex max-w-sheet items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-baseline gap-3">
            <h1 className="font-serif text-[19px] font-semibold tracking-tight text-ink">
              IP-SAKTI <span className="text-haldi">Sahayak</span>
            </h1>
            <p className="hidden text-[12.5px] text-ink-faint md:block">
              Source-cited IP &amp; regulatory guidance for Ayurveda
            </p>
          </div>

          <div className="flex items-center gap-3">
            {turns.length > 0 && (
              <>
                <span className="eyebrow hidden sm:inline">
                  {turns.length} in this session
                </span>
                <button
                  onClick={endSession}
                  title="Clear the transcript and start a fresh consultation"
                  className="rounded-[3px] border border-rule px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-faint transition-colors hover:border-clay hover:text-clay"
                >
                  End session
                </button>
              </>
            )}
            <span className="flex items-center gap-1.5" title={health ? "Backend connected" : "Backend unreachable"}>
              <span
                className={`h-1.5 w-1.5 rounded-full ${health ? "bg-neem" : "bg-clay"}`}
                aria-hidden
              />
              <span className="eyebrow hidden sm:inline">
                {health
                  ? `${health.chunks_in_vector_db.toLocaleString()} provisions`
                  : "offline"}
              </span>
            </span>
          </div>
        </div>
      </header>

      {/* ---------------- Transcript ---------------- */}
      <main className="mx-auto w-full max-w-sheet flex-1 px-6 py-8">
        {turns.length === 0 && !loading && (
          <section className="mx-auto max-w-2xl pt-8 text-center">
            <h2 className="font-serif text-[23px] leading-snug text-ink">
              Ask about protecting or commercialising an Ayurvedic product.
            </h2>
            <p className="mt-2.5 text-[13.5px] leading-relaxed text-ink-soft">
              Every answer is built only from cited Indian statutes, rules and registry
              records — and shows how well-supported it is. When the corpus cannot answer,
              it says so rather than guessing.
            </p>
            <div className="mt-6 grid gap-2 sm:grid-cols-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.question}
                  onClick={() => {
                    setMode(ex.mode);
                    submit(ex.question, ex.mode);
                  }}
                  className="card px-3 py-2.5 text-left transition-colors hover:border-indigo-dye"
                >
                  <span className="eyebrow block text-haldi">{ex.label}</span>
                  <span className="mt-1 block text-[12.5px] leading-snug text-ink-soft">
                    {ex.question}
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
                className="border-t border-rule pt-5 first:border-t-0 first:pt-0"
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
              <AnswerView
                key={turn.id}
                answer={turn.answer}
                defaultOpen={i === turns.length - 1}
                onRemove={() => removeTurn(turn.id)}
              />
            ) : null,
          )}
        </div>

        {loading && (
          <section className="mt-8 max-w-3xl border-t border-rule pt-6">
            <div className="space-y-5">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="relative pl-11">
                  <span className="absolute left-0 top-0 h-8 w-8 animate-pulse rounded-full border border-rule bg-paper-deep" />
                  <div className="h-2.5 w-24 animate-pulse rounded bg-paper-deep" />
                  <div className="mt-2 h-2.5 w-full animate-pulse rounded bg-paper-deep" />
                  <div className="mt-1.5 h-2.5 w-4/5 animate-pulse rounded bg-paper-deep" />
                </div>
              ))}
            </div>
            <p className="eyebrow mt-6">
              {mode === "compare"
                ? "Retrieving provisions, contrasting each category…"
                : "Classifying, retrieving provisions, verifying citations…"}
            </p>
          </section>
        )}

        {error && (
          <div className="card mt-8 max-w-3xl border-clay/40 bg-clay-wash p-4">
            <p className="eyebrow text-clay">Could not complete</p>
            <p className="mt-1 text-[14px] text-ink">{error}</p>
            <button
              onClick={() => setError(null)}
              className="eyebrow mt-2 text-clay hover:underline"
            >
              Dismiss
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
              <span className="eyebrow shrink-0 text-haldi">Replying to</span>
              <p className="text-[12.5px] leading-snug text-ink-soft">{pendingClarification}</p>
            </div>
          )}

          {/* Mode switch — two genuinely different questions to ask. */}
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <div role="radiogroup" aria-label="Mode" className="flex overflow-hidden rounded-[3px] border border-rule">
              {([
                ["ask", "Ask a question"],
                ["compare", "Compare categories"],
              ] as const).map(([value, label]) => (
                <button
                  key={value}
                  role="radio"
                  aria-checked={mode === value}
                  onClick={() => setMode(value)}
                  className={`px-3 py-1 text-[12px] font-medium transition-colors ${
                    mode === value
                      ? "bg-ink text-paper"
                      : "bg-paper text-ink-faint hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {mode === "ask" && (
              <div role="radiogroup" aria-label="Jurisdiction" className="flex overflow-hidden rounded-[3px] border border-rule">
                {(["india", "international"] as const).map((j) => (
                  <button
                    key={j}
                    role="radio"
                    aria-checked={jurisdiction === j}
                    onClick={() => setJurisdiction(j)}
                    className={`px-2.5 py-1 text-[11.5px] font-medium transition-colors ${
                      jurisdiction === j
                        ? "bg-indigo-dye text-paper"
                        : "bg-paper text-ink-faint hover:text-ink"
                    }`}
                  >
                    {j === "india" ? "India" : "International"}
                  </button>
                ))}
              </div>
            )}

            <span className="eyebrow ml-auto hidden normal-case tracking-normal text-ink-faint sm:inline">
              {mode === "compare"
                ? "Describe a product — see how each category treats it"
                : "Enter to ask · Shift + Enter for a new line"}
            </span>
          </div>

          <div className="card p-1.5">
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
              placeholder={
                mode === "compare"
                  ? "e.g. A herbal syrup using classical ingredients but my own ratios"
                  : askPlaceholder
              }
              className="min-h-[2.75rem] w-full resize-none bg-transparent px-3 py-2 font-serif text-[15px] leading-relaxed text-ink placeholder:text-ink-faint/70 focus:outline-none"
            />
            <div className="flex items-center justify-between gap-3 border-t border-rule px-3 py-1.5">
              <span className="eyebrow normal-case tracking-normal">
                Information, not legal advice
              </span>
              <button
                onClick={() => submit(input)}
                disabled={loading || !input.trim()}
                className="rounded-[3px] bg-ink px-4 py-1.5 text-[13px] font-medium text-paper transition-opacity disabled:opacity-35"
              >
                {loading ? "Consulting…" : mode === "compare" ? "Compare" : "Ask"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
