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

/** A drag that ended in a selection is not a click on the card. */
function isTextSelected() {
  const sel = window.getSelection();
  return !!sel && !sel.isCollapsed;
}

/**
 * The collapsed line: the step's own first sentence, nothing invented.
 *
 * A summary written by us would be a fifth piece of prose about the law with no
 * citation of its own — the exact shape of the headline defect. Taking the
 * opening sentence is a display transform: everything shown is text that
 * already passed citation validation, and the rest is one click away.
 */
function splitLead(text: string): { lead: string; rest: string } {
  const trimmed = text.trim();
  const match = trimmed.match(/^.*?[.!?](?=\s|$)/);
  let cut = (match ? match[0] : trimmed).length;
  // A very long opening sentence still has to fit a compact card; clamp at a
  // word boundary rather than mid-word.
  let ellipsis = false;
  if (cut > 165) {
    cut = trimmed.slice(0, 165).replace(/\s+\S*$/, "").length;
    ellipsis = true;
  }
  return {
    lead: trimmed.slice(0, cut).trim() + (ellipsis ? "…" : ""),
    // The expanded body shows only what the lead did not. Rendering the full
    // content there instead printed the opening sentence twice, once clamped
    // and once whole, which reads as a rendering fault.
    rest: trimmed.slice(cut).trim(),
  };
}

function Card({
  step,
  index,
  citationIndex,
  citationById,
  active,
  isPinned,
  isOpen,
  onToggleOpen,
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
  isOpen: boolean;
  onToggleOpen: () => void;
  onHoverStep: (ids: string[] | null) => void;
  onTogglePin: () => void;
  onJumpToCitation: (chunkId: string) => void;
}) {
  const [showSource, setShowSource] = useState(false);

  const isLinked = step.citation_ids.some((id) => active.includes(id));
  const sources = step.citation_ids
    .map((id) => citationById.get(id))
    .filter((c): c is Citation => !!c);
  const hasSources = sources.length > 0;

  const { lead, rest } = splitLead(step.content);
  const hasMore = rest.length > 0;

  // The detail region animates on a measured height rather than a
  // grid-rows trick, because it contains a scrollable source panel whose own
  // height changes while it is open — `1fr` would snap when that happens.
  const bodyRef = useRef<HTMLDivElement>(null);
  const [bodyHeight, setBodyHeight] = useState(0);
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    const measure = () => setBodyHeight(el.scrollHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [showSource, rest]);

  // Mouse convenience only — the labelled controls below are the accessible
  // path. A click inside a nested button belongs to that button, and a click
  // that ended a text selection is a drag: people copy statute text out.
  const toggleOnBodyClick = (event: React.MouseEvent) => {
    if ((event.target as HTMLElement).closest("button")) return;
    if (isTextSelected()) return;
    onToggleOpen();
  };

  return (
    <article
      className={`step-card station-in ${isOpen ? "is-open" : ""} ${
        isPinned ? "is-pinned" : ""
      } ${step.abstained ? "is-abstained" : ""} ${isLinked ? "is-linked" : ""}`}
      style={{ "--i": index } as React.CSSProperties}
      onMouseEnter={() => onHoverStep(step.citation_ids)}
      onMouseLeave={() => onHoverStep(null)}
      onClick={toggleOnBodyClick}
      aria-labelledby={`step-title-${step.step}`}
    >
      <header className="step-card-head">
        {/* The medallion pins; the card opens. Two different questions — "keep
            these sources lit while I read" and "show me the whole reasoning" —
            so two controls rather than one overloaded one. */}
        <button
          type="button"
          onClick={onTogglePin}
          disabled={!hasSources}
          aria-pressed={hasSources ? isPinned : undefined}
          aria-label={
            hasSources
              ? `${isPinned ? "Unpin" : "Pin"} the sources behind step ${step.step}: ${step.title}`
              : `Step ${step.step}: ${step.title}`
          }
          title={hasSources ? "Keep this step's sources highlighted" : undefined}
          className="step-medallion"
        >
          <span className="step-numeral">{step.step}</span>
        </button>

        <div className="min-w-0 flex-1">
          <h3 id={`step-title-${step.step}`} className="step-card-title">
            <span className="step-card-icon" aria-hidden>
              <StepIcon step={step.step} />
            </span>
            {step.title}
          </h3>
        </div>

        <button
          type="button"
          onClick={onToggleOpen}
          aria-expanded={isOpen}
          aria-label={`${isOpen ? "Collapse" : "Expand"} step ${step.step}`}
          className="step-chevron"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </header>

      {/* Collapsed: exactly one sentence. No paragraphs by default. */}
      <p className={`step-lead ${step.abstained ? "is-abstained" : ""}`}>{lead}</p>

      <div
        className="step-body"
        style={{ height: isOpen ? bodyHeight : 0 }}
        aria-hidden={!isOpen}
      >
        <div ref={bodyRef} className="step-body-inner">
          {hasMore && (
            <p className={`step-full ${step.abstained ? "is-abstained" : ""}`}>
              {rest}
            </p>
          )}

          {hasSources && (
            <>
              <p className="step-provisions">
                {sources.map((c) => (
                  <button
                    key={c.chunk_id}
                    type="button"
                    onClick={() => onJumpToCitation(c.chunk_id)}
                    onMouseEnter={() => onHoverStep([c.chunk_id])}
                    title="Show this source in the rail"
                    className={`step-provision ${
                      active.includes(c.chunk_id) ? "is-active" : ""
                    }`}
                  >
                    <span className="step-provision-n">
                      {citationIndex.get(c.chunk_id) ?? "?"}
                    </span>
                    <span className="step-provision-act">{c.act_name}</span>
                    {c.section && <span className="step-provision-sec">{c.section}</span>}
                  </button>
                ))}
              </p>

              <button
                type="button"
                onClick={() => setShowSource((v) => !v)}
                aria-expanded={showSource}
                className="step-source-toggle"
              >
                <span className="h-3.5 w-3.5" aria-hidden>
                  <SealIcon />
                </span>
                {showSource ? "Hide source text" : "Read source text"}
              </button>

              {showSource && (
                <div className="step-source">
                  {sources.map((c) => (
                    <div key={c.chunk_id}>
                      <p className="step-source-head">
                        <span className="step-provision-n">
                          {citationIndex.get(c.chunk_id) ?? "?"}
                        </span>
                        {c.act_name}
                        {c.section ? ` · ${c.section}` : ""}
                        {c.page ? ` · p. ${c.page}` : ""}
                      </p>
                      <blockquote>{c.excerpt}</blockquote>
                    </div>
                  ))}
                  <p className="eyebrow text-ink-faint">Verbatim from the corpus</p>
                </div>
              )}
            </>
          )}

          {step.abstained && (
            <p className="eyebrow mt-2 text-clay">
              Left unanswered rather than stated without a source
            </p>
          )}
        </div>
      </div>

      {/* Collapsed footer: how many sources sit behind this step, so the card
          advertises that it has something to open. */}
      {!isOpen && hasSources && (
        <p className="step-foot">
          <span className="eyebrow">
            {sources.length} source{sources.length === 1 ? "" : "s"}
          </span>
          {isPinned && <span className="eyebrow text-indigo-dye">pinned</span>}
        </p>
      )}
    </article>
  );
}

