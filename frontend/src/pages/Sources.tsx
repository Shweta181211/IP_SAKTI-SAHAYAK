import { useRef, type CSSProperties, type MouseEvent, type ReactNode } from "react";
import { OFFICIAL_SOURCES } from "../data/exportMarkets";
import { AuditPanel } from "../components/AuditPanel";
import { GraphFacts } from "../components/GraphFacts";
import { OrchestrationPanel } from "../components/OrchestrationPanel";

/**
 * The registries a reader can check us against, and the record of what this
 * build has done.
 *
 * The cards here used to be their own thing - a bordered panel with a link
 * headline, styled only for the dark surface, so on paper they were flat
 * rectangles at a different size from every other card on the site. They are
 * `tilt-card` now, the same component the treaty routes use, because they do
 * the same job: one destination per card, opened by clicking the card rather
 * than by finding a link inside it.
 */
export function SourcesPage() {
  return (
    <main className="export-stage mx-auto min-h-[calc(100vh-4rem)] max-w-sheet px-6 py-12 text-ink">
      <h1 className="explore-page-title">Primary sources, open to the public.</h1>
      <p className="page-lead">
        These open free official databases. This build connects to no paid subscription
        and will not do so without explicit, logged permission.
      </p>

      <div className="export-grid mt-10">
        {OFFICIAL_SOURCES.map((src, i) => (
          <TiltCard key={src.href} index={i} href={src.href}>
            <h2 className="card-title">{src.name}</h2>
            <p className="card-body">{src.note}</p>
            <p className="card-ref">{src.href.replace("https://", "")}</p>
            <p className="card-go">Open the register</p>
          </TiltCard>
        ))}
      </div>

      <OrchestrationPanel />

      <GraphFacts />

      <AuditPanel />

      <p className="mt-12 text-[13px] leading-relaxed text-ink-faint">
        Information, not legal advice. Always verify against the live official text.
      </p>
    </main>
  );
}

/**
 * The treaty page's card, taking an href instead of a click handler.
 *
 * These leave the site, so they are anchors: a middle-click or a long-press
 * has to be able to open a register in a new tab, which a button swallows.
 */
function TiltCard({
  children,
  href,
  index,
}: {
  children: ReactNode;
  href: string;
  index: number;
}) {
  const ref = useRef<HTMLAnchorElement>(null);
  const move = (e: MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    el.style.transform = `rotateX(${-y * 10}deg) rotateY(${x * 12}deg) translateY(-6px)`;
  };
  const leave = () => {
    if (ref.current) ref.current.style.transform = "";
  };
  return (
    <a
      ref={ref}
      href={href}
      target="_blank"
      rel="noreferrer"
      onMouseMove={move}
      onMouseLeave={leave}
      data-index={String(index + 1).padStart(2, "0")}
      style={{ "--i": index } as CSSProperties}
      className="tilt-card reveal-in p-6 text-left"
    >
      {children}
    </a>
  );
}
