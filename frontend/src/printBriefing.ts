import type { Answer } from "./types";
import { citationLabel } from "./types";

export const LAST_ANSWER_KEY = "ipsakti.lastAnswer.v1";

export function rememberAnswer(answer: Answer) {
  try {
    sessionStorage.setItem(LAST_ANSWER_KEY, JSON.stringify(answer));
  } catch {
    /* private windows may throw */
  }
}

export function loadLastAnswer(): Answer | null {
  try {
    const raw = sessionStorage.getItem(LAST_ANSWER_KEY);
    return raw ? (JSON.parse(raw) as Answer) : null;
  } catch {
    return null;
  }
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Open a printable opinion sheet for one consultation. */
export function printBriefing(answer: Answer) {
  const layer = answer.jurisdiction === "international" ? "International · treaties" : "India · national law";
  const steps = answer.steps
    .map(
      (s) => `<section>
        <h3>${s.step}. ${escapeHtml(s.title)}</h3>
        <p>${escapeHtml(s.content)}</p>
        ${s.citation_ids.length ? `<p class="ids">Cited: ${s.citation_ids.map(escapeHtml).join(", ")}</p>` : ""}
      </section>`,
    )
    .join("");
  const cites = answer.citations
    .map(
      (c) => `<article>
        <h4>${escapeHtml(citationLabel(c))}</h4>
        <p class="ex">${escapeHtml(c.excerpt)}</p>
      </article>`,
    )
    .join("");

  const html = `<!doctype html><html><head><meta charset="utf-8"/>
<title>IP-SAKTI Sahayak briefing</title>
<style>
  body { font-family: Georgia, serif; color: #16241e; max-width: 720px; margin: 40px auto; padding: 0 24px; }
  .kicker { letter-spacing: .16em; text-transform: uppercase; font-size: 11px; color: #5b6459; }
  h1 { font-weight: 500; font-size: 26px; margin: 8px 0 4px; }
  h3 { font-size: 14px; letter-spacing: .08em; text-transform: uppercase; color: #c98a2b; }
  h4 { font-size: 13px; font-family: ui-monospace, monospace; margin-bottom: 4px; }
  .q { font-style: italic; color: #24382f; border-left: 3px solid #c98a2b; padding-left: 12px; }
  .ex { font-size: 13px; line-height: 1.55; }
  .ids { font-size: 11px; color: #5b6459; }
  .disc { margin-top: 32px; font-size: 12px; color: #5b6459; border-top: 1px solid #ddceac; padding-top: 12px; }
</style></head><body>
  <p class="kicker">IP-SAKTI Sahayak · ${escapeHtml(layer)}</p>
  <h1>Consultation briefing</h1>
  <p class="q">${escapeHtml(answer.question)}</p>
  ${answer.headline ? `<p><strong>${escapeHtml(answer.headline)}</strong></p>` : ""}
  ${answer.abstained ? `<p>${escapeHtml(answer.abstention_message || "Not answered.")}</p>` : `${steps}<h2>Sources</h2>${cites}`}
  <p class="disc">${escapeHtml(answer.disclaimer)}</p>
  <script>window.onload = () => window.print();</script>
</body></html>`;

  const win = window.open("", "_blank", "noopener,noreferrer");
  if (!win) return;
  win.document.write(html);
  win.document.close();
}
