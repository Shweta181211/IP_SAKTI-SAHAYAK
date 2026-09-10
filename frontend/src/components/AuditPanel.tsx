import { useEffect, useState } from "react";
import { fetchAudit } from "../api";
import type { AuditEntry, AuditTrail } from "../types";

/**
 * The system's record of its own behaviour, shown rather than claimed.
 *
 * Two requirements pull against each other here — auditability wants a record,
 * data protection wants as little retained as possible — so this panel shows
 * both at once: the operational rows the server wrote, and the count of rows
 * that kept a question (zero unless somebody opted in). The redaction line is
 * there because a redaction nobody can see is indistinguishable from a field
 * that was never collected.
 *
 * Nothing here is written by a model. Every number is a count over a local
 * append-only file, fetched live — an empty log renders as an empty log.
 */
export function AuditPanel() {
  const [trail, setTrail] = useState<AuditTrail | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "unavailable">("loading");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let live = true;
    fetchAudit(40).then((data) => {
      if (!live) return;
      setTrail(data);
      setState(data ? "ready" : "unavailable");
    });
    return () => {
      live = false;
    };
  }, []);

  if (state === "loading") {
    return (
      <section className="audit mt-14">
        <p className="explore-kicker explore-kicker--ink">Audit trail</p>
        <p className="mt-3 text-[length:var(--t-meta)] text-ink-faint">Reading the log…</p>
      </section>
    );
  }

  if (state === "unavailable" || !trail) {
    return (
      <section className="audit mt-14">
        <p className="explore-kicker explore-kicker--ink">Audit trail</p>
        <p className="mt-3 text-[length:var(--t-meta)] text-ink-soft">
          The server is not reachable, so its log cannot be read. This panel never
          shows a cached or example figure — an unreadable log reads as unreadable.
        </p>
      </section>
    );
  }

  const s = trail.summary;
  const counts: Array<{ label: string; value: number; tone?: string }> = [
    { label: "Recorded", value: s.entries },
    { label: "Answered", value: s.answered ?? 0 },
    { label: "Refused", value: s.abstained ?? 0, tone: "clay" },
    { label: "Sent to a human", value: s.escalated ?? 0, tone: "clay" },
    { label: "Citations rejected", value: s.citations_rejected ?? 0, tone: "neem" },
    { label: "Questions retained", value: s.retained_question_text ?? 0, tone: "indigo" },
  ];

  return (
    <section className="audit mt-14">
      <p className="explore-kicker explore-kicker--ink">Audit trail</p>
      <h2 className="explore-page-title mt-3">
        What this system
        <em> did, on the record.</em>
      </h2>
      <p className="mt-4 max-w-2xl text-[length:var(--t-body)] leading-relaxed text-ink-soft">
        Every question, refusal and export report is written to an append-only log on
        the machine running this build. The log records what was <em>decided</em> — it
        does not record what was asked unless the asker opts in, and even then the
        text is removed before any row is served here.
      </p>

      <ul className="audit-counts mt-8">
        {counts.map((c, i) => (
          <li
            key={c.label}
            style={{ ["--i" as string]: i }}
            className={`audit-count reveal-in ${c.tone ? `is-${c.tone}` : ""}`}
          >
            <span className="audit-count-n">{c.value.toLocaleString()}</span>
            <span className="audit-count-label">{c.label}</span>
          </li>
        ))}
      </ul>

      {/* The privacy claim, stated next to the number that would falsify it. */}
      <div className="audit-note mt-6">
        <p className="eyebrow text-indigo-dye">Retention</p>
        <p className="mt-1.5 text-[length:var(--t-meta)] leading-relaxed text-ink-soft">{trail.retention}</p>
        <p className="mt-2 text-[length:var(--t-micro)] leading-relaxed text-ink-faint">
          Removed before serving:{" "}
          {trail.redacted_fields.map((f) => (
            <code key={f} className="audit-field">
              {f}
            </code>
          ))}
        </p>
      </div>

      {trail.entries.length > 0 && (
        <>
          <button
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
            className="audit-toggle mt-6"
          >
            {expanded ? "Hide the rows" : `Read the last ${trail.entries.length} rows`}
          </button>
          <div className="reveal" data-open={expanded} aria-hidden={!expanded}>
            <div>
              <div className="audit-table-wrap mt-4">
                <table className="audit-table">
                  <thead>
                    <tr>
                      <th scope="col">When</th>
                      <th scope="col">Kind</th>
                      <th scope="col">Outcome</th>
                      <th scope="col">Sources</th>
                      <th scope="col">Rejected</th>
                      <th scope="col">Model</th>
                      <th scope="col">Took</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trail.entries.map((row, i) => (
                      <AuditRow key={`${row.ts}-${i}`} row={row} />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function num(row: AuditEntry, key: string): number {
  const v = row[key];
  return typeof v === "number" ? v : 0;
}

function AuditRow({ row }: { row: AuditEntry }) {
  const abstained = row.abstained === true;
  // The abstention KIND is the useful half: "refused" alone does not say whether
  // a scope boundary held or a provider was down, and those are different facts
  // about the system.
  const reason = typeof row.abstention_kind === "string" ? row.abstention_kind : "";
  const outcome = abstained
    ? `refused${reason && reason !== "none" ? ` · ${reason.replace(/_/g, " ")}` : ""}`
    : "answered";
  const rejected = num(row, "rejected_citations") + num(row, "citations_rejected");
  const took = typeof row.elapsed_s === "number" ? `${row.elapsed_s.toFixed(1)}s` : "—";

  return (
    <tr className={abstained ? "is-refused" : ""}>
      <td className="audit-ts">{formatTs(row.ts)}</td>
      <td>{String(row.kind ?? "query").replace(/_/g, " ")}</td>
      <td className={abstained ? "text-clay" : "text-neem"}>{outcome}</td>
      <td className="tabular-nums">{num(row, "citations") || "—"}</td>
      <td className={`tabular-nums ${rejected > 0 ? "text-neem" : "text-ink-faint"}`}>
        {rejected || "—"}
      </td>
      <td className="audit-model">{String(row.model ?? "—")}</td>
      <td className="tabular-nums text-ink-faint">{took}</td>
    </tr>
  );
}

function formatTs(value: unknown): string {
  if (typeof value !== "string") return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
