/**
 * The path to a human IP facilitator.
 *
 * Shown only when the backend sets `escalate` — which it does for a real legal
 * need this system cannot meet (a foreign-jurisdiction question, an in-scope
 * question with no grounding, an answer resting on thin support), and never for
 * a vague question, an off-topic one, or a transient outage. See
 * `backend/app/escalation.py` for why the negative cases matter as much.
 *
 * Deliberately styled as a quiet next step in indigo (the sources hue), not as
 * an alarm in clay. Reaching a person is a normal continuation of the work, not
 * a failure state — and clay already means "we did not answer", which would
 * read as the system apologising for itself twice in one panel.
 */
export function Escalate({ reason }: { reason: string | null }) {
  // A real deployment routes this to an actual facilitator queue. Until that
  // exists, the honest affordance is a prefilled email rather than a button
  // that pretends to file something.
  const subject = encodeURIComponent("IP-SAKTI Sahayak — request for a human review");
  const body = encodeURIComponent(
    "I used IP-SAKTI Sahayak and would like a practitioner to look at my question.\n\n" +
      "My question:\n\n\n" +
      "What the assistant said:\n\n\n",
  );

  return (
    <div className="mt-4 border-l-[3px] border-indigo-dye bg-indigo-wash px-4 py-3">
      <p className="eyebrow text-indigo-dye">Talk to a person</p>
      {reason && (
        <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">{reason}</p>
      )}
      <a
        href={`mailto:?subject=${subject}&body=${body}`}
        className="mt-2.5 inline-flex items-center gap-1.5 text-[13px] font-medium text-indigo-dye underline decoration-indigo-dye/30 underline-offset-4 transition hover:decoration-indigo-dye"
      >
        Request a human IP facilitator
        <span aria-hidden="true">→</span>
      </a>
      <p className="mt-2 text-[12px] leading-relaxed text-ink-faint">
        This opens an email draft. No question is sent anywhere automatically.
      </p>
    </div>
  );
}
