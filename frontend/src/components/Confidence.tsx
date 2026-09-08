import { useEffect, useState } from "react";
import type { ConfidenceLevel } from "../types";

interface Props {
  level: ConfidenceLevel;
  label: string;
  score: number | null;
  reasons: string[];
}

/**
 * How well the cited sources support this answer, as a semicircular gauge.
 *
 * Three deliberate constraints:
 *
 * **It is called "Evidence support", not confidence and not certainty.** The
 * number behind it is a weighted blend of citation survival, provision
 * specificity, source breadth and retriever agreement. It measures how well
 * anchored the answer is in what it cited. It says nothing about whether the
 * law was applied correctly or how a matter would come out, and a word like
 * "confidence" invites exactly that reading.
 *
 * **The raw score is never shown to a reader.** It used to appear as
 * "(internal score 0.87, uncalibrated)" in the accessibility tree — still
 * showing it, just only to screen-reader users, complete with a two-decimal
 * false precision. It now sits behind a dev flag.
 *
 * **The needle rests on a band, not on a value.** The gauge has four arc
 * segments and the needle points at the middle of the band that was reached —
 * it never lands between two, because the underlying score is ordinal and
 * uncalibrated, and a needle at an arbitrary angle would imply a resolution
 * this measurement does not have.
 *
 * Colour stays semantic: filled arc in neem, which already means
 * grounded/verified here; the bottom band in clay, which means a limit. Haldi
 * is deliberately absent — it names the classification verdict and nothing
 * else.
 */

const BANDS: ConfidenceLevel[] = ["limited", "moderate", "high", "strong"];
const TICK: Record<ConfidenceLevel, string> = {
  limited: "Thin",
  moderate: "Some",
  high: "Well",
  strong: "Strong",
};

// Gauge geometry. A half turn, 180° on the left to 0° on the right.
const CX = 74;
const CY = 68;
const R = 54;
const GAP_DEG = 5;
const SWEEP = (180 - GAP_DEG * (BANDS.length - 1)) / BANDS.length;
const STEP = SWEEP + GAP_DEG;

function polar(angleDeg: number, radius: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: CX + radius * Math.cos(rad), y: CY - radius * Math.sin(rad) };
}

/** One arc segment, drawn clockwise from its start angle. */
function arc(index: number, radius: number) {
  const start = 180 - index * STEP;
  const end = start - SWEEP;
  const a = polar(start, radius);
  const b = polar(end, radius);
  return `M ${a.x.toFixed(2)} ${a.y.toFixed(2)} A ${radius} ${radius} 0 0 1 ${b.x.toFixed(2)} ${b.y.toFixed(2)}`;
}

/** The middle of a band — where the needle rests. */
function bandCentre(index: number) {
  return 180 - index * STEP - SWEEP / 2;
}

function devMode(): boolean {
  try {
    if (localStorage.getItem("ipsakti.dev") === "1") return true;
  } catch {
    /* private windows throw; the flag is a convenience, never a requirement */
  }
  return Boolean(import.meta.env?.DEV);
}

export function Confidence({ level, label, score, reasons }: Props) {
  const [open, setOpen] = useState(false);
  // The needle swings up from rest rather than appearing in place, so the gauge
  // reads as a measurement being taken rather than a badge that was always
  // there. One animation frame's delay is enough to make the transition run.
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setSettled(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  const reached = BANDS.indexOf(level);
  const isLimited = level === "limited";
  const tone = isLimited ? "var(--clay)" : "var(--neem)";
  // At rest the needle sits at the far left; settled, it points at the middle
  // of the band actually reached.
  const angle = settled ? bandCentre(reached) : 180;

  return (
    <section className="support" aria-label={`Evidence support: ${label}`}>
      <div className="support-gauge">
        <svg viewBox="0 0 148 92" className="support-dial" role="img" aria-hidden>
          {/* Engraved ground: every band drawn faint, so the unreached ones are
              still legible as part of the scale. */}
          {BANDS.map((band, i) => (
            <path
              key={`bg-${band}`}
              d={arc(i, R)}
              fill="none"
              stroke="var(--paper-deep)"
              strokeWidth="9"
              strokeLinecap="butt"
            />
          ))}
          {/* Reached bands, filled in order. */}
          {BANDS.map((band, i) =>
            i <= reached ? (
              <path
                key={`on-${band}`}
                d={arc(i, R)}
                fill="none"
                stroke={tone}
                strokeWidth="9"
                strokeLinecap="butt"
                style={{
                  opacity: settled ? 1 : 0,
                  transition: `opacity 260ms ease-out ${i * 90}ms`,
                }}
              />
            ) : null,
          )}

          {/* Tick marks between bands — the engraving that makes this read as
              an instrument rather than a progress bar. */}
          {BANDS.map((band, i) => {
            const a = polar(180 - i * STEP - SWEEP / 2, R + 9);
            return (
              <circle
                key={`tick-${band}`}
                cx={a.x}
                cy={a.y}
                r={i === reached ? 1.9 : 1.1}
                fill={i === reached ? tone : "var(--rule)"}
              />
            );
          })}

          {/* Needle. Drawn pointing left at 180°, then rotated clockwise into
              place, so the transform is a single rotation about the pivot. */}
          <g
            style={{
              transformOrigin: `${CX}px ${CY}px`,
              transform: `rotate(${180 - angle}deg)`,
              transition: "transform 760ms cubic-bezier(0.22, 1, 0.36, 1)",
            }}
          >
            <line
              x1={CX}
              y1={CY}
              x2={CX - (R - 13)}
              y2={CY}
              stroke="var(--ink)"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </g>
          <circle cx={CX} cy={CY} r="4.5" fill="#fffdf8" stroke="var(--ink)" strokeWidth="1.4" />
          <circle cx={CX} cy={CY} r="1.4" fill="var(--ink)" />
        </svg>

        <div className="support-readout">
          <p className="eyebrow text-ink-faint">Evidence support</p>
          <p className={`support-label ${isLimited ? "is-thin" : ""}`}>{label}</p>
          <p className="support-scale" aria-hidden>
            {BANDS.map((band, i) => (
              <span key={band} className={i === reached ? "is-current" : ""}>
                {TICK[band]}
              </span>
            ))}
          </p>
        </div>
      </div>

      <p className="support-caption">
        Reflects how well the cited sources support this specific answer — not a judgment
        of legal certainty or outcome.
        {devMode() && score !== null && (
          <span className="ref ml-1.5 text-ink-faint">[dev {score.toFixed(2)}]</span>
        )}
      </p>

      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="support-why">
        {open ? "Hide how this was measured" : "How was this measured?"}
      </button>

      <div className="reveal" data-open={open} aria-hidden={!open}>
        <div>
          <ul className="support-reasons">
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
            <li className="is-note">
              Scored from the citations that survived validation — not from search
              similarity, which was measured on this corpus and does not separate
              in-scope questions from out-of-scope ones. It is an ordinal scale and has
              not been calibrated against known-correct answers.
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
