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

from .config import ROOT, active_model, settings
from .schemas import ExportReadinessReport, Answer, ComparisonResult

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
        "model": active_model(),
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
        "model": active_model(),
        "elapsed_s": round(elapsed_s, 2) if elapsed_s is not None else None,
    }
    if consent:
        entry["product"] = product
    _write(entry)


@never_fails
def log_readiness(
    product: str,
    report: "ExportReadinessReport",
    *,
    consent: bool = False,
    elapsed_s: float | None = None,
) -> None:
    """Record one export readiness report.

    The target country is retained even without consent: it is not user content
    in the way a question is - it is a market name, and knowing which markets
    are asked for is the operational fact that says where the corpus needs to
    grow next.
    """
    india = report.india.items if report.india else []
    target = report.target.items if report.target else []
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "export_readiness",
        "question_id": _fingerprint(product),
        "question_chars": len(product),
        "target_country": report.target_country,
        "abstained": report.abstained,
        "india_items": len(india),
        "target_items": len(target),
        "target_covered": bool(report.target and report.target.covered),
        "blockers": sum(1 for i in india + target if i.status.value == "blocker"),
        "not_covered": sum(1 for i in india + target if i.status.value == "not_covered"),
        "citations": len(report.citations),
        "citations_rejected": len(report.rejected_citation_ids),
        "confidence": report.confidence.value if report.confidence else None,
        "escalated": report.escalate,
        "model": active_model(),
        "elapsed_s": round(elapsed_s, 2) if elapsed_s is not None else None,
    }
    if consent:
        entry["product"] = product
    _write(entry)


# Fields that carry user content. They exist in the log only when the caller
# consented, and they are removed again on the way OUT, so the inspectable
# trail is the operational record and nothing else. Two gates rather than one:
# consent decides what is written, this decides what is served.
PERSONAL_FIELDS = ("question", "resolved_question", "product")


def _entries(limit: int) -> list[dict[str, Any]]:
    """Parse the tail of the log. Never raises - a missing log is zero entries."""
    try:
        if not AUDIT_PATH.exists():
            return []
        lines = AUDIT_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def recent(limit: int = 40) -> list[dict[str, Any]]:
    """The most recent entries, newest first, with user content removed.

    This is what makes auditability demonstrable rather than asserted: a reader
    can see the actual rows the system wrote about its own behaviour. What they
    cannot see is what anybody asked, because that is stripped here even when it
    was consented into the file. Consent decides what is written; this decides
    what is served, and the second gate is the one a reader is standing behind.
    """
    rows = _entries(max(limit, 1))[-limit:]
    return [
        {k: v for k, v in row.items() if k not in PERSONAL_FIELDS}
        for row in reversed(rows)
    ]


def summary(limit: int = 500) -> dict[str, Any]:
    """Aggregate the recent log. Used by /health so the trail is inspectable."""
    rows = _entries(limit)
    if not rows:
        return {"entries": 0, "path": str(AUDIT_PATH), "retained_question_text": 0}

    total = answered = abstained = escalated = rejected = consented = 0
    kinds: dict[str, int] = {}
    reasons: dict[str, int] = {}
    # Which endpoint actually served each request. This is the only honest
    # evidence that the fallback chain is load-bearing rather than decorative:
    # more than one model in this breakdown means the chain really did move
    # when a provider capped out, and nobody had to be told it did.
    models: dict[str, int] = {}
    for entry in rows:
        total += 1
        kind = str(entry.get("kind") or "query")
        kinds[kind] = kinds.get(kind, 0) + 1
        if entry.get("abstained"):
            abstained += 1
            reason = entry.get("abstention_kind")
            if reason and reason != "none":
                reasons[str(reason)] = reasons.get(str(reason), 0) + 1
        else:
            answered += 1
        if entry.get("escalate"):
            escalated += 1
        rejected += int(entry.get("rejected_citations") or 0)
        if any(field in entry for field in PERSONAL_FIELDS):
            consented += 1
        served = entry.get("model")
        if served:
            models[str(served)] = models.get(str(served), 0) + 1

    return {
        "entries": total,
        "answered": answered,
        "abstained": abstained,
        "escalated": escalated,
        "citations_rejected": rejected,
        # How many of these rows kept the question text. Zero unless someone
        # opted in, which is the claim the consent design is making - and it is
        # a count rather than a flag so it can be checked, not just believed.
        "retained_question_text": consented,
        "kinds": kinds,
        "abstention_kinds": reasons,
        "models": models,
        "first_entry": rows[0].get("ts"),
        "last_entry": rows[-1].get("ts"),
        "path": str(AUDIT_PATH),
    }
