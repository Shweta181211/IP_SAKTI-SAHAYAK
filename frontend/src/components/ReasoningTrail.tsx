import { useEffect, useRef, useState } from "react";
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

/** A drag that ended in a selection is not a click. */
function isTextSelected() {
  const sel = window.getSelection();
  return !!sel && !sel.isCollapsed;
}

/**
 * The reasoning trail as four sealed volumes on a shelf.
 *
 * It began as a stack of paragraphs, which read as a transcript, and then as a
 * 2×2 of cards, which read as a dashboard. Both showed all four answers at
 * once, and that is the problem: the reader met four paragraphs of legal prose
 * with no idea which one they wanted, so they read none of them.
 *
 * Closed, a volume shows only its number, its seal and its title — the shape of
 * the argument, and nothing to read yet. Opening one is a deliberate act, and
 * the others fold back to spines to make room. So the layout says the thing the
 * product is actually claiming: this is ONE argument in four ordered parts, and
 * you can open any part and see the provision underneath it.
 *
 * Two mechanics worth knowing:
 *
 * **The width animates on `flex-grow`, not on `width`.** Growing one panel has
 * to shrink the others by exactly the space it takes, and flex already solves
 * that; animating widths directly means computing four of them and fighting
 * rounding at every frame.
 *
 * **The body is laid out at its open width the whole time and clipped.** If it
 * reflowed as the panel grew, the text would rewrap on every frame of the
 * animation, which reads as a stutter rather than an opening.
 */

const ROMAN = ["I", "II", "III", "IV"];

/** The seal: the logo's leaf inside a ring, as a wax stamp on each volume. */
function LeafSeal() {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden>
      <circle cx="24" cy="24" r="21" stroke="currentColor" strokeWidth="0.9" opacity="0.5" />
      <circle cx="24" cy="24" r="17" stroke="currentColor" strokeWidth="0.5" opacity="0.3" />
      <path
        d="M24 9 C17 19 17 29 24 39 C31 29 31 19 24 9 Z"
        fill="currentColor"
        opacity="0.9"
      />
      <path d="M24 10 V38" stroke="var(--paper)" strokeWidth="0.8" opacity="0.45" />
    </svg>
  );
}

