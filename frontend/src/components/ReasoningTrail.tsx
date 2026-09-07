import { useLayoutEffect, useRef, useState } from "react";
import type { Answer, Citation, ReasoningStep } from "../types";
import { SealIcon, StepIcon } from "./Icons";

interface Props {
  answer: Answer;
  citationIndex: Map<string, number>;
  citationById: Map<string, Citation>;
  /** Citation ids currently lit in the rail — hover if any, otherwise the pin. */
  active: string[];
  /** Transient: follows the cursor / focus ring. */
  onHoverStep: (ids: string[] | null) => void;
  /** Sticky: survives the cursor leaving. `null` clears it. */
  onPinStep: (ids: string[] | null) => void;
  /** Bring one source card into view and light it. */
  onJumpToCitation: (chunkId: string) => void;
  pinnedStep: number | null;
  onPinnedStepChange: (step: number | null) => void;
}

// Roughly two sentences. Past this a step stops being scannable, and the
// free model does not reliably respect a word budget however firmly it is
// asked - so the clamp lives here, where it cannot be ignored. Nothing is
// discarded: the full text is one click away.
const CLAMP_CHARS = 210;

/** A drag that ended in a selection is not a click on the card. */
function isTextSelected() {
  const sel = window.getSelection();
  return !!sel && !sel.isCollapsed;
}

