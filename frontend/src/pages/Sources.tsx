import type { CSSProperties } from "react";
import { OFFICIAL_SOURCES } from "../data/exportMarkets";
import { AuditPanel } from "../components/AuditPanel";
import { GraphFacts } from "../components/GraphFacts";

export function SourcesPage() {
  return (
    <main className="export-stage mx-auto min-h-[calc(100vh-4rem)] max-w-sheet px-6 py-12 text-ink">
      <p className="explore-kicker explore-kicker--ink">Official registries</p>
      <h1 className="explore-page-title mt-3">
        Primary sources,
        <em> open to the public.</em>
      </h1>
      <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink-soft">
        These links open free official databases. This build does not connect to paid
        subscriptions and will not do so without explicit, logged permission.
      </p>
      <ul className="mt-10 grid gap-4 sm:grid-cols-2">
        {OFFICIAL_SOURCES.map((src, i) => (
          <li
            key={src.href}
            style={{ "--i": i } as CSSProperties}
            className="card source-card reveal-in p-5"
          >
            <a
              href={src.href}
              target="_blank"
              rel="noreferrer"
              className="font-serif text-[18px] text-indigo-dye underline decoration-indigo-dye/25 underline-offset-4 hover:decoration-indigo-dye"
            >
              {src.name}
            </a>
            <p className="mt-2 text-[13.5px] leading-relaxed text-ink-soft">{src.note}</p>
            <p className="mt-3 font-mono text-[11px] text-ink-faint">{src.href.replace("https://", "")}</p>
          </li>
        ))}
      </ul>
      <GraphFacts />

      <AuditPanel />

      <p className="mt-10 text-[12px] leading-relaxed text-ink-faint">
        Information, not legal advice. Always verify against the live official text.
      </p>
    </main>
  );
}
