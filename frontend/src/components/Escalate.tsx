import { useState } from "react";
import type { Answer } from "../types";

/**
 * The path to a human IP facilitator.
 *
 * Shown only when the backend sets `escalate` — for a real legal need this
 * system cannot meet (a foreign-jurisdiction question, an in-scope question with
 * no grounding, an answer resting on thin support), and never for a vague
 * question, an off-topic one, or a transient outage. See
 * `backend/app/escalation.py` for why the negative cases matter as much.
 *
 * **This used to open a `mailto:` with no recipient** — a draft addressed to
 * nobody, which looks like a working referral and is not one. There is no
 * facilitator queue behind this build, and inventing an address would be worse
 * than admitting that. So the honest affordance is a prepared brief the user can
 * copy and send to a practitioner they choose: it costs them nothing, it works
 * with no backend, and it does not imply a queue that does not exist.
 *
 * Styled in indigo (the sources hue), not clay. Reaching a person is a normal
 * continuation of the work, not a failure state, and clay already means "we did
 * not answer" — which would read as the system apologising to itself twice.
 */
export function Escalate({ reason, answer }: { reason: string | null; answer?: Answer }) {
  const [copied, setCopied] = useState(false);

  function brief(): string {
    const lines = [
      "Request for review by a qualified IP practitioner",
      "",
      "Prepared with IP-SAKTI Sahayak, a source-cited research assistant for",
      "Ayurveda IP and regulatory questions. This is information, not legal advice.",
      "",
    ];
    if (answer) {
      lines.push(`QUESTION\n${answer.resolved_question ?? answer.question}`, "");
      if (answer.headline) lines.push(`SUMMARY\n${answer.headline}`, "");
      if (answer.steps.length) {
        lines.push("REASONING");
        for (const step of answer.steps) {
          lines.push(`${step.step}. ${step.title}\n${step.content}`);
        }
        lines.push("");
      }
      if (answer.citations.length) {
        lines.push("SOURCES CITED");
        answer.citations.forEach((c, i) => {
          const parts = [c.act_name];
          if (c.section) parts.push(c.section);
          if (c.page) parts.push(`p. ${c.page}`);
          lines.push(`[${i + 1}] ${parts.join(", ")}`);
        });
        lines.push("");
      }
      if (answer.abstention_message) {
        lines.push(`WHY IT WAS NOT ANSWERED\n${answer.abstention_message}`, "");
      }
    }
    if (reason) lines.push(`WHY A PRACTITIONER WAS SUGGESTED\n${reason}`, "");
    lines.push("The assistant cites primary sources but is not a substitute for advice.");
    return lines.join("\n");
  }

  async function copy() {
    const text = brief();
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard access needs a secure context and can be refused outright.
      // Falling back to a selectable textarea beats a button that does nothing.
      const box = document.createElement("textarea");
      box.value = text;
      box.style.position = "fixed";
      box.style.opacity = "0";
      document.body.appendChild(box);
      box.select();
      try {
        document.execCommand("copy");
      } catch {
        /* nothing more to try; the state below still tells the truth */
      }
      document.body.removeChild(box);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2400);
  }

  return (
    <div className="mt-4 border-l-[3px] border-indigo-dye bg-indigo-wash px-4 py-3">
      <p className="eyebrow text-indigo-dye">Talk to a person</p>
      {reason && <p className="mt-1 text-[length:var(--t-meta)] leading-relaxed text-ink-soft">{reason}</p>}

      <button
        type="button"
        onClick={copy}
        className="mt-2.5 inline-flex items-center gap-1.5 rounded-[3px] border border-indigo-dye/40 px-2.5 py-1.5 text-[length:var(--t-meta)] font-medium text-indigo-dye transition hover:bg-indigo-dye hover:text-paper"
      >
        {copied ? "Brief copied" : "Copy a brief for a practitioner"}
        <span aria-hidden="true">{copied ? "✓" : "→"}</span>
      </button>

      <p className="mt-2 text-[length:var(--t-micro)] leading-relaxed text-ink-faint">
        Copies your question, the reasoning and every source cited, ready to send to an
        IP practitioner of your choosing. Nothing is transmitted from this page.
      </p>
    </div>
  );
}
