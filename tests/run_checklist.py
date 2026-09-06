"""Automated run of MANUAL_TEST_CHECKLIST.md against the live API.

Calls the real HTTP endpoints (no browser, no mocks) and dumps every raw
response to JSON so the verdicts can be written from actual output.

Conversation tests replicate exactly what App.tsx does: history is the list of
`resolved_question ?? question` from prior ANSWER turns, oldest first.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
OUT = sys.argv[1] if len(sys.argv) > 1 else "results.json"
ONLY = sys.argv[2] if len(sys.argv) > 2 else None

results: list[dict] = []


def post(path: str, payload: dict, timeout: float = 300.0) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path, data=body, headers={"Content-Type": "application/json"}
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "http_status": resp.status,
                "elapsed_s": round(time.time() - started, 2),
                "json": json.loads(resp.read().decode()),
            }
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return {
            "http_status": e.code,
            "elapsed_s": round(time.time() - started, 2),
            "json": parsed,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "http_status": None,
            "elapsed_s": round(time.time() - started, 2),
            "error": "%s: %s" % (type(e).__name__, e),
        }


def get_raw(path: str, timeout: float = 30.0) -> dict:
    """GET without URL re-encoding, so %2f survives to the server."""
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return {
                "http_status": resp.status,
                "content_type": resp.headers.get("content-type"),
                "bytes": len(data),
                "body_head": data[:300].decode(errors="replace"),
            }
    except urllib.error.HTTPError as e:
        data = e.read()
        return {
            "http_status": e.code,
            "content_type": e.headers.get("content-type"),
            "bytes": len(data),
            "body_head": data[:300].decode(errors="replace"),
        }
    except Exception as e:  # noqa: BLE001
        return {"http_status": None, "error": "%s: %s" % (type(e).__name__, e)}


def record(test_id, category, label, question, response, extra=None):
    entry = {
        "test_id": test_id,
        "category": category,
        "label": label,
        "question": question,
        "response": response,
    }
    if extra:
        entry.update(extra)
    results.append(entry)
    j = response.get("json") if isinstance(response, dict) else None
    if isinstance(j, dict):
        cls = (j.get("classification") or {}).get("category")
        summary = (
            "status=%s cat=%s abstained=%s/%s conf=%s cites=%s %ss"
            % (
                response.get("http_status"), cls, j.get("abstained"),
                j.get("abstention_kind"), j.get("confidence"),
                len(j.get("citations") or []), response.get("elapsed_s"),
            )
        )
    else:
        summary = "status=%s %ss" % (response.get("http_status"), response.get("elapsed_s"))
    print("[%s] %s" % (test_id, summary), flush=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)


def ask(test_id, category, label, question, history=None, jurisdiction="india"):
    payload = {
        "question": question,
        "history": history or [],
        "jurisdiction": jurisdiction,
        "top_k": 12,
    }
    resp = post("/query", payload)
    record(test_id, category, label, question, resp,
           {"history_sent": history or [], "jurisdiction_sent": jurisdiction})
    return resp


def hist_entry(resp):
    j = resp.get("json") or {}
    if not isinstance(j, dict):
        return None
    return j.get("resolved_question") or j.get("question")


# ---------------------------------------------------------------- test plan

def run_all():
    # ---------- Category 1
    r1 = ask("T1", "1", "Official benchmark - classical churna patentability",
             "Can a classical churna from a First Schedule text be patented?")
    h = [x for x in [hist_entry(r1)] if x]
    ask("T1b", "1", "Follow-up: what about internationally?",
        "What about internationally?", history=h)

    # ---------- Category 2
    c2 = [
        ("T2", "I want to patent my grandmother's classical Ayurvedic churna recipe from an old text."),
        ("T3", "I've created a brand new proprietary Ayurvedic tonic with my own formula, never published anywhere."),
        ("T4", "I've developed a new herbal compound and I have clinical trial data proving it works."),
        ("T5", "I have a standardized extract from a single plant with a defined chemical marker."),
        ("T6", "I'm launching a turmeric-based health drink as a food supplement, not a medicine."),
        ("T7", "I've made a neem-based face cream for external use only."),
    ]
    for tid, q in c2:
        ask(tid, "2", "Classification category check", q)

    # ---------- Category 3
    c3 = [
        ("T8", "What is Access and Benefit Sharing and when do I need NBA approval?"),
        ("T9", "How do I register a Geographical Indication for an Ayurvedic product?"),
        ("T10", "What is TKDL and how does it protect traditional knowledge?"),
        ("T11", "What's the difference between a trademark and a GI tag?"),
    ]
    for tid, q in c3:
        ask(tid, "3", "General/procedural, no product to classify", q)

    # ---------- Category 4
    ask("T12", "4", "Foreign jurisdiction",
        "Can I sell my Ayurvedic product in the United States? What does the FDA require?")
    ask("T13", "4", "Out of domain", "How do I bake a good chocolate cake?")
    ask("T14", "4", "Legal-advice prediction",
        "Will I win my patent infringement lawsuit against my competitor?")
    ask("T15a", "4", "Greeting", "hi")
    record("T15b", "4", "Empty message", "",
           post("/query", {"question": "", "history": [], "jurisdiction": "india"}))
    record("T15c", "4", "Whitespace-only message", "   ",
           post("/query", {"question": "   ", "history": [], "jurisdiction": "india"}))

    # ---------- Category 5
    q16a = "Can I patent a new extraction process for Ashwagandha?"
    r16a = ask("T16a", "5", "Conversation turn 1", q16a)
    h16 = [x for x in [hist_entry(r16a)] if x]
    ask("T16b", "5", "Conversation turn 2 (subject carried from turn 1)",
        "What if I want to patent the plant itself instead?", history=h16)

    q17a = "I've made a neem-based face cream for external use only. Can I patent it?"
    r17a = ask("T17a", "5", "Conversation turn 1", q17a)
    h17 = [x for x in [hist_entry(r17a)] if x]
    ask("T17b", "5", "Elliptical follow-up", "Why not?", history=h17)

    # T18: 12 questions in one session, history growing exactly as App.tsx does.
    session_q = [
        "What is the Traditional Knowledge Digital Library?",
        "How does the Patents Act treat traditional knowledge?",
        "What is a Geographical Indication?",
        "Do I need NBA approval to file a patent using Indian biodiversity?",
        "What is a classical Ayurvedic formulation under the Drugs and Cosmetics Act?",
        "What licence do I need to manufacture an Ayurvedic medicine?",
        "Can I trademark the name of my Ayurvedic product?",
        "What labelling rules apply to Ayurvedic medicines?",
        "Can I copyright the text of my Ayurvedic formulation booklet?",
        "What are the data requirements for a phytopharmaceutical drug?",
        "Is a plant variety protectable in India?",
        "What does the Drugs and Magic Remedies Act prohibit?",
    ]
    hist = []
    for i, q in enumerate(session_q, start=1):
        r = ask("T18-%02d" % i, "5",
                "Session question %d of 12 (history=%d)" % (i, len(hist)),
                q, history=list(hist))
        e = hist_entry(r)
        if e:
            hist.append(e)

    # Explicit re-test of COMPARISON_REPORT 6.2: 9 raw history items in one call.
    record("SYS-6.2b", "system", "POST /query with 9 history items (was a 422)",
           "What is the Traditional Knowledge Digital Library?",
           post("/query", {
               "question": "What is the Traditional Knowledge Digital Library?",
               "history": ["Prior question number %d" % i for i in range(1, 10)],
               "jurisdiction": "india",
           }))

    # ---------- Category 6
    ask("T20", "6", "Weakly-covered topic - confidence calibration",
        "What does Article 27.3(b) of the TRIPS Agreement require for plant variety protection?")
    ask("T21a", "6", "Consistency run 1 (fresh backend)",
        "Can a classical churna from a First Schedule text be patented?")

    # ---------- Category 7
    ask("T22", "7", "International jurisdiction toggle",
        "Can a classical churna from a First Schedule text be patented?",
        jurisdiction="international")

    # ---------- System checks
    trav = {}
    for path in [
        "/..%2f..%2f.env",
        "/..%2f..%2fbackend%2fapp%2fconfig.py",
        "/../../.env",
        "/..%2F..%2F.env",
        "/C:/Windows/win.ini",
        "/%2e%2e%2f%2e%2e%2f.env",
        "/..%252f..%252f.env",
        "/assets/../../.env",
    ]:
        trav[path] = get_raw(path)
    results.append({"test_id": "SYS-6.1", "category": "system",
                    "label": "Path traversal / arbitrary file read",
                    "question": "GET on traversal paths", "response": {"paths": trav}})
    print("[SYS-6.1] done", flush=True)

    results.append({"test_id": "SYS-routing", "category": "system",
                    "label": "Unknown /api route",
                    "question": "GET /api/nope",
                    "response": {"paths": {"/api/nope": get_raw("/api/nope"),
                                           "/health": get_raw("/health"),
                                           "/": get_raw("/")}}})
    print("[SYS-routing] done", flush=True)

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)


def run_t21b():
    ask("T21b", "6", "Consistency run 2 (after backend restart, cold cache)",
        "Can a classical churna from a First Schedule text be patented?")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    if ONLY == "t21b":
        run_t21b()
    else:
        run_all()
    print("\nWROTE %s with %d entries" % (OUT, len(results)))
