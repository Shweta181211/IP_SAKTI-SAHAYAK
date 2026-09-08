import type { Citation, ExportReadinessReport, ReadinessItem, ReadinessSection } from "./types";
import { citationLabel } from "./types";

/**
 * The readiness report as a printable sheet.
 *
 * A startup does not act on a web page. It forwards a document to a consultant,
 * a licensing authority or an investor, and it needs the sources travelling with
 * the checklist - otherwise the reader has to take the claims on trust, which is
 * the one thing this build refuses to ask of anybody.
 *
 * Built from the report OBJECT, never by reading the DOM. Same rule as
 * printBriefing: the screen can be restyled, collapsed or dark, and none of that
 * may change what prints. It also means the print path cannot accidentally
 * inherit a status the page derived client-side - every status here is the one
 * the server settled.
 */

function escapeHtml(value: string): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Print marks, not colour. A checklist is photocopied, faxed and read in
 *  greyscale; a status carried only by hue does not survive any of that. */
const MARK: Record<string, { glyph: string; label: string; cls: string }> = {
  verified: { glyph: "&#10003;", label: "Checked", cls: "ok" },
  needs_verification: { glyph: "!", label: "Needs verification", cls: "warn" },
  blocker: { glyph: "&#10007;", label: "Potential blocker", cls: "stop" },
  not_covered: { glyph: "&#8212;", label: "Not covered by these sources", cls: "gap" },
};

function itemRow(item: ReadinessItem, index: Map<string, number>): string {
  const mark = MARK[item.status] ?? MARK.not_covered;
  const refs = (item.citation_ids ?? [])
    .map((id) => index.get(id))
    .filter((n): n is number => !!n)
    .map((n) => `[${n}]`)
    .join(" ");
  return `<tr class="${mark.cls}">
    <td class="mark"><span>${mark.glyph}</span></td>
    <td>
      ${item.area_label ? `<p class="area">${escapeHtml(item.area_label)}</p>` : ""}
      <p class="title">${escapeHtml(item.title)}</p>
      ${item.detail ? `<p class="detail">${escapeHtml(item.detail)}</p>` : ""}
      ${item.status_reason ? `<p class="why">${escapeHtml(item.status_reason)}</p>` : ""}
    </td>
    <td class="state">${mark.label}${refs ? `<span class="refs">${refs}</span>` : ""}</td>
  </tr>`;
}

function sectionBlock(section: ReadinessSection | null, index: Map<string, number>): string {
  if (!section) return "";
  const counts = section.items.reduce<Record<string, number>>((acc, i) => {
    acc[i.status] = (acc[i.status] ?? 0) + 1;
    return acc;
  }, {});
  const tally = (["blocker", "needs_verification", "verified", "not_covered"] as const)
    .filter((k) => counts[k])
    .map((k) => `${counts[k]} ${MARK[k].label.toLowerCase()}`)
    .join(" &middot; ");

  return `<section class="side">
    <h2>${escapeHtml(section.heading)}</h2>
    <p class="tally">${tally || "no items"}</p>
    ${
      section.uncovered_reason
        ? `<p class="gapnote">${escapeHtml(section.uncovered_reason)}</p>`
        : ""
    }
    ${
      section.items.length
        ? `<table>${section.items.map((i) => itemRow(i, index)).join("")}</table>`
        : ""
    }
  </section>`;
}

