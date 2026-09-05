"""Append-only audit trail for answers the system gave.

The problem statement asks for auditability and DPDP-aligned handling of user
data. Those two pull in opposite directions - an audit trail wants to record
what happened, data protection wants to retain as little as possible - so this
module separates them rather than picking one.

**Two tiers, and the split is the whole design:**

  * The **operational record** is always written. It carries no user content at
    all: a timestamp, what the system decided, how many sources survived
    validation, how long it took, which model answered. That is enough to
    reconstruct system behaviour - "did it abstain more after we changed the
    gate?", "how often is a citation rejected?" - which is what auditability
    actually needs.
  * The **question text** is written ONLY when the caller passes explicit
    consent. It is the one field that is personal data, and it is the one field
    the operational record can do without.

The teammate's `log_interaction()` (Version B) logged the question by default
under a single consent flag. This keeps her structure - one JSONL line per
interaction, consent-gated, local file, never blocking - and tightens the
default, because "audit the system" does not require storing what people asked.

Deliberate limits, stated rather than hidden:
  * Local file, no access control. Fine for a local demo, NOT production.
    A real deployment needs storage with access control and a retention policy.
  * A hash of the question is stored so repeat questions can be counted without
    retaining the text. It is a fingerprint, not an anonymisation scheme: a
    short question drawn from a small set could be recovered by brute force.
  * Logging must NEVER break an answer. Every failure here is swallowed.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ROOT, settings
from .schemas import Answer, ComparisonResult

logger = logging.getLogger(__name__)

AUDIT_PATH: Path = ROOT / "data" / "logs" / "audit_log.jsonl"

# Rotate rather than grow without bound. A demo will never reach this; a loop
# pointed at the API would, and a log that fills a disk is its own outage.
MAX_BYTES = 5 * 1024 * 1024

_LOCK = threading.Lock()


def _fingerprint(text: str) -> str:
    """Short stable hash, so repeats can be counted without keeping the text."""
    normalised = " ".join(text.lower().split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def _rotate_if_needed() -> None:
    try:
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size > MAX_BYTES:
            AUDIT_PATH.replace(AUDIT_PATH.with_suffix(".jsonl.1"))
    except OSError:
        pass


def _write(entry: dict[str, Any]) -> None:
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            _rotate_if_needed()
            with AUDIT_PATH.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - an audit failure must not break an answer
        logger.warning("Audit write failed", exc_info=True)


def never_fails(fn):
    """Swallow anything this function raises.

    The guard was originally only around the file write, which covered a full
    disk but not a malformed entry - and building the entry touches a dozen
    attributes of a model object. An audit trail is a nice-to-have; the answer
    is not. Nothing in this module may ever propagate.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - logging must never break an answer
            logger.warning("Audit logging failed for %s", fn.__name__, exc_info=True)

    return wrapper


@never_fails
def log_answer(
    question: str,
    answer: Answer,
    *,
    consent: bool = False,
    elapsed_s: float | None = None,
) -> None:
    """Record one answered (or refused) question."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "query",
        "question_id": _fingerprint(question),
        "question_chars": len(question),
        # --- what the system decided -------------------------------------
        "abstained": answer.abstained,
        "abstention_kind": answer.abstention_kind.value,
        "category": answer.classification.category.value if answer.classification else None,
        "confidence": answer.confidence.value if answer.confidence else None,
        "confidence_score": answer.confidence_score,
        # --- how well it held together -----------------------------------
        "citations": len(answer.citations),
        "rejected_citations": len(answer.rejected_citation_ids),
        "steps_abstained": sum(1 for s in answer.steps if s.abstained),
        "headline_unsourced": answer.headline_unsourced,
        "search_degraded": answer.search_degraded,
        "escalate": answer.escalate,
        # --- provenance ---------------------------------------------------
        "model": settings.model,
        "elapsed_s": round(elapsed_s, 2) if elapsed_s is not None else None,
    }
    # The only personal-data field, and the only one gated on consent.
    if consent:
        entry["question"] = question
        entry["resolved_question"] = answer.resolved_question
    _write(entry)


@never_fails
def log_comparison(
    product: str,
    result: ComparisonResult,
    *,
    consent: bool = False,
    elapsed_s: float | None = None,
) -> None:
    """Record one category comparison."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "compare",
        "question_id": _fingerprint(product),
        "question_chars": len(product),
        "abstained": result.abstained,
        "contrasts": len(result.contrasts),
        "citations": len(result.citations),
        "search_degraded": result.search_degraded,
        "model": settings.model,
        "elapsed_s": round(elapsed_s, 2) if elapsed_s is not None else None,
    }
    if consent:
        entry["product"] = product
    _write(entry)


def summary(limit: int = 500) -> dict[str, Any]:
    """Aggregate the recent log. Used by /health so the trail is inspectable."""
    try:
        if not AUDIT_PATH.exists():
            return {"entries": 0, "path": str(AUDIT_PATH)}
        lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return {"entries": 0, "path": str(AUDIT_PATH)}

    total = answered = abstained = escalated = rejected = 0
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        if entry.get("abstained"):
            abstained += 1
        else:
            answered += 1
        if entry.get("escalate"):
            escalated += 1
        rejected += int(entry.get("rejected_citations") or 0)

    return {
        "entries": total,
        "answered": answered,
        "abstained": abstained,
        "escalated": escalated,
        "citations_rejected": rejected,
        "path": str(AUDIT_PATH),
    }
