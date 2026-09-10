import { useState } from "react";
import type { NextSteps } from "../types";

/**
 * "What this means next" — collapsible, opt-in, and visibly not a determination.
 *
 * This is the most advice-like block in the product, so it is styled as
 * guidance rather than as findings: no citation cards of its own, a lighter
 * ground than the reasoning trail, and its own disclaimer repeated on the block
 * itself rather than only at the foot of the page. A reader who acts on
 * anything here should have been told, in the same eyeful, that it is not a
 * legal determination.
 *
 * It is fetched only when asked for. Every question does not deserve one, and
 * the backend is allowed to answer "nothing to do here" — a "what is a GI tag?"
 * question is answered by its answer, and three imperatives underneath would be
 * padding that teaches people to skip the section.
 */
export function NextStepsPanel({
  data,
  loading,
  onRequest,
  labels,
}: {
  data: NextSteps | null;
  loading: boolean;
  onRequest: () => void;
  labels: {
    title: string;
    ask: string;
    thinking: string;
    none: string;
    guard: string;
    india: string;
    international: string;
  };
}) {
  const [open, setOpen] = useState(true);

  if (!data && !loading) {
    return (
      <button
        type="button"
        onClick={onRequest}
        className="mt-4 rounded-[3px] border border-rule px-3 py-1.5 text-[length:var(--t-micro)] font-semibold uppercase tracking-[0.1em] text-ink-faint transition-colors hover:border-haldi hover:bg-haldi-wash hover:text-haldi focus-visible:focus-ring"
      >
        {labels.ask}
      </button>
    );
  }

  if (loading) {
    return (
      <p className="mt-4 text-[length:var(--t-micro)] italic text-ink-faint">{labels.thinking}</p>
    );
  }

  if (!data) return null;

  return (
    <section className="mt-5 border-t border-rule pt-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-baseline gap-1.5 text-[length:var(--t-micro)] font-semibold uppercase tracking-[0.1em] text-ink-faint hover:text-ink"
      >
        <span>{open ? "▾" : "▸"}</span>
        <span>{labels.title}</span>
      </button>

      {open && (
        <div className="mt-2.5">
          {data.applicable && data.steps.length > 0 ? (
            <ol className="space-y-2">
              {data.steps.map((step, i) => (
                <li key={i} className="flex gap-2.5 text-[length:var(--t-meta)] leading-relaxed text-ink-soft">
                  <span className="mt-[2px] font-serif text-[length:var(--t-meta)] text-haldi">{i + 1}</span>
                  <span>
                    {step.text}
                    {/* Which legal system this follows from. A step drawn from
                        treaty text must never read as an Indian requirement. */}
                    <span
                      className={`ml-1.5 align-middle text-[10px] uppercase tracking-[0.08em] ${
                        step.jurisdiction === "international"
                          ? "text-indigo-dye"
                          : "text-haldi"
                      }`}
                    >
                      {step.jurisdiction === "international"
                        ? labels.international
                        : labels.india}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-[length:var(--t-micro)] leading-relaxed text-ink-faint">
              {data.reason || labels.none}
            </p>
          )}

          {data.rejected.length > 0 && (
            <p className="mt-2.5 border-l-2 border-neem bg-neem-wash px-2.5 py-1.5 text-[length:var(--t-micro)] leading-relaxed text-ink-soft">
              <span className="eyebrow text-neem">{labels.guard}</span>{" "}
              {data.rejected.length}{" "}
              {data.rejected.length === 1 ? "suggestion was" : "suggestions were"} dropped
              for not resting on a cited source.
            </p>
          )}

          <p className="mt-3 text-[length:var(--t-micro)] italic leading-relaxed text-ink-faint">
            {data.disclaimer}
          </p>
        </div>
      )}
    </section>
  );
}