/** Open a printable readiness sheet for one report. */
export function printReadiness(report: ExportReadinessReport) {
  // Numbered once, so a checklist line can point at a source by number and the
  // reader can find the verbatim text at the back - the way a brief works.
  const index = new Map<string, number>();
  report.citations.forEach((c: Citation, i) => index.set(c.chunk_id, i + 1));

  const sources = report.citations
    .map(
      (c, i) => `<article>
        <h4><span class="n">${i + 1}</span> ${escapeHtml(citationLabel(c))}</h4>
        <p class="ex">${escapeHtml(c.excerpt)}</p>
      </article>`,
    )
    .join("");

  const plan = report.action_plan
    .map(
      (s, i) => `<li>
        <span class="step-n">${i + 1}</span>
        <span>${escapeHtml(s.text)}
          <em>${s.jurisdiction === "international" ? "international instruments" : "Indian law"}</em>
        </span>
      </li>`,
    )
    .join("");

  const cls = report.classification;

  const html = `<!doctype html><html><head><meta charset="utf-8"/>
<title>Export readiness &mdash; ${escapeHtml(report.product)}</title>
<style>
  @page { margin: 18mm; }
  body { font-family: Georgia, serif; color: #16241e; max-width: 760px; margin: 36px auto; padding: 0 24px; }
  .kicker { letter-spacing: .16em; text-transform: uppercase; font-size: 10px; color: #5b6459; }
  h1 { font-weight: 500; font-size: 25px; margin: 6px 0 2px; }
  .route { font-size: 15px; color: #24382f; margin: 0 0 18px; }
  .route strong { color: #16241e; }
  h2 { font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: #2f4a63;
       border-bottom: 1px solid #ddceac; padding-bottom: 4px; margin: 26px 0 6px; }
  .tally { font-size: 11px; color: #5b6459; margin: 0 0 10px; }
  .gapnote { font-size: 12.5px; line-height: 1.55; color: #24382f;
             border-left: 3px solid #a3402d; padding: 6px 10px; background: #f7efea; }
  table { width: 100%; border-collapse: collapse; }
  td { border-bottom: 1px solid #e7dcc4; padding: 7px 6px; vertical-align: top; }
  /* A row must not be split across a page: half a requirement on each side of
     a break is how a reader misses the half that mattered. */
  tr { break-inside: avoid; page-break-inside: avoid; }
  .mark { width: 20px; text-align: center; font-size: 14px; }
  .mark span { display: inline-block; width: 17px; height: 17px; line-height: 17px;
               border-radius: 999px; font-size: 11px; }
  .ok .mark span { background: #e1ebe1; color: #4f7d5c; }
  .warn .mark span { background: #f3e6c4; color: #8a6113; }
  .stop .mark span { background: #f1ddd3; color: #a3402d; }
  .gap .mark span { background: #eee8d8; color: #5b6459; }
  .area { font-size: 9px; letter-spacing: .09em; text-transform: uppercase;
          color: #5b6459; margin: 0 0 2px; }
  .title { font-size: 13.5px; font-weight: 600; margin: 0; }
  .detail { font-size: 12.5px; line-height: 1.5; margin: 3px 0 0; }
  .why { font-size: 11px; color: #5b6459; margin: 3px 0 0; font-style: italic; }
  .state { width: 128px; font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
           color: #5b6459; text-align: right; }
  .refs { display: block; font-family: ui-monospace, monospace; color: #2f4a63; margin-top: 3px; }
  ol { list-style: none; padding: 0; }
  ol li { display: flex; gap: 8px; padding: 6px 0; border-bottom: 1px solid #e7dcc4;
          font-size: 13px; break-inside: avoid; }
  .step-n { flex: none; width: 17px; height: 17px; line-height: 17px; text-align: center;
            border-radius: 999px; background: #2f4a63; color: #f5eedd; font-size: 10px; }
  ol em { display: block; font-size: 10px; letter-spacing: .06em; text-transform: uppercase;
          color: #5b6459; font-style: normal; margin-top: 2px; }
  article { break-inside: avoid; margin-bottom: 12px; }
  h4 { font-size: 12px; font-family: ui-monospace, monospace; margin: 0 0 3px; }
  h4 .n { display: inline-block; width: 16px; height: 16px; line-height: 16px; text-align: center;
          border-radius: 2px; background: #2f4a63; color: #f5eedd; font-size: 10px; margin-right: 5px; }
  .ex { font-size: 11.5px; line-height: 1.5; color: #24382f; margin: 0; }
  .disc { margin-top: 28px; font-size: 11px; line-height: 1.55; color: #5b6459;
          border-top: 1px solid #ddceac; padding-top: 10px; }
</style></head><body>
  <p class="kicker">IP-SAKTI Sahayak &middot; export readiness</p>
  <h1>${escapeHtml(report.product)}</h1>
  <p class="route">India <strong>&rarr;</strong> ${escapeHtml(report.target_country)}</p>

  ${
    cls
      ? `<h2>Product classification</h2>
         <p class="detail"><strong>${escapeHtml(cls.label ?? cls.category)}</strong>
         &mdash; ${escapeHtml(cls.rationale ?? "")}</p>`
      : ""
  }
  ${
    report.target_framing
      ? `<p class="detail">In the target market's own instruments:
         ${escapeHtml(report.target_framing)}</p>`
      : ""
  }

  ${sectionBlock(report.india, index)}
  ${sectionBlock(report.target, index)}

  ${plan ? `<h2>What to do next</h2><ol>${plan}</ol>` : ""}

  ${sources ? `<h2>Sources, verbatim</h2>${sources}` : ""}

  <p class="disc">${escapeHtml(report.disclaimer)}</p>
  <p class="disc">Every line above is either backed by a numbered source printed in
  full at the end of this sheet, or marked as not covered by them. Nothing here was
  written from memory.</p>
  <script>window.opener = null; window.onload = () => window.print();</script>
</body></html>`;

  // `noopener` is deliberately NOT in the features string, and it must not be
  // added back. window.open() returns **null** when noopener is set, so the
  // handle we need in order to write the sheet never arrives - the tab opens
  // blank and the `if (!win)` guard below swallows it silently. Measured in
  // Chromium: with "noopener,noreferrer" -> null; without -> a handle.
  //
  // The security property noopener exists to give is preserved a different way:
  // the document is one we compose ourselves, it loads nothing external, and it
  // severs its own `window.opener` on load before anything else runs.
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(html);
  win.document.close();
}
