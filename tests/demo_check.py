#!/usr/bin/env python3
"""Pre-demo readiness check and cache warm-up.

Run this ten minutes before demoing. It does three things:

1. **Verifies the system is actually healthy** - corpus indexed, definition
   anchors resolving, both models reachable.
2. **Warms the answer cache** with the questions you plan to ask, so they return
   in milliseconds instead of ~20 seconds in front of an audience.
3. **Fails loudly** if the flagship benchmark does not produce Section 3(p) and
   TKDL, so you find out here rather than on stage.

    .venv\\Scripts\\python.exe tests\\demo_check.py

The cache lives in the server process, so warm-up only helps while that same
process keeps running. Do not restart the backend after warming it.
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

# The questions to warm, in the order you would demo them. Each one shows a
# different capability, so this doubles as a running order.
DEMO_SCRIPT: list[tuple[str, str]] = [
    ("THE FLAGSHIP — classification + Section 3(p) + TKDL",
     "Can a classical churna from a First Schedule text be patented?"),
    ("A different regime — shows it is not one hardcoded answer",
     "How do I register a Geographical Indication for an Ayurvedic product?"),
    ("ABS / biodiversity",
     "What is Access and Benefit Sharing and when do I need NBA approval?"),
    ("Refuses a false premise, and cites while doing it",
     "Cite the exact section that ALLOWS patenting a classical churna."),
    ("Knows where its knowledge stops — wrong country",
     "Can I sell my ayurvedic supplement in the USA under FDA rules?"),
    ("Knows where its knowledge stops — wrong subject",
     "How do I make a good chocolate cake at home?"),
]

FOLLOW_UP = ("Follow-up memory — ask this AFTER the flagship",
             "what about trademarking it?",
             ["Can a classical churna from a First Schedule text be patented?"])


def call(path: str, body: dict | None = None, timeout: int = 300):
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def main() -> int:
    problems: list[str] = []

    print("=" * 72)
    print(" 1. HEALTH")
    print("=" * 72)
    try:
        health = call("/health")
    except urllib.error.URLError as exc:
        print(f"  BACKEND IS NOT RUNNING ({exc})")
        print("  Start it:  cd backend && ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000")
        return 1

    print(f"  corpus indexed   : {health['chunks_in_vector_db']} chunks")
    print(f"  embedding model  : {health['embed_model']}")
    print(f"  generation model : {health['generation_model']}")
    if health["anchor_problems"]:
        problems.append(f"definition anchors broken: {health['anchor_problems']}")
        print(f"  ANCHOR PROBLEMS  : {health['anchor_problems']}")
    else:
        print("  definition anchors: all resolving")
    if health["chunks_in_vector_db"] < 2000:
        problems.append("vector DB looks under-populated")

    print()
    print("=" * 72)
    print(" 2. WARMING THE CACHE  (this is the slow part — let it finish)")
    print("=" * 72)
    for label, question in DEMO_SCRIPT:
        started = time.time()
        try:
            answer = call("/query", {"question": question, "jurisdiction": "india"})
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{label}: request failed ({exc})")
            print(f"  FAILED  {label}\n          {exc}")
            continue
        elapsed = time.time() - started
        verdict = f"abstains ({answer['abstention_kind']})" if answer["abstained"] \
            else f"{len(answer['citations'])} sources"
        print(f"  {elapsed:5.1f}s  {verdict:24s} {label}")

    started = time.time()
    label, question, history = FOLLOW_UP
    try:
        answer = call("/query", {"question": question, "jurisdiction": "india", "history": history})
        print(f"  {time.time() - started:5.1f}s  understood as: "
              f"{(answer.get('resolved_question') or question)[:56]}")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"follow-up failed: {exc}")

    print()
    print("=" * 72)
    print(" 3. FLAGSHIP ASSERTIONS")
    print("=" * 72)
    flagship = call("/query", {"question": DEMO_SCRIPT[0][1], "jurisdiction": "india"})
    surface = " ".join(s["content"] for s in flagship.get("steps", [])).lower()
    surface += " " + " ".join((c.get("section") or "") for c in flagship.get("citations", [])).lower()

    checks = [
        ("classified as classical_generic",
         (flagship.get("classification") or {}).get("category") == "classical_generic"),
        ("cites Section 3(p)", "3(p)" in surface),
        ("names TKDL", "tkdl" in surface or "traditional knowledge digital" in surface),
        ("has 4 reasoning steps", len(flagship.get("steps", [])) == 4),
        ("every citation is a real chunk", all(c.get("chunk_id") for c in flagship.get("citations", []))),
        ("disclaimer present", "not legal advice" in (flagship.get("disclaimer") or "")),
    ]
    for name, ok in checks:
        print(f"  [{'OK  ' if ok else 'FAIL'}] {name}")
        if not ok:
            problems.append(f"flagship: {name}")

    print()
    print("=" * 72)
    if problems:
        print(f" NOT READY — {len(problems)} problem(s):")
        for problem in problems:
            print(f"   - {problem}")
        return 1

    print(" READY. Cached questions now answer instantly.")
    print(" Do NOT restart the backend, or the cache is lost.")
    print()
    print(" Suggested running order:")
    for i, (label, question) in enumerate(DEMO_SCRIPT, 1):
        print(f"   {i}. {label}")
        print(f"      \"{question}\"")
    print(f"   {len(DEMO_SCRIPT) + 1}. {FOLLOW_UP[0]}")
    print(f"      \"{FOLLOW_UP[1]}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
