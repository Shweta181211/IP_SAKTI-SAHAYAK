import { useState } from "react";
import type { Answer, JurisdictionComparison, JurisdictionPoint } from "../types";
import { AnswerView } from "./AnswerView";

/**
 * The Indian position and the international one, side by side.
 *
 * The layout is part of the safeguard, not decoration. The problem statement
 * requires the two answer-sets to be "visibly separate" and "never conflated",
 * so:
 *
 *   - each side sits in its own column under its own heading, with its own
 *     citations, and is the complete answer rather than a summary of one;
 *   - the two columns carry different accent colours, so which corpus a claim
 *     came from is legible before anything is read;
 *   - every comparison point states each side's position in its own labelled
 *     row. There is no place in this component where a sentence about "the law"
 *     can appear without a jurisdiction attached to it.
 *
 * On narrow screens the columns stack rather than merging, and each keeps its
 * heading — a single scrolling column of unlabelled prose is exactly the
 * failure this design exists to prevent.
 */

function SideHeading({
  label,
  sources,
  tone,
}: {
  label: string;
  sources: number;
  tone: "india" | "international";
}) {
  const accent = tone === "india" ? "border-haldi text-haldi" : "border-indigo-dye text-indigo-dye";
  return (
    <div className={`mb-3 flex items-baseline justify-between border-b-2 pb-1.5 ${accent}`}>
      <h3 className="font-serif text-[length:var(--t-body)] font-medium">{label}</h3>
      <span className="eyebrow text-ink-faint">
        {sources} {sources === 1 ? "source" : "sources"}
      </span>
    </div>
  );
}

function PointRow({
  point,
  labels,
}: {
  point: JurisdictionPoint;
  labels: { national: string; international: string; silent: string };
}) {
  const isDifference = point.kind === "difference";
  return (
    <li className="border-l-2 border-rule py-2.5 pl-3">
      <div className="mb-1.5 flex items-baseline gap-2">
        <span
          className={`eyebrow ${isDifference ? "text-clay" : "text-neem"}`}
        >
          {isDifference ? "Difference" : "Similarity"}
        </span>
        <span className="text-[length:var(--t-meta)] leading-snug text-ink">{point.summary}</span>
      </div>

      {/* Each side on its own labelled row. A claim can never appear here
          without the jurisdiction that owns it. */}
      <dl className="mt-1 space-y-1.5 text-[length:var(--t-micro)] leading-relaxed">
        <div className="grid grid-cols-[auto_1fr] gap-x-2">
          <dt className="whitespace-nowrap font-semibold text-haldi">{labels.national}</dt>
          <dd className="text-ink-soft">
            {point.national_claim ?? <span className="text-ink-faint">{labels.silent}</span>}
            {point.national_citation_ids.length > 0 && (
              <span className="ml-1 font-mono text-[10.5px] text-ink-faint">
                [{point.national_citation_ids.length}]
              </span>
            )}
          </dd>
        </div>
        <div className="grid grid-cols-[auto_1fr] gap-x-2">
          <dt className="whitespace-nowrap font-semibold text-indigo-dye">
            {labels.international}
          </dt>
          <dd className="text-ink-soft">
            {point.international_claim ?? (
              <span className="text-ink-faint">{labels.silent}</span>
            )}
            {point.international_citation_ids.length > 0 && (
              <span className="ml-1 font-mono text-[10.5px] text-ink-faint">
                [{point.international_citation_ids.length}]
              </span>
            )}
          </dd>
        </div>
      </dl>
    </li>
  );
}

/** The comparison points, plus the two guards. Shared by the side-by-side view
 *  and the progressive reveal so both render identically — one place where a
 *  claim can appear, one place to keep it attributed. */
