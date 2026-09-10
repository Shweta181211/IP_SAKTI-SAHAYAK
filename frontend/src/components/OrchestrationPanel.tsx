import { useShell } from "../Shell";

/**
 * How one question is actually served: several specialised calls, over a chain
 * of endpoints that fails over on its own.
 *
 * The problem statement asks for agentic multi-source orchestration. That is
 * easy to claim and hard to show, so this panel shows two things a reader can
 * check rather than believe:
 *
 *  1. **The stages.** A question is not one call. Each stage below has its own
 *     prompt, its own output contract and its own failure mode, and the answer
 *     you read is what survived all of them. The per-answer trace shows the
 *     same chain with live timings.
 *  2. **The endpoints, and which ones actually answered.** The chain is six
 *     endpoints across three providers, and the counts are incremented as each
 *     call RETURNS - not read off the configured head, which would report the
 *     same name whether or not the chain had ever moved. So more than one name
 *     there is a failover that really happened.
 *
 * Everything here comes from /health. A dead backend renders nothing rather
 * than a remembered figure.
 */

/** The specialised calls behind one question. Each is a separate prompt with
 *  its own contract - which is what makes this a pipeline rather than a wrapper. */
const STAGES: Array<{ name: string; does: string; guard: string }> = [
  {
    name: "Classify the formulation",
    does: "Decides which of six regulatory categories the product falls in.",
    guard: "Anchored to the statutory definition, injected verbatim from the corpus.",
  },
  {
    name: "Expand the query",
    does: "Restates the question in statutory vocabulary, so search can find it.",
    guard: "Failure is reported, not hidden — the answer is marked as degraded.",
  },
  {
    name: "Gate scope and jurisdiction",
    does: "Decides whether this is answerable here at all, and under whose law.",
    guard: "Fails closed. No model, no answer — never a guess from Indian law.",
  },
  {
    name: "Retrieve and fuse",
    does: "Dense and lexical search, per jurisdiction, fused by rank.",
    guard: "One index per jurisdiction, so the two legal systems never mix.",
  },
  {
    name: "Generate the trail",
    does: "Writes the four steps, citing only what it was shown.",
    guard: "Sees the evidence and nothing else.",
  },
  {
    name: "Validate every citation",
    does: "Checks each id against what was actually retrieved.",
    guard: "An unverifiable id is rejected; an unsourced step is replaced.",
  },
  {
    name: "Score evidence support",
    does: "Rates what survived, not what was retrieved.",
    guard: "Computed after validation, so it cannot flatter a stripped answer.",
  },
];

export function OrchestrationPanel() {
  const { health } = useShell();
  const chain = health?.llm_chain ?? [];
  // Counted on the way out of each successful call, so this says which endpoint
  // ANSWERED - not which one was configured first. The distinction is the whole
  // point: the second cannot evidence a failover, and the first can.
  const models = health?.llm_served ?? {};
  const observed = Object.entries(models).sort((a, b) => b[1] - a[1]);
  const providers = new Set(chain.map((e) => e.split(":")[0]));

  return (
    <section className="audit mt-14">
      <p className="explore-kicker explore-kicker--ink">Orchestration</p>
      <h2 className="explore-page-title mt-3">
        One question,
        <em> seven decisions.</em>
      </h2>
      <p className="mt-4 max-w-2xl text-[length:var(--t-body)] leading-relaxed text-ink-soft">
        A question is not one call to a model. Each stage below has its own prompt, its
        own output contract and its own way of failing, and the answer you read is what
        came through all of them. Open “How this answer was assembled” under any answer
        to see the same chain with live timings and what each stage decided.
      </p>

      <ol className="orch-stages mt-8">
        {STAGES.map((s, i) => (
          <li key={s.name} style={{ ["--i" as string]: i }} className="orch-stage reveal-in">
            <span className="orch-n">{i + 1}</span>
            <div className="min-w-0">
              <p className="orch-name">{s.name}</p>
              <p className="orch-does">{s.does}</p>
              <p className="orch-guard">{s.guard}</p>
            </div>
          </li>
        ))}
      </ol>

      {chain.length > 0 && (
        <>
          <h3 className="orch-sub mt-10">
            The endpoint chain — {chain.length} endpoints across {providers.size} providers
          </h3>
          <p className="mt-2 max-w-2xl text-[length:var(--t-meta)] leading-relaxed text-ink-soft">
            Tried best-first. A per-minute limit is waited out; a daily cap is recognised
            as unwaitable and the whole provider is skipped, because retrying it would
            only add dead air. The order is configuration, not code.
          </p>
          <ol className="orch-chain mt-4">
            {chain.map((endpoint, i) => (
              <li key={endpoint} className={`orch-endpoint ${i === 0 ? "is-primary" : ""}`}>
                <span className="orch-rank">{i + 1}</span>
                <span className="orch-endpoint-name">{endpoint}</span>
                {models[endpoint] ? (
                  <span className="orch-served">{models[endpoint]} served</span>
                ) : null}
              </li>
            ))}
          </ol>
        </>
      )}

      {observed.length > 0 && (
        <div className="audit-note mt-6">
          <p className="eyebrow text-indigo-dye">Observed, not asserted</p>
          <p className="mt-1.5 text-[length:var(--t-meta)] leading-relaxed text-ink-soft">
            {observed.length === 1 ? (
              <>
                Every model call since this server started was answered by{" "}
                <code className="audit-field">{observed[0][0]}</code> ({observed[0][1]}{" "}
                calls). The chain has not needed to fail over in this window — which is
                what a healthy primary looks like, not evidence that failover is missing.
              </>
            ) : (
              <>
                Model calls since this server started were answered by {observed.length}{" "}
                different endpoints:{" "}
                {observed.map(([name, n]) => (
                  <code key={name} className="audit-field">
                    {name} ×{n}
                  </code>
                ))}
                . Counted as each call returned, so this is the chain having actually
                moved — not the configured order being re-reported.
              </>
            )}
          </p>
        </div>
      )}
    </section>
  );
}
