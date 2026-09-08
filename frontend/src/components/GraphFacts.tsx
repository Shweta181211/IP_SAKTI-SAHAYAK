import { useShell } from "../Shell";

/**
 * The provision graph, stated as the four numbers that describe it.
 *
 * Statutes are a graph, not a list: Rule 122-E means little without the rules
 * it points at, and a reader following a citation wants to know what it leads
 * to. Those edges are extracted from each passage's own text by pattern, with
 * no model in the loop — so an edge is something the statute says, not
 * something a model believes. That is the reason it can be shown as fact here.
 *
 * The numbers come from `/health`, live. If the backend is down there are no
 * numbers, and this renders nothing rather than a remembered figure.
 */
export function GraphFacts() {
  const { health } = useShell();
  const g = health?.graph;
  if (!g || !g.provisions) return null;

  const facts: Array<{ n: number; label: string; note: string }> = [
    {
      n: g.provisions,
      label: "Provisions",
      note: "sections, rules and articles the corpus can name",
    },
    {
      n: g.references ?? 0,
      label: "Cross-references",
      note: "each one quoted from the passage that makes it",
    },
    {
      n: g.passages_with_references ?? 0,
      label: "Linked passages",
      note: "passages that point somewhere else in their own instrument",
    },
    {
      n: g.provisions_referenced ?? 0,
      label: "Provisions pointed at",
      note: "reachable by following a link from a cited source",
    },
  ];

  return (
    <section className="audit mt-14">
      <p className="explore-kicker explore-kicker--ink">Provision graph</p>
      <h2 className="explore-page-title mt-3">
        The law
        <em> points at itself.</em>
      </h2>
      <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
        Every source card in an answer carries the provisions that passage refers to,
        and the provisions that refer back to it. The links are read out of the
        statutory text itself — no model proposes a relationship, so none can invent
        one. Cross-instrument references are deliberately not resolved: deciding that
        “section 4 of the Trade and Merchandise Marks Act” means a chunk in another
        document would be our legal judgement, not the statute’s words.
      </p>

      <ul className="audit-counts mt-8 lg:grid-cols-4">
        {facts.map((f, i) => (
          <li
            key={f.label}
            style={{ ["--i" as string]: i }}
            className="audit-count reveal-in is-indigo"
          >
            <span className="audit-count-n">{f.n.toLocaleString()}</span>
            <span className="audit-count-label">{f.label}</span>
            <span className="mt-2 block text-[11.5px] leading-snug text-ink-faint">
              {f.note}
            </span>
          </li>
        ))}
      </ul>

      {(health?.graph_problems ?? []).length > 0 && (
        <p className="mt-4 border-l-2 border-clay bg-clay-wash px-3 py-2 text-[13px] text-ink-soft">
          {health!.graph_problems!.join(" · ")}
        </p>
      )}
    </section>
  );
}
