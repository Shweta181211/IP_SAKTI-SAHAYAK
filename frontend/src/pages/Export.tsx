import { Link, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { EXPORT_LANES } from "../data/exportMarkets";
import { loadLastAnswer, printBriefing } from "../printBriefing";
import { useShell } from "../Shell";
import { STRINGS } from "../i18n";
import type { Answer } from "../types";

export function ExportPage() {
  const { uiLang } = useShell();
  const t = STRINGS[uiLang];
  const navigate = useNavigate();
  const [last, setLast] = useState<Answer | null>(null);

  useEffect(() => {
    setLast(loadLastAnswer());
  }, []);

  return (
    <main className="export-stage mx-auto min-h-[calc(100vh-4rem)] max-w-sheet px-6 py-12 text-ink">
      <p className="explore-kicker explore-kicker--ink">International filing · treaty corpus</p>
      <h1 className="explore-page-title mt-3">
        Treaty and regional pathways.
        <em> Indexed apart from Indian law.</em>
      </h1>
      <p className="mt-4 max-w-2xl text-[16px] leading-relaxed text-ink-soft">
        Each route retrieves from the international corpus (TRIPS, CBD, Nagoya,
        GRATK, PCT, Madrid, Hague, Budapest, the European Patent Convention, and
        EU Directive 2004/24/EC). US FDA marketing-authorisation texts are not
        in this corpus and are declined.
      </p>

      <div className="export-grid mt-10">
        {EXPORT_LANES.map((lane, i) => (
          <TiltCard
            key={lane.id}
            onClick={() =>
              navigate(`/ask?j=international&q=${encodeURIComponent(lane.question)}`)
            }
          >
            <p className="eyebrow text-haldi">{String(i + 1).padStart(2, "0")}</p>
            <h2 className="mt-2 font-serif text-[20px] text-ink">{lane.treaty}</h2>
            <p className="mt-2 text-[13.5px] leading-relaxed text-ink-soft">{lane.use}</p>
            <p className="mt-3 font-mono text-[11px] text-ink-faint">{lane.file}</p>
            <p className="mt-5 text-[12.5px] font-medium text-clay">Open in Consult →</p>
          </TiltCard>
        ))}
      </div>

      <section className="card mt-14 p-6">
        <h2 className="font-serif text-[22px]">{t.exportBriefing}</h2>
        <p className="mt-2 text-[14px] text-ink-soft">
          Print the last consultation as a one-page opinion sheet — question, trail, verbatim excerpts, disclaimer.
        </p>
        {last ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <p className="max-w-xl font-serif text-[15px] italic text-ink-soft">“{last.question}”</p>
            <button
              type="button"
              onClick={() => printBriefing(last)}
              className="rounded-full bg-ink px-4 py-2 text-[13px] text-paper"
            >
              Print briefing
            </button>
            <Link to="/ask" className="text-[13px] text-indigo-dye underline">
              Return to Consult
            </Link>
          </div>
        ) : (
          <p className="mt-4 text-[14px] text-ink-faint">
            No consultation in this session yet.{" "}
            <Link to="/ask" className="text-indigo-dye underline">
              Submit a question
            </Link>{" "}
            first, then come back.
          </p>
        )}
      </section>
    </main>
  );
}

function TiltCard({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick: () => void;
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
      className="tilt-card p-6 text-left"
    >
      {children}
    </button>
  );
}
