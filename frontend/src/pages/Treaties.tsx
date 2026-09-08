import { useNavigate } from "react-router-dom";
import { useRef, type CSSProperties, type MouseEvent, type ReactNode } from "react";
import { EXPORT_LANES } from "../data/exportMarkets";

/**
 * Treaty and regional pathways — a launcher into the international corpus.
 *
 * This lived at the foot of the Export readiness page and has its own route
 * again, because the two do different jobs: a lane here answers *what an
 * instrument says*, while the readiness report assesses *a product against
 * one*. Sharing a page made the readiness form look like a preamble to a link
 * list.
 *
 * Every lane deep-links into Consult with `j=international`, so the answer
 * comes from the treaty corpus and never from Indian statutes.
 */
export function TreatiesPage() {
  const navigate = useNavigate();

  return (
    <main className="export-stage mx-auto min-h-[calc(100vh-4rem)] max-w-sheet px-6 py-12 text-ink">
      <p className="explore-kicker explore-kicker--ink">International filing · treaty corpus</p>
      <h1 className="explore-page-title mt-3">
        Treaty and regional pathways.
        <em> Indexed apart from Indian law.</em>
      </h1>
      <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-ink-soft">
        Each route opens a question against the international corpus — TRIPS, CBD, Nagoya,
        GRATK, PCT, Madrid, Hague, Budapest, the European Patent Convention, EU Directive
        2004/24/EC, and the FDA botanical-drug guidance. These answer what an instrument
        says. To assess a product against them, use{" "}
        <button
          type="button"
          onClick={() => navigate("/export")}
          className="text-indigo-dye underline decoration-indigo-dye/30 underline-offset-4 hover:decoration-indigo-dye"
        >
          Export readiness
        </button>
        .
      </p>

      <div className="export-grid mt-10">
        {EXPORT_LANES.map((lane, i) => (
          <TiltCard
            key={lane.id}
            index={i}
            onClick={() =>
              navigate(`/ask?j=international&q=${encodeURIComponent(lane.question)}`)
            }
          >
            <p className="eyebrow text-haldi">{String(i + 1).padStart(2, "0")}</p>
            <h2 className="mt-2 font-serif text-[20px] text-ink">{lane.treaty}</h2>
            <p className="mt-2 text-[13.5px] leading-relaxed text-ink-soft">{lane.use}</p>
            <p className="mt-3 font-mono text-[11px] text-ink-faint">{lane.file}</p>
            <p className="mt-5 text-[12.5px] font-medium text-indigo-dye">Open in Consult →</p>
          </TiltCard>
        ))}
      </div>
    </main>
  );
}

function TiltCard({
  children,
  onClick,
  index,
}: {
  children: ReactNode;
  onClick: () => void;
  index: number;
}) {
  const ref = useRef<HTMLButtonElement>(null);
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
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      onMouseMove={move}
      onMouseLeave={leave}
      // `data-index` is what the dark surface draws as the ghost numeral
      // behind the card; `--i` staggers its entrance.
      data-index={String(index + 1).padStart(2, "0")}
      style={{ "--i": index } as CSSProperties}
      className="tilt-card reveal-in p-6 text-left"
    >
      {children}
    </button>
  );
}
