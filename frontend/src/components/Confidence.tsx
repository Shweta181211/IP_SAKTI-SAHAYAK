import { useEffect, useId, useState } from "react";
import type { ConfidenceLevel } from "../types";

interface Props {
  level: ConfidenceLevel;
  label: string;
  score: number | null;
  reasons: string[];
}

/**
 * How well the cited sources support this answer, as a dimensional gauge.
 *
 * Four constraints, three of them substantive:
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
 * **The needle rests on a band, not on a value.** Four arc segments, and the
 * needle points at the middle of the band reached — never between two, because
 * the underlying score is ordinal and uncalibrated, and a needle at an
 * arbitrary angle would imply a resolution this measurement does not have.
 *
 * **No card around it.** The white panel made a measuring instrument look like
 * a form field. The gauge now sits directly on the sheet and carries itself
 * through depth — a recessed track, a lit arc, and a needle with a real
 * shadow — so it reads as an instrument set into the page.
 */

const BANDS: ConfidenceLevel[] = ["limited", "moderate", "high", "strong"];
const TICK: Record<ConfidenceLevel, string> = {
  limited: "Thin",
  moderate: "Some",
  high: "Well",
  strong: "Strong",
};

// Gauge geometry. A half turn, 180° on the left to 0° on the right.
const CX = 78;
const CY = 74;
const R = 58;
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

const bandCentre = (index: number) => 180 - index * STEP - SWEEP / 2;

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
  // Several answers share a page, so the gradient/filter ids must be unique or
  // the first gauge on the page captures every later reference to them.
  const uid = useId().replace(/:/g, "");
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setSettled(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  const reached = BANDS.indexOf(level);
  const isLimited = level === "limited";
  const angle = settled ? bandCentre(reached) : 180;

  const lit = isLimited ? `#c0553d` : `#5f9270`;
  const litDeep = isLimited ? `#8d3324` : `#3d6547`;

  return (
    <section className="support" aria-label={`Evidence support: ${label}`}>
      <div className="support-gauge">
        <svg viewBox="0 0 156 100" className="support-dial" role="img" aria-hidden>
          <defs>
            {/* Lit from the upper left, so every arc shares one light source
                and the dial reads as a solid object rather than flat strokes. */}
            <linearGradient id={`lit-${uid}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={lit} />
              <stop offset="100%" stopColor={litDeep} />
            </linearGradient>
            <linearGradient id={`track-${uid}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d8caa8" />
              <stop offset="100%" stopColor="#efe6cd" />
            </linearGradient>
            <linearGradient id={`needle-${uid}`} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#3d5147" />
              <stop offset="100%" stopColor="#16241e" />
            </linearGradient>
            <radialGradient id={`hub-${uid}`} cx="35%" cy="30%" r="75%">
              <stop offset="0%" stopColor="#fffdf8" />
              <stop offset="100%" stopColor="#cdbf9d" />
            </radialGradient>
            <filter id={`cast-${uid}`} x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="1.6" stdDeviation="1.6" floodColor="#16241e" floodOpacity="0.28" />
            </filter>
            <filter id={`glow-${uid}`} x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="0" stdDeviation="2.6" floodColor={lit} floodOpacity="0.45" />
            </filter>
          </defs>

          {/* Recessed channel: a dark rim under the track is what makes the
              groove look cut into the sheet rather than drawn on it. */}
          {BANDS.map((band, i) => (
            <path
              key={`groove-${band}`}
              d={arc(i, R)}
              fill="none"
              stroke="#b9a882"
              strokeOpacity="0.55"
              strokeWidth="13"
              strokeLinecap="round"
            />
          ))}
          {BANDS.map((band, i) => (
            <path
              key={`track-${band}`}
              d={arc(i, R)}
              fill="none"
              stroke={`url(#track-${uid})`}
              strokeWidth="10.5"
              strokeLinecap="round"
            />
          ))}

          {/* Reached bands, lit in order. */}
          {BANDS.map((band, i) =>
            i <= reached ? (
              <path
                key={`on-${band}`}
                d={arc(i, R)}
                fill="none"
                stroke={`url(#lit-${uid})`}
                strokeWidth="10.5"
                strokeLinecap="round"
                filter={`url(#glow-${uid})`}
                style={{
                  opacity: settled ? 1 : 0,
                  transition: `opacity 300ms ease-out ${i * 95}ms`,
                }}
              />
            ) : null,
          )}
          {/* Specular highlight along the top of the lit arcs. */}
          {BANDS.map((band, i) =>
            i <= reached ? (
              <path
                key={`gloss-${band}`}
                d={arc(i, R + 2.6)}
                fill="none"
                stroke="#ffffff"
                strokeOpacity={settled ? 0.3 : 0}
                strokeWidth="2"
                strokeLinecap="round"
                style={{ transition: `stroke-opacity 300ms ease-out ${i * 95 + 120}ms` }}
              />
            ) : null,
          )}

          {/* Engraved band marks. */}
          {BANDS.map((band, i) => {
            const a = polar(bandCentre(i), R + 11);
            return (
              <circle
                key={`tick-${band}`}
                cx={a.x}
                cy={a.y}
                r={i === reached ? 2.1 : 1.2}
                fill={i === reached ? lit : "#c3b291"}
              />
            );
          })}

          {/* Needle. Drawn pointing left at 180°, then rotated clockwise into
              place, so the whole motion is one rotation about the hub. */}
          <g
            filter={`url(#cast-${uid})`}
            style={{
              transformOrigin: `${CX}px ${CY}px`,
              transform: `rotate(${180 - angle}deg)`,
              transition: "transform 820ms cubic-bezier(0.22, 1, 0.36, 1)",
            }}
          >
            <path
              d={`M ${CX - (R - 12)} ${CY} L ${CX + 4} ${CY - 3.1} L ${CX + 4} ${CY + 3.1} Z`}
              fill={`url(#needle-${uid})`}
            />
          </g>
          <circle cx={CX} cy={CY} r="6.4" fill={`url(#hub-${uid})`} filter={`url(#cast-${uid})`} />
          <circle cx={CX} cy={CY} r="6.4" fill="none" stroke="#16241e" strokeOpacity="0.5" strokeWidth="1" />
          <circle cx={CX} cy={CY} r="1.7" fill="#16241e" />
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
          <p className="support-caption">
            How well the cited sources support this answer — not a judgment of legal
            certainty or outcome.
            {devMode() && score !== null && (
              <span className="ref ml-1.5 text-ink-faint">[dev {score.toFixed(2)}]</span>
            )}
          </p>
          <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="support-why">
            {open ? "Hide how this was measured" : "How was this measured?"}
          </button>
        </div>
      </div>

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