export function JurisdictionPoints({
  comparison,
  labels,
}: {
  comparison: JurisdictionComparison;
  labels: {
    national: string;
    international: string;
    silent: string;
    guard: string;
    unavailable: string;
  };
}) {
  return (
    <>
      {comparison.points.length > 0 && (
        <ul className="space-y-1 rounded-[3px] border border-rule bg-paper-raised p-3">
          {comparison.points.map((point, i) => (
            <PointRow key={i} point={point} labels={labels} />
          ))}
        </ul>
      )}

      {comparison.synthesis_unavailable && comparison.synthesis_message && (
        <div className="mt-3 border-l-2 border-clay bg-clay-wash px-3 py-2">
          <p className="eyebrow text-clay">{labels.unavailable}</p>
          <p className="mt-1 text-[length:var(--t-micro)] leading-relaxed text-ink-soft">
            {comparison.synthesis_message}
          </p>
        </div>
      )}

      {comparison.rejected_points.length > 0 && (
        <div className="mt-3 border-l-2 border-neem bg-neem-wash px-3 py-2">
          <p className="eyebrow text-neem">{labels.guard}</p>
          <p className="mt-1 text-[length:var(--t-micro)] leading-relaxed text-ink-soft">
            {comparison.rejected_points.length}{" "}
            {comparison.rejected_points.length === 1 ? "statement was" : "statements were"}{" "}
            dropped for citing the wrong jurisdiction's sources, or none at all.
          </p>
        </div>
      )}
    </>
  );
}

export function JurisdictionCompareView({
  comparison,
  labels,
}: {
  comparison: JurisdictionComparison;
  labels: {
    national: string;
    international: string;
    comparison: string;
    silent: string;
    guard: string;
    unavailable: string;
  };
}) {
  const [showSides, setShowSides] = useState(true);
  const { national, international, points } = comparison;

  return (
    <section className="mb-10">
      <h2 className="mb-1 font-serif text-[length:var(--t-sub)] leading-snug text-ink">
        {comparison.question}
      </h2>
      <p className="mb-4 text-[length:var(--t-micro)] text-ink-faint">{labels.comparison}</p>

      {/* The comparison sits BETWEEN the two answers, never merged into either,
          and never as a substitute for reading them. */}
      {points.length > 0 && (
        <ul className="mb-6 space-y-1 rounded-[3px] border border-rule bg-paper-raised p-3">
          {points.map((point, i) => (
            <PointRow key={i} point={point} labels={labels} />
          ))}
        </ul>
      )}

      {comparison.synthesis_unavailable && comparison.synthesis_message && (
        <div className="mb-6 border-l-2 border-clay bg-clay-wash px-3 py-2">
          <p className="eyebrow text-clay">{labels.unavailable}</p>
          <p className="mt-1 text-[length:var(--t-micro)] leading-relaxed text-ink-soft">
            {comparison.synthesis_message}
          </p>
        </div>
      )}

      {comparison.rejected_points.length > 0 && (
        <div className="mb-6 border-l-2 border-neem bg-neem-wash px-3 py-2">
          <p className="eyebrow text-neem">{labels.guard}</p>
          <p className="mt-1 text-[length:var(--t-micro)] leading-relaxed text-ink-soft">
            {comparison.rejected_points.length}{" "}
            {comparison.rejected_points.length === 1 ? "statement was" : "statements were"}{" "}
            dropped for citing the wrong jurisdiction's sources, or none at all.
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={() => setShowSides((v) => !v)}
        className="mb-3 text-[length:var(--t-micro)] font-semibold uppercase tracking-[0.1em] text-ink-faint hover:text-ink"
      >
        {showSides ? "▾" : "▸"} {labels.national} / {labels.international}
      </button>

      {showSides && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <SideHeading
              label={labels.national}
              sources={national.citations.length}
              tone="india"
            />
            <AnswerView answer={national} />
          </div>
          <div>
            <SideHeading
              label={labels.international}
              sources={international.citations.length}
              tone="international"
            />
            <AnswerView answer={international} />
          </div>
        </div>
      )}

      <p className="mt-4 border-t border-rule pt-3 text-[length:var(--t-micro)] leading-relaxed text-ink-faint">
        {comparison.disclaimer}
      </p>
    </section>
  );
}

export type { Answer };