function Step({
  step,
  index,
  citationIndex,
  citationById,
  active,
  isPinned,
  onHoverStep,
  onTogglePin,
  onJumpToCitation,
}: {
  step: ReasoningStep;
  index: number;
  citationIndex: Map<string, number>;
  citationById: Map<string, Citation>;
  active: string[];
  isPinned: boolean;
  onHoverStep: (ids: string[] | null) => void;
  onTogglePin: () => void;
  onJumpToCitation: (chunkId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [flipped, setFlipped] = useState(false);

  const isLinked = step.citation_ids.some((id) => active.includes(id));
  const isLong = step.content.length > CLAMP_CHARS;
  // Split once, at a word boundary. The head always renders; the tail lives in
  // the animated reveal below it, so expanding is a height change rather than a
  // text swap. The trailing ellipsis belongs to the collapsed state only - it
  // would otherwise sit stranded mid-sentence once the rest is showing.
  const head = step.content.slice(0, CLAMP_CHARS).replace(/\s+\S*$/, "");
  const tail = step.content.slice(head.length).trimStart();

  const sources = step.citation_ids
    .map((id) => citationById.get(id))
    .filter((c): c is Citation => !!c);
  const hasSources = sources.length > 0;

  // Both faces are absolutely positioned so they can occupy the same space and
  // rotate past each other, which means the container has no intrinsic height.
  // It takes the height of whichever face is showing, measured rather than
  // guessed: a statute excerpt and two sentences of prose are nowhere near the
  // same size, and a fixed height would either clip the law or leave a hole.
  const frontRef = useRef<HTMLDivElement>(null);
  const backRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState<number>();

  useLayoutEffect(() => {
    const el = flipped ? backRef.current : frontRef.current;
    if (!el) return;
    const measure = () => setHeight(el.offsetHeight);
    measure();
    // Catches the expand toggle, a font swap, and any reflow from resizing.
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [flipped, expanded]);

  const turn = () => hasSources && setFlipped((v) => !v);

  // Both faces share this. A click that lands inside a nested button belongs to
  // that button - without the guard the button's turn() and the card's turn()
  // both fire and the card toggles twice, which looks exactly like a control
  // that does nothing. A click that ends a text selection is a drag, not a
  // turn: people copy statute text out of the back face.
  const turnOnBodyClick = (event: React.MouseEvent) => {
    if ((event.target as HTMLElement).closest("button")) return;
    if (isTextSelected()) return;
    turn();
  };

  return (
    <li
      className="trail-line station-in relative pl-11"
      // Each station arrives just after the one above it, walking the eye down
      // the reasoning in the order the argument is actually made. The same
      // index drives the connecting rule's draw, so the line grows into the
      // gap the next card is about to occupy.
      style={{ "--i": index } as React.CSSProperties}
    >
      {/* The medallion pins; the card turns. Two different questions - "keep
          these sources lit while I read" and "show me the law itself" - so two
          controls rather than one overloaded one. */}
      <button
        type="button"
        onClick={onTogglePin}
        // Nothing to pin, so nothing to press. Step 4 is a scope statement and
        // carries no citation by design; offering a toggle that lights nothing
        // would advertise a broken control.
        disabled={!hasSources}
        aria-pressed={hasSources ? isPinned : undefined}
        aria-label={
          hasSources
            ? `${isPinned ? "Unpin" : "Pin"} the sources behind step ${step.step}: ${step.title}`
            : `Step ${step.step}: ${step.title}`
        }
        title={hasSources ? "Keep this step's sources highlighted" : undefined}
        className={`trail-medallion absolute left-0 top-0 z-10 flex h-8 w-8 items-center justify-center rounded-full border text-[13px] font-semibold ${
          step.abstained
            ? "border-clay bg-clay-wash text-clay"
            : isPinned || isLinked
              ? "border-indigo-dye bg-indigo-dye text-paper"
              : "border-rule bg-paper text-ink-soft"
        }`}
      >
        {/* The number is the anchor; the icon appears when the step is linked
            to a source under the cursor. Both are present in the DOM and
            cross-faded, so nothing reflows on hover. */}
        <span
          className={`transition-opacity duration-200 ${isPinned || isLinked ? "opacity-0" : "opacity-100"}`}
        >
          {step.step}
        </span>
        <span
          className={`absolute h-4 w-4 transition-opacity duration-200 ${
            isPinned || isLinked ? "opacity-100" : "opacity-0"
          }`}
        >
          <StepIcon step={step.step} />
        </span>
      </button>

      <div
        className="trail-flip"
        data-flipped={flipped}
        style={height ? { height } : undefined}
        onMouseEnter={() => onHoverStep(step.citation_ids)}
        onMouseLeave={() => onHoverStep(null)}
      >
        <div className="trail-flip-inner">
          {/* ------------------------------- front ------------------------------- */}
          <div className="trail-face trail-face--front" inert={flipped} aria-hidden={flipped}>
            <div
              ref={frontRef}
              className={`trail-card ${isPinned ? "is-pinned" : ""} ${
                step.abstained ? "is-abstained" : ""
              } ${hasSources ? "" : "is-flat"}`}
              // Mouse convenience only - the labelled buttons above and below
              // are the accessible controls.
              onClick={turnOnBodyClick}
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="eyebrow flex items-center gap-1.5">
                  <span className="h-3.5 w-3.5 text-ink-faint">
                    <StepIcon step={step.step} />
                  </span>
                  {step.title}
                </h3>
                {hasSources && (
                  // Always present, not hover-only: on a touch screen a
                  // hover-revealed affordance is an affordance nobody finds.
                  <button
                    type="button"
                    onClick={turn}
                    title="Turn over to read the source text"
                    aria-label={`Read the source text behind step ${step.step}`}
                    className="trail-turn shrink-0 text-ink-faint"
                  >
                    <TurnIcon />
                  </button>
                )}
              </div>

              <p className={`prose-legal mt-1.5 ${step.abstained ? "italic text-clay" : ""}`}>
                {isLong && !expanded ? `${head}…` : isLong ? head : step.content}
              </p>

              {/* The remainder animates open on a grid-rows transition rather
                  than appearing instantly, so a long provision does not shove
                  the citation rail down the page under the reader's eye. */}
              {isLong && (
                <>
                  <div className="reveal" data-open={expanded} aria-hidden={!expanded}>
                    <div>
                      <p
                        className={`prose-legal pt-1.5 ${step.abstained ? "italic text-clay" : ""}`}
                      >
                        {tail}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    className="eyebrow mt-1 transition-colors hover:text-indigo-dye"
                    aria-expanded={expanded}
                  >
                    {expanded ? "Show less" : "Show full reasoning"}
                  </button>
                </>
              )}

              {hasSources && (
                <p className="mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-rule/60 pt-2.5">
                  <span className="eyebrow">Sources</span>
                  {step.citation_ids.map((id) => (
                    // A chip is a jump, not decoration: on a phone the rail is
                    // far below the trail, and on a projector nobody can hover
                    // precisely.
                    <button
                      key={id}
                      type="button"
                      onClick={() => onJumpToCitation(id)}
                      onMouseEnter={() => onHoverStep([id])}
                      title="Show this source in the rail"
                      className={`ref trail-chip rounded-[2px] px-1.5 py-0.5 ${
                        active.includes(id)
                          ? "bg-indigo-dye text-paper"
                          : "bg-indigo-wash text-indigo-dye"
                      }`}
                    >
                      {citationIndex.get(id) ?? "?"}
                    </button>
                  ))}
                  {isPinned && <span className="eyebrow text-indigo-dye">pinned</span>}
                  <button
                    type="button"
                    onClick={turn}
                    className="eyebrow ml-auto text-indigo-dye transition-colors hover:text-ink"
                  >
                    Read the law →
                  </button>
                </p>
              )}

              {step.abstained && (
                <p className="eyebrow mt-1.5 text-clay">
                  Left unanswered rather than stated without a source
                </p>
              )}
            </div>
          </div>

          {/* -------------------------------- back -------------------------------- */}
          {hasSources && (
            <div className="trail-face trail-face--back" inert={!flipped} aria-hidden={!flipped}>
              <div ref={backRef} className="trail-card is-back" onClick={turnOnBodyClick}>
                <div className="flex items-start justify-between gap-2">
                  <h3 className="eyebrow flex items-center gap-1.5 text-indigo-dye">
                    <span className="h-3.5 w-3.5">
                      <SealIcon />
                    </span>
                    Source text · step {step.step}
                  </h3>
                  <button
                    type="button"
                    onClick={turn}
                    title="Turn back to the reasoning"
                    aria-label={`Back to the reasoning for step ${step.step}`}
                    className="trail-turn shrink-0 text-indigo-dye"
                  >
                    <TurnIcon />
                  </button>
                </div>

                {/* Capped and scrollable: a statutory chunk runs to ~800 tokens
                    and an uncapped back face would make the card taller than
                    the viewport, which is worse than a scrollbar. */}
                <div className="trail-back-scroll mt-2 space-y-3">
                  {sources.map((c) => (
                    <div key={c.chunk_id}>
                      <p className="flex items-baseline gap-1.5">
                        <span className="ref inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[2px] bg-indigo-dye text-[10px] text-paper">
                          {citationIndex.get(c.chunk_id) ?? "?"}
                        </span>
                        <span className="font-serif text-[13px] font-medium leading-snug text-ink">
                          {c.act_name}
                        </span>
                      </p>
                      <p className="ref mt-0.5 pl-[22px] text-indigo-dye">
                        {c.section ?? <span className="text-ink-faint">provision not identified</span>}
                        {c.page ? <span className="text-ink-faint"> · p. {c.page}</span> : null}
                      </p>
                      <blockquote className="mt-1.5 border-l-2 border-indigo-dye/35 pl-2.5 font-serif text-[12.5px] leading-relaxed text-ink-soft">
                        {c.excerpt}
                      </blockquote>
                    </div>
                  ))}
                </div>

                <p className="mt-2.5 flex items-center justify-between border-t border-rule/60 pt-2.5">
                  <span className="eyebrow">Verbatim from the corpus</span>
                  <button
                    type="button"
                    onClick={turn}
                    className="eyebrow text-indigo-dye transition-colors hover:text-ink"
                  >
                    ← Back to the reasoning
                  </button>
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

/** Two arrows turning a leaf over — the card's own gesture, not a generic refresh. */
function TurnIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" className="h-4 w-4">
      <path d="M4 9a8 8 0 0 1 13.6-4.6L20 7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 3v4h-4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M20 15a8 8 0 0 1-13.6 4.6L4 17" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 21v-4h4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * The reasoning trail as four numbered stations joined by a rule — a chain of
 * reasoning, not chat bubbles. Each station is a card with two faces:
 *
 *   front — what we concluded, in our words
 *   back  — the verbatim statute the conclusion came from
 *
 * That is the product's whole claim rendered as one gesture. Turning a card
 * over is not decoration: it puts the law itself directly behind the sentence
 * that relies on it, so "every claim is traceable" is checked in place rather
 * than by trusting a marker and hunting for the matching card.
 *
 * Alongside it, the link to the citation rail has two strengths:
 *   hover  — transient preview
 *   click the medallion — pins them, so they stay lit while you read
 *
 * The pin matters because hover is a mouse-only affordance: on a phone, and on
 * a projector where a presenter cannot hover precisely, that demonstration
 * simply did not exist.
 */
export function ReasoningTrail({
  answer,
  citationIndex,
  citationById,
  active,
  onHoverStep,
  onPinStep,
  onJumpToCitation,
  pinnedStep,
  onPinnedStepChange,
}: Props) {
  return (
    <ol className="space-y-5">
      {answer.steps.map((step, i) => (
        <Step
          key={step.step}
          step={step}
          index={i}
          citationIndex={citationIndex}
          citationById={citationById}
          active={active}
          isPinned={pinnedStep === step.step}
          onHoverStep={onHoverStep}
          onTogglePin={() => {
            const next = pinnedStep === step.step ? null : step.step;
            onPinnedStepChange(next);
            onPinStep(next === null ? null : step.citation_ids);
          }}
          onJumpToCitation={onJumpToCitation}
        />
      ))}
    </ol>
  );
}

export function buildCitationIndex(citations: Citation[]): Map<string, number> {
  return new Map(citations.map((c, i) => [c.chunk_id, i + 1]));
}

export function buildCitationMap(citations: Citation[]): Map<string, Citation> {
  return new Map(citations.map((c) => [c.chunk_id, c]));
}
