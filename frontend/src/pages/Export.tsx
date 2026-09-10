import { Link } from "react-router-dom";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { CancelledError, fetchExportReadiness } from "../api";
import { ReadinessReport } from "../components/ReadinessReport";
import { loadLastAnswer, printBriefing } from "../printBriefing";
import { useShell } from "../Shell";
import { STRINGS } from "../i18n";
import type { Answer, Category, ExportReadinessReport } from "../types";

/**
 * Export readiness — the India-side and target-market position for one product.
 *
 * This page was a launcher for ten treaty questions. The readiness report is
 * now its primary work and the treaty lanes sit beneath it as a way to read one
 * instrument directly, which is a different job from assessing a product.
 *
 * Two things here are deliberate and easy to get wrong:
 *
 * **The target market is free text.** There is no list of supported countries,
 * because a list is a promise about coverage that the corpus has to keep. What
 * the report says about a market is retrieved and cited at request time, and a
 * market the corpus does not reach produces a stated boundary.
 *
 * **The category select is optional and defaults to "let the system decide".**
 * The six-category classifier already reads the description; offering the field
 * lets someone who knows their category pin it, without making everyone else
 * guess at regulatory vocabulary before they can ask anything.
 */

const CATEGORIES: { value: Category; label: string }[] = [
  { value: "classical_generic", label: "Classical / generic Ayurvedic medicine" },
  { value: "patent_proprietary", label: "Patent or proprietary medicine" },
  { value: "new_drug", label: "New / non-classical drug" },
  { value: "phytopharmaceutical", label: "Phytopharmaceutical" },
  { value: "ayurveda_aahar", label: "Ayurveda Aahar / nutraceutical" },
  { value: "cosmetic", label: "Cosmetic" },
];

