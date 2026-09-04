import { useState } from "react";
import type { Answer, Citation, ReasoningStep } from "../types";

interface Props {
  answer: Answer;
  citationIndex: Map<string, number>;
  hovered: string | null;
  onHoverStep: (ids: string[] | null) => void;
}

// Roughly two sentences. Past this a step stops being scannable, and the
// free model does not reliably respect a word budget however firmly it is
// asked - so the clamp lives here, where it cannot be ignored. Nothing is
// discarded: the full text is one click away.
const CLAMP_CHARS = 210;

function Step({
  step,
  citationIndex,
  hovered,
  onHoverStep,
}: {
  step: ReasoningStep;
  citationIndex: Map<string, number>;
  hovered: string | null;
  onHoverStep: (ids: string[] | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isLinked = hovered !== null && step.citation_ids.includes(hovered);
  const isLong = step.content.length > CLAMP_CHARS;
  const shown =
    expanded || !isLong
      ? step.content
      : `${step.content.slice(0, CLAMP_CHARS).replace(/\s+\S*$/, "")}…`;

  return (
    <li
      className="trail-line relative pl-11"
      onMouseEnter={() => onHoverStep(step.citation_ids)}
      onMouseLeave={() => onHoverStep(null)}
    >
      <span
        className={`absolute left-0 top-0 flex h-8 w-8 items-center justify-center rounded-full border text-[13px] font-semibold transition-colors ${
          step.abstained
            ? "border-clay bg-clay-wash text-clay"
            : isLinked
              ? "border-indigo-dye bg-indigo-dye text-paper"
              : "border-rule bg-paper text-ink-soft"
        }`}
      >
        {step.step}
      </span>

      <h3 className="eyebrow pt-1.5">{step.title}</h3>

      <p className={`prose-legal mt-1.5 ${step.abstained ? "italic text-clay" : ""}`}>
        {shown}
      </p>

      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="eyebrow mt-1 hover:text-indigo-dye"
          aria-expanded={expanded}
        >
          {expanded ? "Show less" : "Show full reasoning"}
        </button>
      )}

      {step.citation_ids.length > 0 && (
        <p className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="eyebrow">Sources</span>
          {step.citation_ids.map((id) => (
            <span
              key={id}
              className={`ref rounded-[2px] px-1.5 py-0.5 transition-colors ${
                hovered === id ? "bg-indigo-dye text-paper" : "bg-indigo-wash text-indigo-dye"
              }`}
            >
              {citationIndex.get(id) ?? "?"}
            </span>
          ))}
        </p>
      )}

      {step.abstained && (
        <p className="eyebrow mt-1.5 text-clay">
          Left unanswered rather than stated without a source
        </p>
      )}
    </li>
  );
}

/**
 * The reasoning trail as four numbered stations joined by a rule — a chain of
 * reasoning, not chat bubbles. Hovering a step lights up the exact sources
 * behind it in the citation rail, which is what makes "every claim is
 * traceable" something you can see rather than something we claim.
 */
export function ReasoningTrail({ answer, citationIndex, hovered, onHoverStep }: Props) {
  return (
    <ol className="space-y-6">
      {answer.steps.map((step) => (
        <Step
          key={step.step}
          step={step}
          citationIndex={citationIndex}
          hovered={hovered}
          onHoverStep={onHoverStep}
        />
      ))}
    </ol>
  );
}

export function buildCitationIndex(citations: Citation[]): Map<string, number> {
  return new Map(citations.map((c, i) => [c.chunk_id, i + 1]));
}
