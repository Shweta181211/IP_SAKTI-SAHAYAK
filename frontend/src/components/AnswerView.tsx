import { useEffect, useMemo, useState } from "react";
import type { Answer } from "../types";
import { CitationCard } from "./CitationCard";
import { ReasoningTrail, buildCitationIndex } from "./ReasoningTrail";
import { Confidence } from "./Confidence";
import { AbstentionPanel, Verdict } from "./Verdict";
import { Escalate } from "./Escalate";

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

  // Small talk is a normal reply, not a refusal - render it plainly, with no
  // verdict banner, no citation rail and no "not answered" framing.
  if (answer.abstention_kind === "conversational") {
    return (
      <article className="border-t border-rule pt-5 first:border-t-0 first:pt-0">
        <p className="mb-3 border-l-2 border-haldi pl-3 font-serif text-[15px] italic text-ink-soft">
          {answer.question}
        </p>
        <p className="prose-legal max-w-2xl">{answer.abstention_message}</p>
        {answer.example_questions.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {answer.example_questions.map((q) => (
              <span key={q} className="card px-2.5 py-1.5 text-[12.5px] text-ink-soft">
                {q}
              </span>
            ))}
          </div>
        )}
      </article>
    );
  }

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
              {answer.escalate && <Escalate reason={answer.escalation_reason} />}
            </div>
          ) : (
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <div className="space-y-6">
                {/* Retrieval ran narrowed. Said plainly and above the answer,
                    because the risk is precisely that the answer looks normal:
                    without query expansion the flagship benchmark does not
                    retrieve Section 3(p) at all, yet still answers confidently
                    from neighbouring provisions. */}
                {answer.search_degraded && answer.degraded_reason && (
                  <div className="border-l-[3px] border-clay bg-clay-wash px-4 py-3">
                    <p className="eyebrow text-clay">Search was narrowed</p>
                    <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">
                      {answer.degraded_reason}
                    </p>
                  </div>
                )}

                {/* Conclusion first. The trail below is the working, for anyone
                    who wants to check it. */}
                {answer.headline && (
                  <div>
                    <p className="font-serif text-[19px] font-medium leading-snug text-ink">
                      {answer.headline}
                    </p>
                    {/* The headline is the sentence most people read, and it
                        used to be the only model output that reached them with
                        no citation check. It is now validated like a step; when
                        nothing backs it, it stays (a correct summary is still
                        useful) but must not read as sourced. */}
                    {answer.headline_unsourced && (
                      <p className="eyebrow mt-1.5 text-ink-faint">
                        Summary — the cited findings are in the steps below
                      </p>
                    )}
                  </div>
                )}
                {answer.confidence && (
                  <Confidence
                    level={answer.confidence}
                    label={answer.confidence_label ?? ""}
                    score={answer.confidence_score}
                    reasons={answer.confidence_reasons}
                  />
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

          {/* An answered question can still warrant a human: `escalate` is set
              when confidence came out limited, i.e. the answer stands and is
              cited but rests on thin support. Placed below the trail so it
              reads as a next step, not as a warning about what you just read. */}
          {!answer.abstained && answer.escalate && (
            <div className="max-w-3xl">
              <Escalate reason={answer.escalation_reason} />
            </div>
          )}

          {/* An answer can now carry an open question with it: the category was
              undetermined, so we answered what the evidence supports and ask
              alongside rather than instead. */}
          {!answer.abstained && answer.clarifying_question && (
            <div className="mt-6 border-l-2 border-haldi bg-haldi-wash px-3 py-2.5">
              <p className="eyebrow text-haldi">To narrow this further</p>
              <p className="prose-legal mt-1 text-[14px]">{answer.clarifying_question}</p>
              <p className="mt-1.5 text-[12px] text-ink-faint">
                Answer in the box below and I will refine the response.
              </p>
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
