import { useState } from "react";
import type { ConfidenceLevel } from "../types";

interface Props {
  level: ConfidenceLevel;
  label: string;
  score: number | null;
  reasons: string[];
}

// Three states, three meanings — mapped onto the palette's existing semantics
// rather than a traffic light. Neem already means "verified"; clay already
// means "limits". Reusing them keeps the colour vocabulary honest.
const STYLES: Record<ConfidenceLevel, { dot: string; text: string; bg: string }> = {
  high: { dot: "bg-neem", text: "text-neem", bg: "bg-neem-wash" },
  moderate: { dot: "bg-haldi", text: "text-haldi", bg: "bg-haldi-wash" },
  limited: { dot: "bg-clay", text: "text-clay", bg: "bg-clay-wash" },
};

/**
 * How well-supported the answer is — and, on click, exactly why.
 *
 * The reasons matter more than the badge. A confidence score you cannot
 * interrogate is just a number asking to be trusted; this one names the
 * evidence it was computed from (citations that survived validation, source
 * breadth, whether both retrievers agreed).
 */
export function Confidence({ level, label, score, reasons }: Props) {
  const [open, setOpen] = useState(false);
  const style = STYLES[level];

  return (
    <div className={`${style.bg} border-l-[3px] ${style.dot.replace("bg-", "border-")} px-3 py-2`}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left"
      >
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} aria-hidden />
        <span className={`eyebrow ${style.text}`}>{label}</span>
        {score !== null && (
          <span className="ref text-ink-faint">{Math.round(score * 100)}%</span>
        )}
        <span className="eyebrow ml-auto text-ink-faint">{open ? "hide" : "why?"}</span>
      </button>

      {open && (
        <ul className="mt-2 space-y-1 border-t border-rule/60 pt-2">
          {reasons.map((reason) => (
            <li key={reason} className="flex gap-1.5 text-[12px] leading-relaxed text-ink-soft">
              <span className="text-ink-faint" aria-hidden>·</span>
              {reason}
            </li>
          ))}
          <li className="pt-1 text-[11px] italic leading-relaxed text-ink-faint">
            Scored from citations that survived validation, not from search-similarity —
            similarity was measured on this corpus and does not separate in-scope from
            out-of-scope questions.
          </li>
        </ul>
      )}
    </div>
  );
}
