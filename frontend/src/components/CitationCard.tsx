import { useState } from "react";
import type { Citation } from "../types";
import { citationLabel } from "../types";

interface Props {
  citation: Citation;
  index: number;
  highlighted: boolean;
  onHover: (chunkId: string | null) => void;
}

/**
 * A source record, not a link card. The verbatim corpus excerpt is one click
 * away because "traceable to a source" has to be checkable by the reader, not
 * merely asserted — a judge should be able to read the statute text themselves.
 */
export function CitationCard({ citation, index, highlighted, onHover }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <li
      onMouseEnter={() => onHover(citation.chunk_id)}
      onMouseLeave={() => onHover(null)}
      className={`card p-3 transition-colors duration-150 ${
        highlighted ? "border-indigo-dye bg-indigo-wash" : "hover:border-ink-faint/50"
      }`}
    >
      <div className="flex gap-2.5">
        <span className="ref mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-[2px] bg-indigo-dye text-[11px] font-medium text-paper">
          {index}
        </span>

        <div className="min-w-0 flex-1">
          <p className="font-serif text-[13.5px] font-medium leading-snug text-ink">
            {citation.act_name}
          </p>

          <p className="ref mt-1 text-indigo-dye">
            {citation.section ?? "provision not identified"}
            {citation.page ? <span className="text-ink-faint"> · p. {citation.page}</span> : null}
          </p>

          <button
            onClick={() => setOpen((v) => !v)}
            className="eyebrow mt-2 hover:text-indigo-dye focus-visible:focus-ring"
            aria-expanded={open}
          >
            {open ? "Hide source text" : "Read source text"}
          </button>

          {open && (
            <div className="mt-2 border-l-2 border-rule pl-2.5">
              <p className="font-serif text-[12.5px] leading-relaxed text-ink-soft">
                {citation.excerpt}
              </p>
              {citation.source_file && (
                <p className="eyebrow mt-2 normal-case tracking-normal">
                  {citation.source_file} · {citation.chunk_id}
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <span className="sr-only">{citationLabel(citation)}</span>
    </li>
  );
}
