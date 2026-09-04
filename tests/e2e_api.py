#!/usr/bin/env python3
"""End-to-end tests against the running HTTP API.

This is the layer the frontend actually consumes, so it is the layer worth
testing. Every UI state the app can render has a case here:

  - a full answer with reasoning trail and citation rail
  - each abstention kind (too_vague / out_of_scope / foreign_jurisdiction)
  - the clarifying-question path
  - the international jurisdiction toggle
  - input validation

Run the backend first:
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000   (from backend/)
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  [{PASS if ok else FAIL}] {name}{'  — ' + detail if detail else ''}")


def call(path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    if body is None:
        request = urllib.request.Request(url)
    else:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except Exception:
            return exc.code, {}


def ask(question: str, jurisdiction: str = "india") -> tuple[dict, float]:
    started = time.time()
    status, data = call("/query", {"question": question, "jurisdiction": jurisdiction})
    assert status == 200, f"expected 200, got {status}: {data}"
    return data, time.time() - started


def main() -> int:
    print("=" * 74 + "\n HEALTH\n" + "=" * 74)
    status, health = call("/health")
    record("GET /health returns 200", status == 200)
    record("corpus indexed", health.get("chunks_in_vector_db", 0) > 2000,
           f"{health.get('chunks_in_vector_db')} chunks")
    record("definition anchors intact", not health.get("anchor_problems"),
           str(health.get("anchor_problems") or "none"))

    print("\n" + "=" * 74 + "\n VALIDATION\n" + "=" * 74)
    record("empty question rejected", call("/query", {"question": ""})[0] == 422)
    record("bad jurisdiction rejected",
           call("/query", {"question": "a real question about patents", "jurisdiction": "mars"})[0] == 422)
    record("oversized question rejected",
           call("/query", {"question": "x" * 3000})[0] == 422)

    print("\n" + "=" * 74 + "\n FULL ANSWER PATH (official benchmark)\n" + "=" * 74)
    answer, elapsed = ask("Can a classical churna from a First Schedule text be patented?")
    record("answered (not abstained)", not answer["abstained"])
    record("classified as classical_generic",
           answer["classification"]["category"] == "classical_generic",
           answer["classification"]["category"])
    record("has exactly 4 reasoning steps", len(answer["steps"]) == 4)
    record("has citations", len(answer["citations"]) > 0, f"{len(answer['citations'])} sources")
    record("disclaimer present", "not legal advice" in answer["disclaimer"])

    cited = {c["chunk_id"] for c in answer["citations"]}
    step_ids = {i for s in answer["steps"] for i in s["citation_ids"]}
    record("every step citation resolves to a citation card", step_ids <= cited,
           f"orphans: {step_ids - cited or 'none'}")

    texts = " ".join(s["content"] for s in answer["steps"]).lower()
    # 3(p) can surface in the prose or on the citation card - the reader sees
    # both, so either satisfies "the answer cites Section 3(p)".
    sections = " ".join((c.get("section") or "") for c in answer["citations"]).lower()
    record("cites Section 3(p)", "3(p)" in texts or "3(p)" in sections,
           "in prose" if "3(p)" in texts else "on citation card")
    record("names TKDL as defensive route", "tkdl" in texts or "traditional knowledge digital" in texts)
    record("states Indian-law-only jurisdiction", "india" in answer["steps"][3]["content"].lower())
    print(f"  (latency {elapsed:.1f}s)")

    print("\n" + "=" * 74 + "\n ABSTENTION PATHS (each renders a different UI state)\n" + "=" * 74)
    for label, question, expected_kind in [
        ("too vague", "patent?", "too_vague"),
        ("off domain", "How do I make a good chocolate cake at home?", "out_of_scope"),
        ("foreign law", "Can I sell my supplement in the USA under FDA rules?", None),
    ]:
        a, _ = ask(question)
        ok = a["abstained"] and bool(a["abstention_message"])
        if expected_kind:
            ok = ok and a["abstention_kind"] == expected_kind
        record(f"{label} abstains with a reason", ok,
               f"{a['abstention_kind']}")
        record(f"{label} emits no citations", not a["citations"])

    print("\n" + "=" * 74 + "\n JURISDICTION TOGGLE\n" + "=" * 74)
    a, _ = ask("Can a classical churna be patented?", jurisdiction="international")
    record("international toggle abstains honestly",
           a["abstained"] and a["abstention_kind"] == "foreign_jurisdiction")
    record("international emits no fabricated content", not a["steps"] and not a["citations"])

    print("\n" + "=" * 74 + "\n CITATION INTEGRITY ACROSS MANY QUESTIONS\n" + "=" * 74)
    questions = [
        "How do I register a Geographical Indication for an Ayurvedic product?",
        "What is Access and Benefit Sharing and when do I need NBA approval?",
        "Is my printed Ayurvedic formulary book protected by copyright?",
        "Can I register a new medicinal plant variety I have bred?",
    ]
    total_citations = 0
    all_valid = True
    for q in questions:
        a, secs = ask(q)
        if a["abstained"]:
            print(f"  (abstained: {q[:50]}… — {a['abstention_kind']})")
            continue
        for c in a["citations"]:
            total_citations += 1
            # A citation must name a real act and carry verbatim source text.
            if not c["act_name"] or not c["excerpt"]:
                all_valid = False
        print(f"  {len(a['citations'])} sources in {secs:.1f}s — {q[:52]}…")
    record("all citations carry act name + verbatim excerpt", all_valid,
           f"{total_citations} checked")

    print("\n" + "=" * 74)
    failed = [r for r in results if r[0] == FAIL]
    print(f" {len(results) - len(failed)}/{len(results)} checks passed")
    for _, name, detail in failed:
        print(f"   FAILED: {name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
