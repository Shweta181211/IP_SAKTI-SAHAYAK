"""When to offer a human IP facilitator.

The problem statement asks for "a path to escalate to a human IP facilitator".
The interesting part is not the affordance - it is deciding *when* to offer it,
because an escalation prompt on every answer is noise that trains people to
ignore it, and one that never appears is not a path at all.

The rule here: offer a human exactly when the user has a **real legal need this
system cannot meet**. That is a narrower set than "we did not answer".

Worth reading the negative cases, because they carry the reasoning:

  * `too_vague` - nothing to escalate yet. The user has not asked a question;
    they need to say more, not talk to a lawyer.
  * `out_of_scope` - not a legal question at all (a recipe, marketing advice).
    Offering an IP facilitator for a chocolate cake is absurd, and it would make
    every other escalation offer look equally thoughtless.
  * `gate_unavailable` - a transient outage. The right advice is "try again in a
    moment", and sending someone to a human because our provider hiccuped wastes
    their time and the facilitator's.
  * `conversational` - small talk.

And the positive ones:

  * `foreign_jurisdiction` - a genuine legal need we are structurally unable to
    serve. The corpus is Indian law; the question is not. This is the clearest
    case for a human there is.
  * `no_evidence` - in scope, and we could not ground an answer. Exactly the gap
    a person fills.
  * answered, but `LIMITED` confidence - thin support. The answer stands and is
    cited, but a practitioner should confirm it before it is relied on.
"""

from __future__ import annotations

from .schemas import AbstentionKind, ConfidenceLevel

# A refusal that reflects a real legal need we cannot serve, rather than a
# question that was malformed, off-topic, or hit a transient failure.
ESCALATE_ON_ABSTENTION = {
    AbstentionKind.FOREIGN_JURISDICTION,
    AbstentionKind.NO_EVIDENCE,
}

REASONS = {
    AbstentionKind.FOREIGN_JURISDICTION: (
        "This question is governed by law outside this corpus. A practitioner who works "
        "across jurisdictions can advise on it directly."
    ),
    AbstentionKind.NO_EVIDENCE: (
        "This is within scope, but the corpus did not contain a provision that answers it. "
        "A qualified IP practitioner can look beyond these sources."
    ),
}

LIMITED_CONFIDENCE_REASON = (
    "This answer rests on thin support - check the sources below. A qualified IP "
    "practitioner should confirm it before you act on it."
)


def assess(
    abstained: bool,
    kind: AbstentionKind,
    confidence: ConfidenceLevel | None,
) -> tuple[bool, str | None]:
    """Return (offer a human, why). Never raises."""
    if abstained:
        if kind in ESCALATE_ON_ABSTENTION:
            return True, REASONS.get(kind)
        return False, None

    if confidence is ConfidenceLevel.LIMITED:
        return True, LIMITED_CONFIDENCE_REASON

    return False, None
