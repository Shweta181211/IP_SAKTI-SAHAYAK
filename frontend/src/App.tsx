import { useEffect, useRef, useState } from "react";
import { askQuestion, fetchHealth } from "./api";
import { AnswerView } from "./components/AnswerView";
import type { Answer, Health } from "./types";

type Jurisdiction = "india" | "international";

/** One exchange. `asked` is what the user typed; the Answer carries the full
 *  question actually sent, which may include carried-over context. */
interface Turn {
  id: number;
  asked: string;
  answer: Answer;
}

const EXAMPLES = [
  "Can a classical churna from a First Schedule text be patented?",
  "How do I register a Geographical Indication for an Ayurvedic product?",
  "What is Access and Benefit Sharing and when do I need NBA approval?",
  "Can I advertise that my ayurvedic product cures diabetes?",
];

const STORAGE_KEY = "ipsakti.turns.v1";

export default function App() {
  const [input, setInput] = useState("");
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("india");
  const [turns, setTurns] = useState<Turn[]>(() => {
    // History survives a refresh. Wrapped because private windows and blocked
    // site data make storage access throw rather than return null.
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
      localStorage.setItem(STORAGE_KEY, JSON.stringify(turns.slice(-20)));
    } catch {
      /* history is a convenience, never a requirement */
    }
  }, [turns]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, loading]);

  // The backend is stateless by design, so the transcript lives here and prior
  // questions travel with each request. The server resolves follow-ups into
  // standalone questions; we do not concatenate strings ourselves, because that
  // cannot tell a genuine follow-up from a change of subject.
  const last = turns[turns.length - 1];
  const pendingClarification = last?.answer.clarifying_question ?? null;

  async function submit(text: string) {
    const typed = text.trim();
    if (!typed || loading) return;

    // Prior questions, oldest first. Includes the resolved form where one
    // exists, so a chain of follow-ups does not lose the subject.
    const history = turns.map((t) => t.answer.resolved_question ?? t.answer.question);

    setInput("");           // clear immediately, so the box is ready for the reply
    setLoading(true);
    setError(null);
    try {
      const answer = await askQuestion(typed, jurisdiction, history);
      setTurns((prev) => [...prev, { id: Date.now(), asked: typed, answer }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setInput(typed);      // give the text back rather than losing their typing
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function removeTurn(id: number) {
    setTurns((prev) => prev.filter((t) => t.id !== id));
  }

  function reset() {
    setTurns([]);
    setInput("");
    setError(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    inputRef.current?.focus();
  }

  return (
    <div className="flex min-h-screen flex-col">
      {/* ---------- Masthead ---------- */}
      <header className="sticky top-0 z-20 border-b border-rule bg-paper-deep/95 backdrop-blur">
        <div className="mx-auto flex max-w-sheet items-baseline justify-between gap-4 px-6 py-3.5">
          <div className="flex items-baseline gap-3">
            <h1 className="font-serif text-[19px] font-semibold tracking-tight text-ink">
              IP-SAKTI <span className="text-haldi">Sahayak</span>
            </h1>
            <p className="hidden text-[12.5px] text-ink-faint sm:block">
              Source-cited IP &amp; regulatory guidance for Ayurveda
            </p>
          </div>

          <div className="flex items-center gap-4">
            {turns.length > 0 && (
              <button
                onClick={reset}
                className="rounded-[3px] border border-rule px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-faint transition-colors hover:border-clay hover:text-clay"
              >
                Clear {turns.length}
              </button>
            )}
            <div className="flex items-center gap-2">
              <span
                className={`h-1.5 w-1.5 rounded-full ${health ? "bg-neem" : "bg-clay"}`}
                aria-hidden
              />
              <span className="eyebrow">
                {health
                  ? `${health.chunks_in_vector_db.toLocaleString()} provisions indexed`
                  : "backend offline"}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* ---------- Transcript ---------- */}
      <main className="mx-auto w-full max-w-sheet flex-1 px-6 py-8">
        {turns.length === 0 && !loading && (
          <section className="mx-auto max-w-2xl pt-10 text-center">
            <h2 className="font-serif text-[22px] leading-snug text-ink">
              Ask about protecting or commercialising an Ayurvedic product.
            </h2>
            <p className="mt-2 text-[13.5px] leading-relaxed text-ink-soft">
              Every answer is built only from cited Indian statutes, rules and registry
              records. When the corpus cannot answer, it says so rather than guessing.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => submit(ex)}
                  className="card px-2.5 py-1.5 text-left text-[12.5px] text-ink-soft transition-colors hover:border-indigo-dye hover:text-ink"
                >
                  {ex}
                </button>
              ))}
            </div>
          </section>
        )}

        <div className="space-y-6">
          {turns.map((turn, i) => (
            <AnswerView
              key={turn.id}
              answer={turn.answer}
              defaultOpen={i === turns.length - 1}
              onRemove={() => removeTurn(turn.id)}
            />
          ))}
        </div>

        {loading && (
          <section className="mt-10 max-w-3xl border-t border-rule pt-6">
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
              Classifying, retrieving provisions, verifying citations…
            </p>
          </section>
        )}

        {error && (
          <div className="card mt-8 max-w-3xl border-clay/40 bg-clay-wash p-4">
            <p className="eyebrow text-clay">Could not complete</p>
            <p className="mt-1 text-[14px] text-ink">{error}</p>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* ---------- Composer ---------- */}
      <div className="sticky bottom-0 border-t border-rule bg-paper/95 backdrop-blur">
        <div className="mx-auto max-w-sheet px-6 py-4">
          {pendingClarification && (
            <div className="mb-2 flex items-start gap-2 border-l-2 border-haldi bg-haldi-wash px-3 py-2">
              <span className="eyebrow shrink-0 text-haldi">Replying to</span>
              <p className="text-[12.5px] leading-snug text-ink-soft">
                {pendingClarification}
              </p>
            </div>
          )}

          <div className="card p-1.5">
            <div className="flex items-start gap-2">
              <textarea
                id="q"
                ref={inputRef}
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  // Enter sends; Shift+Enter makes a new line. Ctrl/Cmd+Enter
                  // also sends, for people who expect that.
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit(input);
                  }
                }}
                placeholder={
                  pendingClarification
                    ? "Type your answer…"
                    : "e.g. Can a classical churna from a First Schedule text be patented?"
                }
                className="min-h-[3rem] w-full resize-none bg-transparent px-3 py-2 font-serif text-[15px] leading-relaxed text-ink placeholder:text-ink-faint/70 focus:outline-none"
              />

              <div
                role="radiogroup"
                aria-label="Jurisdiction"
                className="mt-1 flex shrink-0 overflow-hidden rounded-[3px] border border-rule"
              >
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
                    {j === "india" ? "India" : "Intl"}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between gap-3 border-t border-rule px-3 py-2">
              <span className="eyebrow normal-case tracking-normal">
                Enter to ask · Shift + Enter for a new line
              </span>
              <button
                onClick={() => submit(input)}
                disabled={loading || !input.trim()}
                className="rounded-[3px] bg-ink px-4 py-1.5 text-[13px] font-medium text-paper transition-opacity disabled:opacity-35"
              >
                {loading ? "Consulting…" : "Ask"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