function Volume({
  step,
  index,
  isOpen,
  isShrunk,
  onToggle,
  citationIndex,
  citationById,
  active,
  isPinned,
  onHoverStep,
  onJumpToCitation,
}: {
  step: ReasoningStep;
  index: number;
  isOpen: boolean;
  isShrunk: boolean;
  onToggle: () => void;
  citationIndex: Map<string, number>;
  citationById: Map<string, Citation>;
  active: string[];
  isPinned: boolean;
  onHoverStep: (ids: string[] | null) => void;
  onJumpToCitation: (chunkId: string) => void;
}) {
  const [showSource, setShowSource] = useState(false);

  const isLinked = step.citation_ids.some((id) => active.includes(id));
  const sources = step.citation_ids
    .map((id) => citationById.get(id))
    .filter((c): c is Citation => !!c);
  const hasSources = sources.length > 0;

  // Closing a volume should not leave its source panel open behind it, or
  // reopening it later starts halfway through a reading the user never chose.
  useEffect(() => {
    if (!isOpen) setShowSource(false);
  }, [isOpen]);

  return (
    <article
      className={`step-card volume ${isOpen ? "is-open" : ""} ${
        isShrunk ? "is-shrunk" : ""
      } ${step.abstained ? "is-abstained" : ""} ${isPinned ? "is-pinned" : ""} ${
        isLinked ? "is-linked" : ""
      }`}
      style={{ "--i": index } as React.CSSProperties}
      onMouseEnter={() => onHoverStep(step.citation_ids)}
      onMouseLeave={() => onHoverStep(null)}
    >
      {/* ------------------------------ the spine ------------------------------ */}
      <button
        type="button"
        className="volume-spine"
        onClick={(e) => {
          if (isTextSelected()) return;
          e.stopPropagation();
          onToggle();
        }}
        aria-expanded={isOpen}
        aria-label={`${isOpen ? "Collapse" : "Expand"} step ${step.step}: ${step.title}`}
        data-roman={ROMAN[index] ?? step.step}
      >
        {/* Seal, numeral and the step's own glyph on one line. Stacked, the
            plate's contents outgrew a closed row and flex shrank the title -
            which has `overflow: hidden`, giving it an automatic minimum size of
            zero - to nothing. */}
        <span className="volume-mark" aria-hidden>
          <span className="volume-seal">
            <LeafSeal />
          </span>
          <span className="volume-roman">{ROMAN[index] ?? step.step}</span>
          <span className="volume-cue">
            <StepIcon step={step.step} />
          </span>
        </span>
        <span className="volume-title">{step.title}</span>
        {/* Only on hover, and only on a closed plate: the shelf should read as
            four titles at rest, not four buttons shouting to be pressed. */}
        <span className="volume-hint" aria-hidden>
          {hasSources ? `Open · ${sources.length} source${sources.length === 1 ? "" : "s"}` : "Open"}
        </span>
      </button>

      {/* ------------------------------- the leaf ------------------------------ */}
      <div className="volume-body" inert={!isOpen} aria-hidden={!isOpen}>
        <div className="volume-inner">
          <header className="volume-head">
            <span className="volume-head-roman" aria-hidden>
              {ROMAN[index] ?? step.step}
            </span>
            <span className="volume-head-icon" aria-hidden>
              <StepIcon step={step.step} />
            </span>
            <h3 className="volume-head-title">{step.title}</h3>

            {hasSources && (
              <span className="volume-tracing" aria-hidden>
                {sources.length} source{sources.length === 1 ? "" : "s"} lit
              </span>
            )}
            <button
              type="button"
              onClick={onToggle}
              aria-label={`Close step ${step.step}`}
              className="volume-close"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              </svg>
            </button>
          </header>

          <div className="volume-scroll">
            <p className={`step-lead prose-legal ${step.abstained ? "is-abstained" : ""}`}>
              {step.content}
            </p>

            {hasSources && (
              <>
                <p className="volume-provisions">
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
                      {c.section && (
                        <span className="step-provision-sec">{c.section}</span>
                      )}
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
                  {showSource ? "Hide the law itself" : "Read the law itself"}
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
              <p className="eyebrow mt-3 text-clay">
                Left unanswered rather than stated without a source
              </p>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

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
  // Nothing open to begin with. The closed shelf IS the summary: four titles in
  // order, which is the shape of the argument. Opening one is the reader's
  // choice about where to look, and pre-opening one makes that choice for them.
  const [openStep, setOpenStep] = useState<number | null>(null);
  const shelfRef = useRef<HTMLDivElement>(null);

  // Left/Right move between volumes on the shelf, the way arrow keys move
  // between tabs. Without this the whole thing is reachable only by tabbing
  // through every control inside the volume that happens to be open.
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const spines = Array.from(
      shelfRef.current?.querySelectorAll<HTMLButtonElement>(".volume-spine") ?? [],
    );
    const here = spines.indexOf(document.activeElement as HTMLButtonElement);
    if (here === -1) return;
    event.preventDefault();
    const next = event.key === "ArrowRight" ? here + 1 : here - 1;
    spines[(next + spines.length) % spines.length]?.focus();
  };

  // Two rows of two rather than one row of four. Four abreast made each volume
  // a sliver, and opening one left the other three as bookends down the side of
  // the page; paired, a closed volume is a plate wide enough to carry its title
  // horizontally, and an opened one takes most of its own row instead of a
  // quarter of the page.
  const rows: ReasoningStep[][] = [];
  for (let i = 0; i < answer.steps.length; i += 2) {
    rows.push(answer.steps.slice(i, i + 2));
  }

  return (
    <div ref={shelfRef} className="trail-shelf" onKeyDown={onKeyDown}>
      {rows.map((row, r) => {
        // Only the row holding the open volume changes shape. The other row
        // stays exactly as it was, so opening something moves as little of the
        // page as possible.
        const rowIsOpen = row.some((step) => step.step === openStep);
        return (
          <div key={r} className={`shelf-row ${rowIsOpen ? "has-open" : ""}`}>
            {row.map((step, c) => (
              <Volume
                key={step.step}
                step={step}
                index={r * 2 + c}
                isOpen={openStep === step.step}
                isShrunk={rowIsOpen && openStep !== step.step}
                onToggle={() => {
                  // Opening a volume IS the act of focusing on it, so it lights
                  // that step's sources in the rail and dims the rest. This used
                  // to need a separate "Pin sources" button beside the title -
                  // two controls for one intention, and the one that mattered
                  // was the one nobody pressed.
                  const next = openStep === step.step ? null : step.step;
                  setOpenStep(next);
                  onPinnedStepChange(next);
                  onPinStep(next === null ? null : step.citation_ids);
                }}
                citationIndex={citationIndex}
                citationById={citationById}
                active={active}
                isPinned={pinnedStep === step.step}
                onHoverStep={onHoverStep}
                onJumpToCitation={onJumpToCitation}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}

export function buildCitationIndex(citations: Citation[]): Map<string, number> {
  return new Map(citations.map((c, i) => [c.chunk_id, i + 1]));
}

export function buildCitationMap(citations: Citation[]): Map<string, Citation> {
  return new Map(citations.map((c) => [c.chunk_id, c]));
}
