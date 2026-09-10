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
      {/* The dial is gone.

          A needle on a semicircular face is a gauge, and a gauge implies a
          continuous, calibrated reading. This measurement is neither: it is
          four ordinal bands over an uncalibrated score, which is exactly why
          the needle was already pinned to the middle of a band rather than
          allowed to rest anywhere. Drawing it as an instrument face promised a
          precision the number does not have, and it took a 156x100 block out
          of the middle of the reading column to do it.

          Four steps, the reached one filled. Same information, stated at the
          resolution it actually has, in a strip that sits beside the sources
          it is describing. */}
      <p className="support-head">Evidence support</p>
      <p className={`support-label ${isLimited ? "is-thin" : ""}`}>{label}</p>

      <ol className="support-steps" aria-hidden>
        {BANDS.map((band, i) => (
          <li
            key={band}
            className={`support-step ${i <= reached ? "is-lit" : ""} ${
              i === reached ? "is-current" : ""
            } ${isLimited ? "is-thin" : ""}`}
          >
            <span className="support-step-bar" />
            <span className="support-step-name">{TICK[band]}</span>
          </li>
        ))}
      </ol>

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
