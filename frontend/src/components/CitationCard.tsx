import { useEffect, useState } from "react";
import type { Citation } from "../types";
import { citationLabel } from "../types";
import { CheckIcon, CopyIcon, SealIcon } from "./Icons";

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
  const [copied, setCopied] = useState(false);

  // Reset the confirmation so the tick does not sit there permanently.
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copyCitation() {
    // Copy the human-readable reference, not the chunk id: the point is to
    // paste "Patents Act 1970, Section 3(p), p. 11" into a document, and an
    // internal identifier is meaningless outside this app.
    try {
      await navigator.clipboard.writeText(citationLabel(citation));
      setCopied(true);
    } catch {
      // Clipboard access can be refused (insecure origin, permissions policy).
      // Failing quietly is right — nothing is lost, the text is still on screen.
    }
  }

  return (
    <li
      onMouseEnter={() => onHover(citation.chunk_id)}
      onMouseLeave={() => onHover(null)}
      className={`card lift group p-3 ${
        highlighted ? "border-indigo-dye bg-indigo-wash" : "hover:border-indigo-dye/45"
      }`}
    >
      <div className="flex gap-2.5">
        <span className="ref mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-[2px] bg-indigo-dye text-[11px] font-medium text-paper">
          {index}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="font-serif text-[13.5px] font-medium leading-snug text-ink">
              {citation.act_name}
            </p>
            {/* Appears on hover or keyboard focus; always reachable by tab, so
                it is not a mouse-only affordance. */}
            <button
              onClick={copyCitation}
              title="Copy this citation"
              aria-label={copied ? "Citation copied" : `Copy citation: ${citationLabel(citation)}`}
              className="h-4 w-4 shrink-0 text-ink-faint opacity-0 transition-opacity duration-150 hover:text-indigo-dye focus-visible:focus-ring focus-visible:opacity-100 group-hover:opacity-100"
            >
              {copied ? <CheckIcon /> : <CopyIcon />}
            </button>
          </div>

          <p className="ref mt-1 flex items-center gap-1 text-indigo-dye">
            {/* The seal marks a provision we verified is present in the chunk
                text. Where none could be verified we say so plainly instead —
                under-citing is safe, mis-citing is not. */}
            {citation.section ? (
              <>
                <span className="h-3 w-3 shrink-0 text-neem" title="Provision verified in the source text">
                  <SealIcon />
                </span>
                {citation.section}
              </>
            ) : (
              <span className="text-ink-faint">provision not identified</span>
            )}
            {citation.page ? <span className="text-ink-faint"> · p. {citation.page}</span> : null}
          </p>

          <button
            onClick={() => setOpen((v) => !v)}
            className="eyebrow mt-2 transition-colors hover:text-indigo-dye focus-visible:focus-ring"
            aria-expanded={open}
          >
            {open ? "Hide source text" : "Read source text"}
          </button>

          <div className="reveal" data-open={open} aria-hidden={!open}>
            <div>
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
            </div>
          </div>
        </div>
      </div>

      <span className="sr-only">{citationLabel(citation)}</span>
    </li>
  );
}
