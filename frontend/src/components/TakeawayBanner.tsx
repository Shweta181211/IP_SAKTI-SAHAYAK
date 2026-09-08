import type { Citation, Takeaway, TakeawayIntent } from "../types";

/**
 * The one-line orientation above the reasoning trail.
 *
 * Two decisions worth defending:
 *
 * **It is deliberately not haldi, not neem, not clay.** Each hue in this
 * palette means exactly one thing — haldi is the classification verdict, neem
 * is "verified", clay is "we declined". A takeaway is none of those: it is a
 * preliminary orientation that always needs checking, and dressing it in a
 * colour that already means "verified" would assert exactly what the hedged
 * vocabulary is written to avoid. So it sits in ink on the deep paper ground,
 * with an intent glyph carrying the recognition instead of a colour.
 *
 * **The caveat is inside the banner, not at the foot of the page.** A reader
 * who acts on one line of this page will act on this one, so the sentence that
 * says it is not a legal conclusion has to be within it.
 */

const INTENT_LABEL: Record<TakeawayIntent, string> = {
  patent: "Patent / protection",
  gi: "Geographical indication",
  abs: "Access & benefit sharing",
  tkdl: "Prior art",
  other: "Preliminary orientation",
};

function IntentGlyph({ intent }: { intent: TakeawayIntent }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "h-full w-full",
  };
  switch (intent) {
    case "patent":
      // A sealed grant.
      return (
        <svg {...common}>
          <path d="M12 3l7 3.5v5c0 4-3 7.2-7 8.5-4-1.3-7-4.5-7-8.5v-5L12 3z" />
          <path d="M9.4 11.8l1.9 1.9 3.5-3.6" />
        </svg>
      );
    case "gi":
      // Place — origin is the whole point of a GI.
      return (
        <svg {...common}>
          <path d="M12 21s6.5-5.4 6.5-10a6.5 6.5 0 1 0-13 0C5.5 15.6 12 21 12 21z" />
          <circle cx="12" cy="11" r="2.3" />
        </svg>
      );
    case "abs":
      // Sharing between two parties.
      return (
        <svg {...common}>
          <circle cx="7" cy="8" r="2.6" />
          <circle cx="17" cy="16" r="2.6" />
          <path d="M9.3 9.6l5.4 4.8" />
          <path d="M17 5.5V11M14.2 8.2h5.6" />
        </svg>
      );
    case "tkdl":
      // A record already on the shelf — what prior art is.
      return (
        <svg {...common}>
          <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10v16H5.5A1.5 1.5 0 0 1 4 18.5v-13z" />
          <path d="M10 4h8.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H10" />
          <path d="M13 9h4M13 13h4" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 11v5M12 8h.01" />
        </svg>
      );
  }
}

export function TakeawayBanner({
  takeaway,
  citationIndex,
  onJumpToCitation,
  onHover,
}: {
  takeaway: Takeaway;
  citationIndex: Map<string, number>;
  citationById?: Map<string, Citation>;
  onJumpToCitation?: (chunkId: string) => void;
  onHover?: (ids: string[] | null) => void;
}) {
  return (
    <section
      className="takeaway"
      aria-label="Preliminary takeaway"
      onMouseEnter={() => onHover?.(takeaway.citation_ids)}
      onMouseLeave={() => onHover?.(null)}
    >
      <span className="takeaway-glyph" aria-hidden>
        <IntentGlyph intent={takeaway.intent} />
      </span>

      <div className="min-w-0 flex-1">
        <p className="eyebrow text-ink-faint">{INTENT_LABEL[takeaway.intent]}</p>

        {/* The label is drawn from a closed, always-hedged vocabulary that the
            backend validates — a bare "yes, patentable" cannot reach here. */}
        <p className="takeaway-label">{takeaway.label}</p>

        <p className="mt-1 max-w-[62ch] text-[14px] leading-relaxed text-ink-soft">
          {takeaway.reason}
        </p>

        <p className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1.5">
          {takeaway.citation_ids.length > 0 ? (
            <>
              <span className="eyebrow">Based on</span>
              {takeaway.citation_ids.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => onJumpToCitation?.(id)}
                  onMouseEnter={() => onHover?.([id])}
                  title="Show this source"
                  className="ref trail-chip rounded-[2px] bg-indigo-wash px-1.5 py-0.5 text-indigo-dye"
                >
                  {citationIndex.get(id) ?? "?"}
                </button>
              ))}
            </>
          ) : (
            <span className="eyebrow text-ink-faint">
              Orientation only — the cited findings are in the steps below
            </span>
          )}
        </p>
      </div>

      {/* Not a footnote. Someone who reads one line of this page reads this one. */}
      <p className="takeaway-caveat">
        Preliminary orientation from a source search — not a legal conclusion, and not advice.
        Read the reasoning and the cited provisions below before acting.
      </p>
    </section>
  );
}
