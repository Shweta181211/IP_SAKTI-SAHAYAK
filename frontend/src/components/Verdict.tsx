import type { AbstentionKind, ClassificationResult } from "../types";

/**
 * The classification verdict — the one place haldi/turmeric is used, because
 * it is the single most consequential fact in the answer: a classical
 * formulation and a new drug have opposite patent positions.
 */
export function Verdict({ classification }: { classification: ClassificationResult }) {
  const isCategory =
    classification.category !== "not_applicable" &&
    classification.category !== "needs_clarification";

  return (
    <div className="border-l-[3px] border-haldi bg-haldi-wash px-4 py-3">
      <p className="eyebrow text-haldi">
        {isCategory ? "Classified as" : "Question type"}
      </p>
      <p className="mt-0.5 font-serif text-[17px] font-medium leading-snug text-ink">
        {classification.label}
      </p>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-soft">
        {classification.rationale}
      </p>
      {classification.defining_source_name && (
        <p className="ref mt-2 text-ink-faint">
          Defined by {classification.defining_source_name}
        </p>
      )}
    </div>
  );
}

const ABSTENTION_HEADING: Record<AbstentionKind, string> = {
  none: "One more detail needed",
  no_evidence: "No grounded answer available",
  too_vague: "Need a little more to go on",
  foreign_jurisdiction: "Outside this jurisdiction",
  out_of_scope: "Outside this corpus",
  gate_unavailable: "Safety check unavailable",
  // Never rendered through this panel — small talk has its own plain layout.
  conversational: "",
};

/**
 * Abstention is a graded requirement of the problem statement, not an error.
 * It gets a designed panel, never a red toast — the system declining to invent
 * an answer is the product working, and should look like it.
 */
export function AbstentionPanel({
  kind,
  message,
  clarifying,
}: {
  kind: AbstentionKind;
  message: string | null;
  clarifying: string | null;
}) {
  return (
    <div className="card border-clay/40 bg-clay-wash p-5">
      <p className="eyebrow text-clay">{ABSTENTION_HEADING[kind] ?? "Not answered"}</p>
      <p className="prose-legal mt-1.5 text-ink">{message}</p>

      {clarifying && (
        <div className="mt-3 border-t border-clay/25 pt-3">
          <p className="eyebrow text-clay">To continue, tell me</p>
          <p className="prose-legal mt-1 text-ink">{clarifying}</p>
        </div>
      )}

      <p className="mt-3 text-[12px] leading-relaxed text-ink-faint">
        Nothing was generated for this question. The assistant answers only from cited
        sources in its corpus, and says so when it cannot.
      </p>
    </div>
  );
}
