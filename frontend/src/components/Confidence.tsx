import { useId, useState } from "react";
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

// Gauge geometry. A half turn, 180° on the left to 0° on the right.
function devMode(): boolean {
  try {
    if (localStorage.getItem("ipsakti.dev") === "1") return true;
  } catch {
    /* private windows throw; the flag is a convenience, never a requirement */
  }
  return Boolean(import.meta.env?.DEV);
}



/* The logo's leaf, at readout size. Same two mirrored curves meeting at a
   point, so the mark on an answer and the mark in the header are one shape. */
const LEAF = "M20 4 C7 19 7 34 20 48 C33 34 33 19 20 4 Z";
/* The leaf's own extent inside the 52-unit box - levels are measured
   against this, not the box, so a full leaf is full to its tip. */
const TOP = 4;
const SPAN = 44;

export function Confidence({ level, label, score, reasons }: Props) {
  const [open, setOpen] = useState(false);
  // The needle used to swing to its band on the first frame; there is no
  // needle, so there is nothing to settle.
  const reached = BANDS.indexOf(level);
  const isLimited = level === "limited";
  /* Four bands, four levels - but the levels are spaced by AREA, not by height.

     A leaf is pointed at both ends, so its width varies down its length: the
     top quarter of the box is a narrow tip carrying almost no area. Filling to
     three quarters of the HEIGHT therefore covered about nine tenths of the
     visible leaf, and a "well supported" reading looked indistinguishable from
     a full one - the mark was lying about its own value.

     Treating the leaf as a symmetric taper (width proportional to the distance
     from the nearer point), the area below height h is 2h^2 up to the midpoint
     and its mirror above. Solving that for the quarter marks gives 0.354 and
     0.646 either side of the middle, which is what these numbers are.

     Still a function of the BAND, not of the raw score: the score is
     uncalibrated, and a leaf filled to 61% would claim a resolution the
     measurement does not have. */
  const LEVELS = [0.354, 0.5, 0.646, 1];
  const fill = LEVELS[reached] ?? LEVELS[0];
  /* Several answers share a page, so each clip path needs its own id or the
     first leaf on the page captures every later reference to it. */
  const uid = useId().replace(/:/g, "");


  return (
    <section className="support" aria-label={`Evidence support: ${label}`}>
      {/* A LEAF THAT FILLS.

          Three earlier attempts all failed the same way. A needle on a gauge
          face, a four-step bar, and a quartered seal with the band number in it
          were each borrowing the language of measurement - and the last one put
          a figure on the page ("3 of 4") that invites exactly the arithmetic
          this score cannot support. There is no denominator worth showing when
          the scale is ordinal and uncalibrated.

          So: the mark this product is already built around, filled from the
          stem to one of four heights. It carries no number, it cannot be read
          as a percentage, and it is the one shape on the page that belongs to
          nothing else. How full it is says how far the evidence reached; the
          words beside it say the rest. */}
      <div className="support-mark">
        <svg
          viewBox="0 0 40 52"
          className={`support-leaf ${isLimited ? "is-thin" : ""}`}
          aria-hidden
        >
          <defs>
            <clipPath id={`fill-${uid}`}>
              {/* Fills from the base upward, so a fuller leaf is more support
                  the way a filled vessel is more of something. */}
              <rect x="0" y={TOP + (1 - fill) * SPAN} width="40" height={fill * SPAN + 4} />
            </clipPath>
            <clipPath id={`leaf-${uid}`}>
              <path d={LEAF} />
            </clipPath>
          </defs>
          {/* The empty part is tinted rather than left blank, so the whole
              leaf is legible as a leaf and the fill reads as a level inside a
              known shape - not as a shard floating on the page. */}
          <path className="support-leaf-well" d={LEAF} />
          <path className="support-leaf-body" d={LEAF} clipPath={`url(#fill-${uid})`} />
          {/* A rule at the level, clipped to the leaf. The boundary between
              tint and solid is legible on paper but thin on the dark surface;
              a line makes "how full" readable at a glance on both. */}
          <line
            className="support-leaf-level"
            x1="0"
            x2="40"
            y1={TOP + (1 - fill) * SPAN}
            y2={TOP + (1 - fill) * SPAN}
            clipPath={`url(#leaf-${uid})`}
          />
          <path className="support-leaf-rib" d="M20 9 V45" clipPath={`url(#leaf-${uid})`} />
          <path className="support-leaf-edge" d={LEAF} />
        </svg>

        <div className="min-w-0">
          <p className="support-head">Evidence support</p>
          <p className={`support-label ${isLimited ? "is-thin" : ""}`}>{label}</p>
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
