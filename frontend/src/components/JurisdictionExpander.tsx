import type { Answer, JurisdictionComparison } from "../types";
import { AnswerView } from "./AnswerView";
import { JurisdictionPoints } from "./JurisdictionCompareView";

/**
 * Reveal the other jurisdiction for a question already answered, then compare.
 *
 * Progressive on purpose, for two reasons that happen to agree:
 *
 *  - Cost. The question is answered once, in whichever jurisdiction the toggle
 *    is set to. Revealing the other side is a second call, and comparing them a
 *    third that REUSES both rather than regenerating. Nobody pays for a side
 *    they did not ask to see — a comparison used to cost nine calls up front.
 *
 *  - Reading. The problem statement wants the two answer-sets visibly separate.
 *    Arriving one at a time, each under its own heading and accent, separates
 *    them more firmly than two columns that appear together and invite being
 *    skimmed as one thing. The comparison appears only once the reader has both
 *    in front of them, and it never replaces either.
 *
 * Works from either toggle position: "the other side" is whichever jurisdiction
 * the answer was not given in.
 */
export function JurisdictionExpander({
  primary,
  other,
  otherAnswer,
  comparison,
  loadingOther,
  loadingComparison,
  onReveal,
  onCompare,
  labels,
}: {
  /** The jurisdiction the answer above was given in. */
  primary: "national" | "international";
  other: "national" | "international";
  otherAnswer?: Answer;
  comparison?: JurisdictionComparison;
  loadingOther: boolean;
  loadingComparison: boolean;
  onReveal: () => void;
  onCompare: () => void;
  labels: {
    india: string;
    international: string;
    reveal: string;
    revealing: string;
    compare: string;
    comparing: string;
    comparisonHeading: string;
    silent: string;
    guard: string;
    unavailable: string;
  };
}) {
  const otherLabel = other === "international" ? labels.international : labels.india;
  const otherIsInternational = other === "international";
  const accent = otherIsInternational
    ? "border-indigo-dye text-indigo-dye"
    : "border-haldi text-haldi";

  return (
    <div className="mt-4">
      {!otherAnswer && !loadingOther && (
        <button
          type="button"
          onClick={onReveal}
          className={`rounded-[3px] border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] transition-colors focus-visible:focus-ring ${
            otherIsInternational
              ? "border-indigo-dye/40 text-indigo-dye hover:border-indigo-dye"
              : "border-haldi/40 text-haldi hover:border-haldi"
          }`}
        >
          {labels.reveal.replace("{side}", otherLabel)}
        </button>
      )}

      {loadingOther && (
        <p className="text-[12px] italic text-ink-faint">
          {labels.revealing.replace("{side}", otherLabel)}
        </p>
      )}

      {otherAnswer && (
        <section className="mt-2">
          {/* Its own heading and accent: a reader should never have to work out
              which legal system a paragraph belongs to. */}
          <div className={`mb-3 flex items-baseline justify-between border-b-2 pb-1.5 ${accent}`}>
            <h3 className="font-serif text-[15px] font-medium">{otherLabel}</h3>
            <span className="eyebrow text-ink-faint">
              {otherAnswer.citations.length}{" "}
              {otherAnswer.citations.length === 1 ? "source" : "sources"}
            </span>
          </div>
          <AnswerView answer={otherAnswer} />

          {!comparison && !loadingComparison && (
            <button
              type="button"
              onClick={onCompare}
              className="mt-4 rounded-[3px] border border-rule px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-faint transition-colors hover:border-haldi hover:bg-haldi-wash hover:text-haldi focus-visible:focus-ring"
            >
              {labels.compare}
            </button>
          )}
          {loadingComparison && (
            <p className="mt-4 text-[12px] italic text-ink-faint">{labels.comparing}</p>
          )}
        </section>
      )}

      {comparison && (
        <section className="mt-6 border-t border-rule pt-4">
          <h3 className="mb-3 font-serif text-[15px] font-medium text-ink">
            {labels.comparisonHeading}
          </h3>
          {/* Same renderer as the side-by-side view: one place a claim can
              appear, one place to keep it attributed. */}
          <JurisdictionPoints
            comparison={comparison}
            labels={{
              national: labels.india,
              international: labels.international,
              silent: labels.silent,
              guard: labels.guard,
              unavailable: labels.unavailable,
            }}
          />
        </section>
      )}

      {/* `primary` is not rendered — it is here so the caller must say which
          side the answer above came from, which is what makes `other` correct
          when the toggle is set to International. */}
      <span hidden data-primary={primary} />
    </div>
  );
}
