#!/usr/bin/env python3
"""
run_eval.py -- Evaluation harness for IP Sakti Sahayak's national-scope RAG
pipeline.

Measures, against a small labelled set (eval_set.json):
  - retrieval hit-rate      : did the expected Act show up in the top-k?
  - citation correctness    : does every result carry a real Act/page cite?
  - safe abstention         : does an out-of-corpus question get "no match"
                               / low confidence instead of a guessed answer?
  - ABS/TKDL flag accuracy  : does the pointer fire exactly when expected?
  - EN vs HI breakdown      : are Hindi-language questions doing as well as
                               English ones (this is the metric that matters
                               most right now, since the international layer
                               and full Bhashini-based multilingual UI are
                               explicitly out of scope for this phase)?

This is a starting evaluation harness, not a certified benchmark -- extend
eval_set.json as real usage surfaces new query patterns and edge cases.

Usage:
    python3 run_eval.py
    python3 run_eval.py --eval-set eval_set.json --report eval_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import rag_engine  # noqa: E402


def _is_hindi(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def evaluate(eval_set: list[dict]) -> dict:
    rag_engine.load_backend()
    if not rag_engine.is_ready():
        raise SystemExit(
            f"Backend not ready: {rag_engine.status()['error']}\n"
            "Run: python3 build_vector_db.py --chunks all_chunks.json"
        )

    rows = []
    for case in eval_set:
        question = case["question"]
        result = rag_engine.answer_query(question, top_k=6, log_consent=False)
        acts = [r["metadata"].get("act_name", "").lower() for r in result["results"]]
        expect_acts = [a.lower() for a in case.get("expect_act_contains", [])]

        retrieval_hit = (
            True if not expect_acts
            else any(any(exp in act for act in acts) for exp in expect_acts)
        )
        citations_ok = all(
            r["metadata"].get("act_name") and r["metadata"].get("page_number") is not None
            for r in result["results"]
        )
        abstained_correctly = (
            result["confidence"] in ("low", "none") if case.get("expect_no_match") else True
        )
        answered_when_expected = (
            result["confidence"] in ("high", "medium") if not case.get("expect_no_match") else True
        )
        abs_flag_ok = result["abs_tkdl_flag"] == case.get("expect_abs_flag", False)

        rows.append({
            "id": case["id"],
            "question": question,
            "language": "hi" if _is_hindi(question) else "en",
            "confidence": result["confidence"],
            "retrieval_hit": retrieval_hit,
            "citations_ok": citations_ok,
            "abstained_correctly": abstained_correctly,
            "answered_when_expected": answered_when_expected,
            "abs_flag_ok": abs_flag_ok,
            "num_results": len(result["results"]),
        })

    def rate(rows_, key):
        return round(sum(1 for r in rows_ if r[key]) / len(rows_), 3) if rows_ else None

    overall = {
        "n": len(rows),
        "retrieval_hit_rate": rate(rows, "retrieval_hit"),
        "citation_correctness": rate(rows, "citations_ok"),
        "safe_abstention_rate": rate(rows, "abstained_correctly"),
        "answered_when_expected_rate": rate(rows, "answered_when_expected"),
        "abs_tkdl_flag_accuracy": rate(rows, "abs_flag_ok"),
    }
    by_lang = {}
    for lang in ("en", "hi"):
        lang_rows = [r for r in rows if r["language"] == lang]
        by_lang[lang] = {
            "n": len(lang_rows),
            "retrieval_hit_rate": rate(lang_rows, "retrieval_hit"),
            "safe_abstention_rate": rate(lang_rows, "abstained_correctly"),
        }

    return {"overall": overall, "by_language": by_lang, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-set", type=Path, default=REPO_ROOT / "eval_set.json")
    parser.add_argument("--report", type=Path, default=REPO_ROOT / "eval_report.json")
    args = parser.parse_args()

    eval_set = json.loads(args.eval_set.read_text(encoding="utf-8"))
    report = evaluate(eval_set)

    print("\n=== Overall ===")
    for k, v in report["overall"].items():
        print(f"  {k}: {v}")
    print("\n=== By language ===")
    for lang, stats in report["by_language"].items():
        print(f"  {lang}: {stats}")
    print("\n=== Per-question ===")
    for row in report["rows"]:
        flag = "OK " if (row["retrieval_hit"] and row["abstained_correctly"] and row["abs_flag_ok"]) else "!! "
        print(f"  {flag}[{row['language']}] {row['id']}: conf={row['confidence']} "
              f"hit={row['retrieval_hit']} abs_flag_ok={row['abs_flag_ok']} -> {row['question'][:60]}")

    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nFull report written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
