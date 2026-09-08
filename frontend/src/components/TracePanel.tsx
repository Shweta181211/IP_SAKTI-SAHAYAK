import { useState } from "react";
import type { TraceStep } from "../types";

/**
 * How this answer was assembled.
 *
 * One question is not one call to a model. It is a chain: classify the
 * formulation, restate the question in statutory vocabulary, decide whether it
 * is in scope and in this jurisdiction at all, search twice and fuse, generate,
 * then check every citation against what was actually retrieved and score what
 * survived.
 *
 * That chain is the product. Asserting it in a pitch is worth little; showing
 * the stages that ran, with what each one decided and how long it took, is
 * something a reader can check. It is also the honest answer to "is this just a
 * ChatGPT wrapper" — a question worth being able to answer with evidence.
 *
 * Collapsed by default: it is provenance, not the answer.
 */
export function TracePanel({ trace }: { trace: TraceStep[] }) {
  const [open, setOpen] = useState(false);
  if (trace.length === 0) return null;

  const total = trace.reduce((sum, step) => sum + step.ms, 0);
  const slowest = Math.max(...trace.map((s) => s.ms), 1);

  return (
    <section className="trace">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="trace-toggle"
      >
        <span className="trace-toggle-label">How this answer was assembled</span>
        <span className="trace-toggle-meta">
          {trace.length} stages · {(total / 1000).toFixed(1)}s
        </span>
        <span className={`trace-chevron ${open ? "is-open" : ""}`} aria-hidden>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      <div className="reveal" data-open={open} aria-hidden={!open}>
        <div>
          <ol className="trace-list">
            {trace.map((step, i) => (
              <li key={step.stage} className={`trace-step is-${step.status}`}>
                <span className="trace-n">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="trace-stage">
                    {step.stage}
                    {step.status !== "ok" && (
                      <span className="trace-status">{step.status}</span>
                    )}
                  </span>
                  {step.detail && <span className="trace-detail">{step.detail}</span>}
                  {/* Bar widths are relative to the slowest stage, not to the
                      total: the point is which stage costs the time, and on a
                      free endpoint one stage dwarfs the rest. */}
                  <span className="trace-bar" aria-hidden>
                    <span style={{ width: `${Math.max(2, (step.ms / slowest) * 100)}%` }} />
                  </span>
                </span>
                <span className="trace-ms">{(step.ms / 1000).toFixed(1)}s</span>
              </li>
            ))}
          </ol>
          <p className="trace-note">
            Every stage runs on every question. Retrieval and generation are separate
            calls, and the citation check runs after generation — so a claim the model
            made without a source is removed before you see it, not flagged afterwards.
          </p>
        </div>
      </div>
    </section>
  );
}