/**
 * The reasoning trail as a 2×2 grid of cards that open in place.
 *
 *   collapsed — number, icon, title, one sentence
 *   expanded  — the full reasoning, the provisions it rests on, and the
 *               verbatim statute behind them
 *
 * This replaced a single vertical column of two-faced cards. The column read
 * as a transcript and pushed the citation rail far down the page; four compact
 * cards let a reader see the whole shape of the argument at once and choose
 * where to look, which is what the trail is for.
 *
 * A card expands **in its own column** rather than spanning the grid. Spanning
 * looks richer for one frame and then reflows every sibling sideways, which is
 * a jump the eye reads as a glitch; growing in place moves nothing but the row
 * beneath. `align-items: start` keeps the sibling card its natural height
 * instead of stretching it to match.
 *
 * The link to the citation rail keeps both strengths it had:
 *   hover a card        — transient, lights that step's sources
 *   click the medallion — pins them, so they stay lit while you read
 * Hover is mouse-only, and on a phone or a projector the pin is the only one
 * that works at all.
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
  const [openStep, setOpenStep] = useState<number | null>(null);

  return (
    <div className="trail-grid">
      {answer.steps.map((step, i) => (
        <Card
          key={step.step}
          step={step}
          index={i}
          citationIndex={citationIndex}
          citationById={citationById}
          active={active}
          isPinned={pinnedStep === step.step}
          isOpen={openStep === step.step}
          onToggleOpen={() =>
            setOpenStep((current) => (current === step.step ? null : step.step))
          }
          onHoverStep={onHoverStep}
          onTogglePin={() => {
            const next = pinnedStep === step.step ? null : step.step;
            onPinnedStepChange(next);
            onPinStep(next === null ? null : step.citation_ids);
          }}
          onJumpToCitation={onJumpToCitation}
        />
      ))}
    </div>
  );
}

export function buildCitationIndex(citations: Citation[]): Map<string, number> {
  return new Map(citations.map((c, i) => [c.chunk_id, i + 1]));
}

export function buildCitationMap(citations: Citation[]): Map<string, Citation> {
  return new Map(citations.map((c) => [c.chunk_id, c]));
}
