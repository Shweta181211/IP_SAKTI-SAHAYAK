import { useState } from "react";
import type { Answer, Citation, ReasoningStep } from "../types";
import { StepIcon } from "./Icons";

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
  index,
  citationIndex,
  hovered,
  onHoverStep,
}: {
  step: ReasoningStep;
  index: number;
  citationIndex: Map<string, number>;
  hovered: string | null;
  onHoverStep: (ids: string[] | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isLinked = hovered !== null && step.citation_ids.includes(hovered);
  const isLong = step.content.length > CLAMP_CHARS;
  // Split once, at a word boundary. The head always renders; the tail lives in
  // the animated reveal below it, so expanding is a height change rather than a
  // text swap. The trailing ellipsis belongs to the collapsed state only - it
  // would otherwise sit stranded mid-sentence once the rest is showing.
  const head = step.content.slice(0, CLAMP_CHARS).replace(/\s+\S*$/, "");
  const tail = step.content.slice(head.length).trimStart();

  return (
    <li
      className="trail-line station-in relative pl-11"
      // Each station arrives just after the one above it, walking the eye down
      // the reasoning in the order the argument is actually made.
      style={{ "--i": index } as React.CSSProperties}
      onMouseEnter={() => onHoverStep(step.citation_ids)}
      onMouseLeave={() => onHoverStep(null)}
      onFocus={() => onHoverStep(step.citation_ids)}
      onBlur={() => onHoverStep(null)}
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
        {/* The number is the anchor; the icon appears when the step is linked
            to a source under the cursor. Both are present in the DOM and
            cross-faded, so nothing reflows on hover. */}
        <span className={`transition-opacity duration-200 ${isLinked ? "opacity-0" : "opacity-100"}`}>
          {step.step}
        </span>
        <span
          className={`absolute h-4 w-4 transition-opacity duration-200 ${
            isLinked ? "opacity-100" : "opacity-0"
          }`}
        >
          <StepIcon step={step.step} />
        </span>
      </span>

      <h3 className="eyebrow flex items-center gap-1.5 pt-1.5">
        <span className="h-3.5 w-3.5 text-ink-faint">
          <StepIcon step={step.step} />
        </span>
        {step.title}
      </h3>

      <p className={`prose-legal mt-1.5 ${step.abstained ? "italic text-clay" : ""}`}>
        {isLong && !expanded ? `${head}…` : isLong ? head : step.content}
      </p>

      {/* The remainder animates open on a grid-rows transition rather than
          appearing instantly, so a long provision does not shove the citation
          rail down the page under the reader's eye. */}
      {isLong && (
        <>
          <div className="reveal" data-open={expanded} aria-hidden={!expanded}>
            <div>
              <p className={`prose-legal pt-1.5 ${step.abstained ? "italic text-clay" : ""}`}>
                {tail}
              </p>
            </div>
          </div>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="eyebrow mt-1 transition-colors hover:text-indigo-dye"
            aria-expanded={expanded}
          >
            {expanded ? "Show less" : "Show full reasoning"}
          </button>
        </>
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
      {answer.steps.map((step, i) => (
        <Step
          key={step.step}
          step={step}
          index={i}
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
