import { useMemo } from "react";
import type { ComparisonResult } from "../types";
import { CitationCard } from "./CitationCard";
import { buildCitationIndex } from "./ReasoningTrail";

/**
 * The same product, four regulatory categories, four different answers.
 *
 * This is the problem statement's central claim made visible: a classical
 * formulation faces the Section 3(p) bar, while a phytopharmaceutical or new
 * drug has genuine patent potential on a different evidentiary pathway. Told
 * one category at a time it is an assertion; side by side it is obvious.
 */
export function ComparisonView({ result }: { result: ComparisonResult }) {
  const citationIndex = useMemo(
    () => buildCitationIndex(result.citations),
    [result.citations],
  );

  if (result.abstained) {
    return (
      <div className="card border-clay/40 bg-clay-wash p-5">
        <p className="eyebrow text-clay">Cannot compare this yet</p>
        <p className="prose-legal mt-1.5">{result.abstention_message}</p>
      </div>
    );
  }

  return (
    <div>
      <p className="mb-4 border-l-2 border-haldi pl-3">
        <span className="eyebrow block">Comparing across categories</span>
        <span className="font-serif text-[15px] italic text-ink-soft">{result.product}</span>
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        {result.contrasts.map((c) => {
          const unsupported = c.citation_ids.length === 0;
          return (
            <div
              key={c.category}
              className={`card flex flex-col p-4 ${unsupported ? "opacity-70" : ""}`}
            >
              <h3 className="font-serif text-[15px] font-medium leading-snug text-ink">
                {c.label}
              </h3>

              {/* The verdict is the thing being compared, so it leads. */}
              <p
                className={`mt-2 border-l-[3px] pl-2.5 text-[13px] font-medium leading-snug ${
                  unsupported
                    ? "border-rule text-ink-faint"
                    : "border-haldi text-ink"
                }`}
              >
                {c.patentable}
              </p>

              <p className="prose-legal mt-3 flex-1 text-[14px]">{c.posture}</p>

              {c.citation_ids.length > 0 ? (
                <p className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-rule pt-2">
                  <span className="eyebrow">Sources</span>
                  {c.citation_ids.map((id) => (
                    <span
                      key={id}
                      className="ref rounded-[2px] bg-indigo-wash px-1.5 py-0.5 text-indigo-dye"
                    >
                      {citationIndex.get(id) ?? "?"}
                    </span>
                  ))}
                </p>
              ) : (
                <p className="eyebrow mt-3 border-t border-rule pt-2 text-clay">
                  Not supported by the corpus
                </p>
              )}
            </div>
          );
        })}
      </div>

      {result.citations.length > 0 && (
        <div className="mt-5">
          <h3 className="eyebrow mb-2">Sources cited</h3>
          <ul className="grid gap-2 sm:grid-cols-2">
            {result.citations.map((c, i) => (
              <CitationCard
                key={c.chunk_id}
                citation={c}
                index={i + 1}
                highlighted={false}
                onHover={() => {}}
              />
            ))}
          </ul>
        </div>
      )}

      <p className="mt-6 border-t border-rule pt-3 text-[12px] leading-relaxed text-ink-faint">
        {result.disclaimer}
      </p>
    </div>
  );
}
