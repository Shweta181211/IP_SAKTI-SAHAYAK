import { useMemo, useState, type ReactElement } from "react";
import type {
  Citation,
  ExportReadinessReport,
  ReadinessItem,
  ReadinessSection,
  ReadinessStatus,
} from "../types";
import { buildCitationIndex, buildCitationMap } from "./ReasoningTrail";
import { Confidence } from "./Confidence";
import { printReadiness } from "../printReadiness";
import { Escalate } from "./Escalate";

/**
 * The export readiness report.
 *
 * Every line here is a claim about law, so every line carries the same
 * apparatus as an answer in the Consult flow: a status derived server-side from
 * what actually survived citation validation, the provisions it rests on, and
 * the verbatim source one click away.
 *
 * The state worth designing carefully is `not_covered`. A market the corpus
 * does not reach is the honest and common outcome, and the temptation is to
 * hide it or fill it with generic advice. It is given the same visual weight as
 * a satisfied requirement instead — a stated boundary is a finding.
 */

const STATUS: Record<
  ReadinessStatus,
  { label: string; className: string; icon: ReactElement }
> = {
  verified: {
    label: "Verified",
    className: "is-verified",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  needs_verification: {
    label: "Needs verification",
    className: "is-check",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5M12 16.5h.01" strokeLinecap="round" />
      </svg>
    ),
  },
  blocker: {
    label: "Potential blocker",
    className: "is-blocker",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="9" />
        <path d="M6.3 6.3l11.4 11.4" strokeLinecap="round" />
      </svg>
    ),
  },
  not_covered: {
    label: "Not in this corpus",
    className: "is-gap",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
      </svg>
    ),
  },
};

