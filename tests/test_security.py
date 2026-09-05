#!/usr/bin/env python3
"""Security regression tests for the static-file route.

Why this file exists: the SPA catch-all in `main.py` joined an attacker-supplied
URL path onto a directory and served whatever came out. `GET /..%2f..%2f.env`
returned the live OpenRouter API key over plain HTTP, and every source file was
readable the same way. See COMPARISON_REPORT.md §6.1.

The route is exercised through the real ASGI app, not by calling the helper, so
the test covers Starlette's own path decoding as well as our containment check -
the decoding is half the bug. `TestClient` is deliberately NOT used as a context
manager: that would run the lifespan hook and load the embedding model, which
takes ~20s and is irrelevant to serving a file.

Run:
    .venv\\Scripts\\python.exe tests\\test_security.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import DIST_ROOT, app, resolve_static  # noqa: E402

client = TestClient(app)

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  [{PASS if ok else FAIL}] {name}{'  - ' + detail if detail else ''}")


# Markers that must never appear in a response body. If any does, a file that
# lives outside the build directory was served.
SECRET_MARKERS = ("OPENROUTER_API_KEY", "sk-or-v1-", "ANTHROPIC_API_KEY")

# Every one of these resolved to a real file on disk before the fix.
# The first two are the exact requests reproduced in COMPARISON_REPORT.md §6.1.
TRAVERSAL_PATHS = [
    "/..%2f..%2f.env",                              # the exploit that leaked the key
    "/..%2f..%2fbackend%2fapp%2fconfig.py",         # arbitrary source read
    "/../../.env",                                  # unencoded, for clients that do not normalise
    "/..%2F..%2F.env",                              # uppercase percent-encoding
    "/..%2f..%2f..%2f.env",                         # deeper than the repo root
    "/assets/..%2f..%2f..%2f.env",                  # traversal from a real subdirectory
    "/..%2f..%2fdata%2fchunks%2fall_chunks.json",   # corpus data
    "/..%2f..%2f.gitignore",
    "/..%2f.env",                                   # one level up: frontend/
    "/%2e%2e%2f%2e%2e%2f.env",                      # fully encoded dot-dot
    "/....//....//.env",                            # doubled dots, defeats naive ".." stripping
]

# pathlib DISCARDS the left operand when the right side is absolute, so these
# never contained ".." at all. A traversal filter that only looks for ".." would
# pass every one of them straight through.
ABSOLUTE_PATHS = [
    "/C:%2fWindows%2fwin.ini",
    "/D:%2fIP_SAKTI-SAHAYAK%2f.env",
    "//localhost/c$/Windows/win.ini",
]

# These must still work - a security fix that breaks the app is not a fix.
LEGITIMATE_PATHS = ["/", "/index.html", "/favicon.svg", "/icons.svg"]


def body_of(path: str) -> tuple[int, str]:
    response = client.get(path)
    return response.status_code, response.text


def assert_blocked(path: str, index_html: str) -> None:
    """A blocked request must not return any file from outside the build.

    Two responses are both correct, because two different handlers guard two
    different prefixes:
      * our SPA catch-all falls back to index.html;
      * the `/assets` StaticFiles mount does its own containment and answers
        404 JSON.
    Asserting one specific body would fail on the other handler while proving
    nothing about safety. The invariant is what matters: no secret in the body,
    and nothing served that is not either the SPA shell or a refusal.
    """
    status, text = body_of(path)
    leaked = [m for m in SECRET_MARKERS if m in text]
    blocked = not leaked and (text == index_html or status == 404)
    if leaked:
        detail = f"LEAKED {leaked}"
    elif not blocked:
        detail = f"served an unexpected body ({status}, {len(text)} bytes)"
    else:
        detail = "index.html" if text == index_html else f"{status} refusal"
    record(f"blocked: {path}", blocked, detail)


print("\n" + "=" * 74)
print(" PATH TRAVERSAL - the exploit from COMPARISON_REPORT.md 6.1")
print("=" * 74)

index_html = (DIST_ROOT / "index.html").read_text(encoding="utf-8")

for path in TRAVERSAL_PATHS:
    assert_blocked(path, index_html)

print("\n" + "=" * 74)
print(" ABSOLUTE / UNC PATHS - pathlib discards the left operand")
print("=" * 74)

for path in ABSOLUTE_PATHS:
    assert_blocked(path, index_html)

print("\n" + "=" * 74)
print(" HELPER UNIT CHECKS - resolve_static() containment")
print("=" * 74)

record("empty path falls through", resolve_static("") is None)
record("traversal returns None", resolve_static("../../.env") is None)
record("absolute path returns None", resolve_static("C:/Windows/win.ini") is None)
record("NUL byte returns None", resolve_static("index.html\x00.env") is None)
record("missing file returns None", resolve_static("does-not-exist.html") is None)

real = resolve_static("index.html")
record(
    "real file inside the build resolves",
    real is not None and real.is_file() and real.is_relative_to(DIST_ROOT),
    str(real.name) if real else "None",
)

print("\n" + "=" * 74)
print(" NO REGRESSION - the app still serves itself")
print("=" * 74)

for path in LEGITIMATE_PATHS:
    status, text = body_of(path)
    record(f"serves {path}", status == 200 and len(text) > 0, f"{status}, {len(text)} bytes")

# The SPA fallback is what makes client-side routing work; it must survive.
status, text = body_of("/some/client/route")
record("unknown app route still returns the SPA", status == 200 and text == index_html)

print("\n" + "=" * 74)
failed = [r for r in results if r[0] == FAIL]
print(f" {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\n FAILURES:")
    for _, name, detail in failed:
        print(f"   - {name}: {detail}")
print("=" * 74 + "\n")

sys.exit(1 if failed else 0)
