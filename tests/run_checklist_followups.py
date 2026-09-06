"""Follow-up probes after the Gemini full run.

Three things the main run left open or raised:
  * T18-07 / T18-09 refused trademark and copyright questions claiming the corpus
    lacks them. It does not. Re-ask standalone to see whether history caused it.
  * T20 could not test confidence calibration because TRIPS is correctly refused as
    a treaty question. Substitute an IN-SCOPE question with known-thin evidence
    (CLAUDE.md 6b: the statutory definition of "phytopharmaceutical" is NOT in the
    corpus - r.2(eb) was never captured).
  * A repeat of a strong question, to compare confidence on strong vs thin evidence.
"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")
from run_tests import ask, record, post, results, OUT  # noqa: E402

import json  # noqa: E402


def main():
    # Are the trademark / copyright refusals caused by conversation history?
    ask("F1", "followup", "Trademark question, STANDALONE (no history)",
        "Can I trademark the name of my Ayurvedic product?")
    ask("F2", "followup", "Copyright question, STANDALONE (no history)",
        "Can I copyright the text of my Ayurvedic formulation booklet?")
    # More explicit phrasing, still standalone.
    ask("F3", "followup", "Trademark, naming the statute",
        "What does the Trade Marks Act 1999 say about registering the name of an Ayurvedic medicine?")
    ask("F4", "followup", "Copyright, naming the statute",
        "What does the Copyright Act 1957 protect in a written Ayurvedic formulation book?")

    # T20 substitute: in-scope, known-thin evidence.
    ask("T20alt", "6", "Confidence on a KNOWN corpus gap (in-scope)",
        "What is the statutory definition of a phytopharmaceutical drug in the Drugs and Cosmetics Rules?")

    # The vagueness guard, isolated from any model behaviour.
    for q in ["What is a Geographical Indication?", "What is ABS?"]:
        record("VAG-" + q[:12], "followup", "Short but well-formed question", q,
               post("/query", {"question": q, "history": [], "jurisdiction": "india"}))

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print("\nWROTE %s with %d entries" % (OUT, len(results)))


if __name__ == "__main__":
    main()
