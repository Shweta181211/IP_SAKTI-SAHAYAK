import { useEffect, useMemo, useState } from "react";
import type { Answer } from "../types";
import { CitationCard } from "./CitationCard";
import { ReasoningTrail, buildCitationIndex } from "./ReasoningTrail";
import { AbstentionPanel, Verdict } from "./Verdict";

interface Props {
  answer: Answer;
  /** The newest consultation opens; earlier ones collapse so the transcript
   *  stays scannable instead of becoming a very long scroll. */
  defaultOpen?: boolean;
  onRemove?: () => void;
}

export function AnswerView({ answer, defaultOpen = true, onRemove }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [hovered, setHovered] = useState<string | null>(null);

  // A new answer arriving makes this the newest turn; reopen it.
  useEffect(() => setOpen(defaultOpen), [defaultOpen]);

  const citationIndex = useMemo(
    () => buildCitationIndex(answer.citations),
    [answer.citations],
  );

  const summary = answer.abstained
    ? answer.abstention_kind === "none"
      ? "clarification requested"
      : "not answered"
    : `${answer.citations.length} source${answer.citations.length === 1 ? "" : "s"}`;

  return (
    <article className="border-t border-rule pt-5 first:border-t-0 first:pt-0">
      {/* ---------- Header: always visible, doubles as the collapsed row ---------- */}
      <div className="flex items-start gap-3">
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="group flex min-w-0 flex-1 items-start gap-3 text-left"
        >
          <span
            className={`mt-1 shrink-0 text-ink-faint transition-transform ${
              open ? "rotate-90" : ""
            }`}
            aria-hidden
          >
            ▸
          </span>

          <span className="min-w-0 flex-1 border-l-2 border-haldi pl-3">
            <span className="block font-serif text-[15px] italic text-ink-soft group-hover:text-ink">
              {answer.question}
            </span>
            {answer.resolved_question && (
              <span className="eyebrow mt-1 block normal-case tracking-normal text-ink-faint">
                Understood as: {answer.resolved_question}
              </span>
            )}
            {!open && (
              <span className="eyebrow mt-1 block">
                {answer.classification?.label ?? "—"} · {summary}
              </span>
            )}
          </span>
        </button>

        {onRemove && (
          <button
            onClick={onRemove}
            title="Remove this consultation"
            className="eyebrow shrink-0 px-1 text-ink-faint hover:text-clay"
          >
            ✕
          </button>
        )}
      </div>

      {!open ? null : (
        <div className="mt-5">
          {answer.abstained ? (
            <div className="max-w-3xl space-y-5">
              {answer.classification && <Verdict classification={answer.classification} />}
              <AbstentionPanel
                kind={answer.abstention_kind}
                message={answer.abstention_message}
                clarifying={answer.clarifying_question}
              />
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <div className="space-y-6">
                {/* Conclusion first. The trail below is the working, for anyone
                    who wants to check it. */}
                {answer.headline && (
                  <p className="font-serif text-[19px] font-medium leading-snug text-ink">
                    {answer.headline}
                  </p>
                )}
                {answer.classification && <Verdict classification={answer.classification} />}
                <ReasoningTrail
                  answer={answer}
                  citationIndex={citationIndex}
                  hovered={hovered}
                  onHoverStep={(ids) => setHovered(ids?.[0] ?? null)}
                />
              </div>

              <aside className="lg:sticky lg:top-20 lg:self-start">
                <div className="mb-2.5 flex items-baseline justify-between">
                  <h2 className="eyebrow">Sources cited</h2>
                  <span className="ref text-ink-faint">{answer.citations.length}</span>
                </div>
                <ul className="space-y-2">
                  {answer.citations.map((c, i) => (
                    <CitationCard
                      key={c.chunk_id}
                      citation={c}
                      index={i + 1}
                      highlighted={hovered === c.chunk_id}
                      onHover={setHovered}
                    />
                  ))}
                </ul>

                {answer.rejected_citation_ids.length > 0 && (
                  <div className="mt-3 border-l-2 border-neem bg-neem-wash px-3 py-2">
                    <p className="eyebrow text-neem">Citation guard</p>
                    <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">
                      {answer.rejected_citation_ids.length} unverifiable reference
                      {answer.rejected_citation_ids.length > 1 ? "s were" : " was"} rejected
                      before this answer was shown.
                    </p>
                  </div>
                )}
              </aside>
            </div>
          )}

          <p className="mt-8 border-t border-rule pt-3 text-[12px] leading-relaxed text-ink-faint">
            {answer.disclaimer}
          </p>
        </div>
      )}
    </article>
  );
}