function Item({
  item,
  citationById,
  citationIndex,
}: {
  item: ReadinessItem;
  citationById: Map<string, Citation>;
  citationIndex: Map<string, number>;
}) {
  const [showSource, setShowSource] = useState(false);
  const state = STATUS[item.status];
  const sources = item.citation_ids
    .map((id) => citationById.get(id))
    .filter((c): c is Citation => !!c);

  return (
    <li className={`readiness-item ${state.className}`}>
      <span className="readiness-icon" aria-hidden>
        {state.icon}
      </span>

      <div className="min-w-0 flex-1">
        {/* The requirement area, above the title. It is what makes the list
            legible as a CHECKLIST rather than a set of findings: the reader can
            see licensing, IP, ABS, labelling and documents all accounted for,
            including the ones the corpus could not reach. */}
        {item.area_label && (
          <p className="readiness-area">{item.area_label}</p>
        )}
        <p className="readiness-item-head">
          <span className="readiness-title">{item.title}</span>
          <span className="readiness-status">{state.label}</span>
        </p>

        {item.detail && <p className="readiness-detail">{item.detail}</p>}

        {/* Why this state and not another. A status icon nobody can interrogate
            is decoration; this is the sentence that makes it a finding. */}
        {item.status_reason && (
          <p className="readiness-reason">{item.status_reason}</p>
        )}

        {sources.length > 0 && (
          <>
            <p className="readiness-provisions">
              {sources.map((c) => (
                <span key={c.chunk_id} className="step-provision">
                  <span className="step-provision-n">
                    {citationIndex.get(c.chunk_id) ?? "?"}
                  </span>
                  <span className="step-provision-act">{c.act_name}</span>
                  {c.section && <span className="step-provision-sec">{c.section}</span>}
                </span>
              ))}
            </p>
            <button
              type="button"
              onClick={() => setShowSource((v) => !v)}
              aria-expanded={showSource}
              className="step-source-toggle"
            >
              {showSource ? "Hide source text" : "Read source text"}
            </button>
            {showSource && (
              <div className="step-source">
                {sources.map((c) => (
                  <div key={c.chunk_id}>
                    <p className="step-source-head">
                      <span className="step-provision-n">
                        {citationIndex.get(c.chunk_id) ?? "?"}
                      </span>
                      {c.act_name}
                      {c.section ? ` · ${c.section}` : ""}
                      {c.page ? ` · p. ${c.page}` : ""}
                    </p>
                    <blockquote>{c.excerpt}</blockquote>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </li>
  );
}

function Section({
  section,
  citationById,
  citationIndex,
}: {
  section: ReadinessSection;
  citationById: Map<string, Citation>;
  citationIndex: Map<string, number>;
}) {
  const counts = section.items.reduce<Record<string, number>>((acc, i) => {
    acc[i.status] = (acc[i.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <section className="readiness-section reveal-in">
      <header className="readiness-section-head">
        <div>
          <p className="eyebrow text-ink-faint">
            {section.jurisdiction === "national" ? "Indian law" : "International instruments"}
          </p>
          <h3 className="readiness-section-title">{section.heading}</h3>
        </div>
        {section.items.length > 0 && (
          <p className="readiness-tally">
            {(["blocker", "needs_verification", "verified", "not_covered"] as const)
              .filter((s) => counts[s])
              .map((s) => (
                <span key={s} className={STATUS[s].className}>
                  <span className="readiness-tally-icon" aria-hidden>
                    {STATUS[s].icon}
                  </span>
                  {counts[s]}
                </span>
              ))}
          </p>
        )}
      </header>

      {section.covered ? (
        <ul className="readiness-list">
          {section.items.map((item) => (
            <Item
              key={item.title}
              item={item}
              citationById={citationById}
              citationIndex={citationIndex}
            />
          ))}
        </ul>
      ) : (
        /* A stated boundary, given the same weight as a satisfied requirement.
           The alternative — generic export advice — is the one thing this
           feature must never produce. */
        <div className="readiness-gap">
          <p className="eyebrow text-clay">Not covered by the current corpus</p>
          <p className="readiness-gap-body">{section.uncovered_reason}</p>
          <p className="readiness-gap-note">
            Nothing is stated for this market rather than guessing at it. The corpus holds
            treaties and regional instruments, not every country's domestic marketing law —
            so this is a boundary of the sources, not a finding about your product.
          </p>
        </div>
      )}
    </section>
  );
}

export function ReadinessReport({ report }: { report: ExportReadinessReport }) {
  const citationIndex = useMemo(
    () => buildCitationIndex(report.citations),
    [report.citations],
  );
  const citationById = useMemo(
    () => buildCitationMap(report.citations),
    [report.citations],
  );

  if (report.abstained) {
    return (
      <div className="card border-clay/40 bg-clay-wash p-5">
        <p className="eyebrow text-clay">No readiness view available</p>
        <p className="prose-legal mt-1.5 text-ink">{report.abstention_message}</p>
        {report.escalate && <Escalate reason={report.escalation_reason} />}
      </div>
    );
  }

  return (
    <div className="readiness">
      <header className="readiness-head">
        <div className="min-w-0">
          <p className="eyebrow text-ink-faint">Export readiness</p>
          <h2 className="readiness-product">{report.product}</h2>
          <p className="readiness-route">
            India <span aria-hidden>→</span> {report.target_country}
          </p>
        </div>
        <div className="readiness-head-side">
          {report.classification && (
            <div className="readiness-verdict">
              <p className="eyebrow text-haldi">Classified as</p>
              <p className="readiness-verdict-label">{report.classification.label}</p>
            </div>
          )}
          {/* A startup does not act on a web page - it forwards a document. The
              sheet carries every source verbatim at the back, so the reader can
              check the checklist instead of trusting it. */}
          <button
            type="button"
            onClick={() => printReadiness(report)}
            className="readiness-print"
          >
            Print / save as PDF
          </button>
        </div>
      </header>

      {report.confidence && (
        <Confidence
          level={report.confidence}
          label={report.confidence_label ?? ""}
          score={report.confidence_score}
          reasons={report.confidence_reasons}
        />
      )}

      {/* Only rendered when the international corpus actually said it. A
          target-market framing with no source is exactly the invention this
          feature must not produce, so the backend drops it rather than
          shipping it unsourced. */}
      {report.target_framing && (
        <section className="readiness-framing">
          <p className="eyebrow text-ink-faint">
            How {report.target_country} frames this kind of product
          </p>
          <p className="readiness-framing-body">{report.target_framing}</p>
          <p className="readiness-provisions">
            {report.target_framing_citation_ids.map((id) => {
              const c = citationById.get(id);
              if (!c) return null;
              return (
                <span key={id} className="step-provision">
                  <span className="step-provision-n">{citationIndex.get(id) ?? "?"}</span>
                  <span className="step-provision-act">{c.act_name}</span>
                  {c.section && <span className="step-provision-sec">{c.section}</span>}
                </span>
              );
            })}
          </p>
        </section>
      )}

      <div className="readiness-columns">
        {report.india && (
          <Section
            section={report.india}
            citationById={citationById}
            citationIndex={citationIndex}
          />
        )}
        {report.target && (
          <Section
            section={report.target}
            citationById={citationById}
            citationIndex={citationIndex}
          />
        )}
      </div>

      {report.action_plan.length > 0 && (
        <section className="readiness-plan">
          <p className="eyebrow text-ink-faint">Action plan</p>
          <ol className="readiness-plan-list">
            {report.action_plan.map((step, i) => (
              <li key={step.text}>
                <span className="readiness-plan-n">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="readiness-plan-text">{step.text}</span>
                  <span
                    className={`readiness-plan-side ${
                      step.jurisdiction === "international" ? "is-intl" : ""
                    }`}
                  >
                    {step.jurisdiction === "international"
                      ? "from the international instruments"
                      : "from Indian law"}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {report.citations.length > 0 && (
        <section className="readiness-sources">
          <p className="eyebrow text-ink-faint">
            Sources cited · {report.citations.length}
          </p>
          <ul className="readiness-source-list">
            {report.citations.map((c, i) => (
              <li key={c.chunk_id}>
                <span className="step-provision-n">{i + 1}</span>
                <span>
                  {c.act_name}
                  {c.section ? ` · ${c.section}` : ""}
                  {c.page ? ` · p. ${c.page}` : ""}
                </span>
              </li>
            ))}
          </ul>
          {report.rejected_citation_ids.length > 0 && (
            <p className="readiness-guard">
              Citation guard: {report.rejected_citation_ids.length} unverifiable reference
              {report.rejected_citation_ids.length > 1 ? "s were" : " was"} rejected before
              this report was shown.
            </p>
          )}
        </section>
      )}

      {report.escalate && <Escalate reason={report.escalation_reason} />}

      <p className="readiness-disclaimer">{report.disclaimer}</p>
    </div>
  );
}
