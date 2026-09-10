import { useState } from "react";
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
  // The needle used to swing to its band on the first frame; there is no
  // needle, so there is nothing to settle.
  const reached = BANDS.indexOf(level);
  const isLimited = level === "limited";


  return (
    <section className="support" aria-label={`Evidence support: ${label}`}>
      {/* A SEAL, not a meter.

          Two earlier attempts were both instruments: a needle on a gauge face,
          then a four-step bar. Both borrowed the visual language of continuous
          measurement for something that is four ordinal bands over an
          uncalibrated score, and both looked like a widget bolted to a legal
          document.

          This page already has a seal: the little mark on a citation card that
          says the provision was found in the source text. Authentication is the
          gesture this product is actually making, so the support reading is a
          seal too - one ring, quartered, filled as far as the evidence reaches.
          It reads as a stamp on a document rather than a dial on a dashboard,
          and it cannot be mistaken for a percentage. */}
      <div className="support-mark">
        <svg viewBox="0 0 44 44" className={`support-seal ${isLimited ? "is-thin" : ""}`} aria-hidden>
          {/* Four arcs of 90deg less a gap, drawn from the top clockwise, so
              "more filled" reads the way a clock does. */}
          {BANDS.map((band, i) => {
            const R = 18;
            const C = 2 * Math.PI * R;
            const seg = C / 4;
            return (
              <circle
                key={band}
                cx="22"
                cy="22"
                r={R}
                fill="none"
                strokeWidth="3.5"
                strokeLinecap="butt"
                className={i <= reached ? "is-lit" : "is-track"}
                strokeDasharray={`${seg - 4} ${C - seg + 4}`}
                strokeDashoffset={-i * seg}
                transform="rotate(-90 22 22)"
              />
            );
          })}
          {/* The centre carries the count reached, not a number out of ten -
              four bands, and you are on the nth. */}
          <text x="22" y="22" className="support-seal-n">
            {reached + 1}
          </text>
        </svg>

        <div className="min-w-0">
          <p className="support-head">Evidence support</p>
          <p className={`support-label ${isLimited ? "is-thin" : ""}`}>{label}</p>
          <p className="support-of">{TICK[BANDS[reached]]} · {reached + 1} of 4</p>
        </div>
      </div>

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