export function ExportPage() {
  const { uiLang, logConsent } = useShell();
  const t = STRINGS[uiLang];
  const [last, setLast] = useState<Answer | null>(null);

  const [product, setProduct] = useState("");
  const [ingredients, setIngredients] = useState("");
  const [category, setCategory] = useState<Category | "">("");
  const [healthClaims, setHealthClaims] = useState(false);
  const [targetCountry, setTargetCountry] = useState("");

  const [report, setReport] = useState<ExportReadinessReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLast(loadLastAnswer());
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (loading || !product.trim() || !targetCountry.trim()) return;
    setLoading(true);
    setError(null);
    setReport(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const result = await fetchExportReadiness(
        {
          product: product.trim(),
          ingredients: ingredients.trim(),
          category: category === "" ? null : category,
          health_claims: healthClaims,
          target_country: targetCountry.trim(),
        },
        controller.signal,
        logConsent,
      );
      setReport(result);
      requestAnimationFrame(() =>
        resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (e) {
      if (!(e instanceof CancelledError)) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  }

  const ready = product.trim().length > 1 && targetCountry.trim().length > 1;

  return (
    <main className="export-stage mx-auto min-h-[calc(100vh-4rem)] max-w-sheet px-6 py-12 text-ink">
      <header className="page-head">
        <h1 className="explore-page-title">
          What India requires, and what the market requires.
        </h1>
        <p className="page-lead">
          Describe the product and name the market. The India-side position is answered
          from Indian statutes and rules; the target-market position from the treaty and
          regional corpus only. Where that corpus does not reach a market, the report says
          so rather than filling the gap.
        </p>
      </header>

      {/* ------------------------------- the form ------------------------------- */}
      <form onSubmit={submit} className="readiness-form">
        <div className="readiness-field readiness-field--wide">
          <label htmlFor="rp">Product or formulation</label>
          <textarea
            id="rp"
            rows={2}
            value={product}
            onChange={(e) => setProduct(e.target.value)}
            placeholder="e.g. A classical ashwagandha churna made to a First Schedule formula"
          />
        </div>

        <div className="readiness-field readiness-field--wide">
          <label htmlFor="ri">Key ingredients</label>
          <input
            id="ri"
            value={ingredients}
            onChange={(e) => setIngredients(e.target.value)}
            placeholder="e.g. Withania somnifera root powder, black pepper"
          />
        </div>

        <div className="readiness-field">
          <label htmlFor="rc">Product category</label>
          <select
            id="rc"
            value={category}
            onChange={(e) => setCategory(e.target.value as Category | "")}
          >
            {/* The classifier reads the description anyway; this only lets
                someone who already knows pin it. */}
            <option value="">Let the system classify it</option>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        <div className="readiness-field">
          <label htmlFor="rt">Target export market</label>
          <input
            id="rt"
            value={targetCountry}
            onChange={(e) => setTargetCountry(e.target.value)}
            placeholder="e.g. Germany, European Union, Japan"
          />
          <p className="readiness-hint">
            Any market. What the report says about it is retrieved and cited at the time
            you ask — there is no built-in list.
          </p>
        </div>

        <div className="readiness-field readiness-field--wide">
          <label className="readiness-check">
            <input
              type="checkbox"
              checked={healthClaims}
              onChange={(e) => setHealthClaims(e.target.checked)}
            />
            <span>
              Health or medical claims are made for this product
              <span className="readiness-hint">
                Claims change which regime governs a product, so this materially changes the
                answer.
              </span>
            </span>
          </label>
        </div>

        <div className="readiness-actions">
          <button type="submit" disabled={!ready || loading} className="readiness-submit">
            {loading ? "Assembling the report…" : "Build readiness report"}
          </button>
          {loading && (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="readiness-stop"
            >
              Stop
            </button>
          )}
          <span className="readiness-hint">Information, not legal advice.</span>
        </div>
      </form>

      {error && (
        <div className="card mt-6 max-w-3xl border-clay/40 bg-clay-wash p-4">
          <p className="eyebrow text-clay">Could not complete</p>
          <p className="mt-1 text-[length:var(--t-meta)] text-ink">{error}</p>
        </div>
      )}

      {loading && (
        /* The skeleton is the shape of the report that is coming — two columns
           of checklist lines — so a 20-second wait is legible rather than a
           spinner that says nothing. */
        <div className="readiness-skeleton" aria-hidden>
          {[0, 1].map((col) => (
            <div key={col}>
              <div className="readiness-skel-head" />
              {[0, 1, 2].map((row) => (
                <div
                  key={row}
                  className="readiness-skel-row"
                  style={{ animationDelay: `${(col * 3 + row) * 110}ms` }}
                />
              ))}
            </div>
          ))}
        </div>
      )}

      <div ref={resultRef}>{report && <ReadinessReport report={report} />}</div>

      {/* The treaty lanes have their own route again — they answer what an
          instrument SAYS, which is a different job from assessing a product
          against one, and stacking them here made this form read as a preamble
          to a link list. */}
      <section className="readiness-crosslink">
        <div className="min-w-0">
          <p className="eyebrow text-ink-faint">Reading an instrument directly</p>
          <p className="mt-1 text-[length:var(--t-meta)] leading-relaxed text-ink-soft">
            To ask what a single treaty or regional instrument says, rather than assessing a
            product against it, open the treaty routes.
          </p>
        </div>
        <Link to="/treaties" className="readiness-crosslink-cta">
          Treaty routes <span aria-hidden>→</span>
        </Link>
      </section>

      <section className="card mt-14 p-6">
        <h2 className="font-serif text-[22px]">{t.exportBriefing}</h2>
        <p className="mt-2 text-[length:var(--t-meta)] text-ink-soft">
          Print the last consultation as a one-page opinion sheet — question, trail, verbatim
          excerpts, disclaimer.
        </p>
        {last ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <p className="max-w-xl font-serif text-[length:var(--t-body)] italic text-ink-soft">
              “{last.question}”
            </p>
            <button
              type="button"
              onClick={() => printBriefing(last)}
              className="rounded-full bg-ink px-4 py-2 text-[length:var(--t-meta)] text-paper"
            >
              Print briefing
            </button>
            <Link to="/ask" className="text-[length:var(--t-meta)] text-indigo-dye underline">
              Return to Consult
            </Link>
          </div>
        ) : (
          <p className="mt-4 text-[length:var(--t-meta)] text-ink-faint">
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
