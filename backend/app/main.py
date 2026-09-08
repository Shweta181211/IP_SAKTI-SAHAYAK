"""FastAPI service for IP-SAKTI Sahayak.

Three endpoints, thin by design: all the real work lives in classification.py,
retrieval.py and generation.py, which are independently testable without a
server running.

Indexes are loaded once in the lifespan hook. The embedding model takes several
seconds to load, and paying that on a user's first question - during a live demo -
would be a poor trade.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import audit
from .classification import classify, verify_anchors
from .config import ROOT, active_model, settings
from .corpus_index import warm_up
from .escalation import assess as assess_escalation
from .comparison import compare_categories
from .export_readiness import build_report as build_export_readiness
from .jurisdiction_compare import compare_jurisdictions
from .next_steps import next_steps_for_answer, next_steps_for_comparison
from .plain_language import apply_style
from .generation import answer_question
from .llm import endpoints as llm_endpoints
from .ratelimit import RateLimiter, enforce
from .schemas import (
    AbstentionKind,
    Answer,
    CompareJurisdictionsRequest,
    CompareRequest,
    ComparisonResult,
    ClassificationResult,
    ExportReadinessReport,
    ExportReadinessRequest,
    HealthResponse,
    JurisdictionComparison,
    NextSteps,
    NextStepsRequest,
    QueryRequest,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_state: dict = {}

# Separate buckets: a comparison is a heavier, rarer action than a question, and
# sharing one counter would let either starve the other.
query_limiter = RateLimiter(limit=settings.rate_limit_query)
compare_limiter = RateLimiter(limit=settings.rate_limit_compare)


def _international_available() -> bool:
    """True when the treaty corpus actually holds documents.

    Checked rather than assumed: a rebuild, a fresh clone, or a corpus.zip that
    predates the international phase all leave `03_international/` empty, and in
    that state answering an international question would silently fall back to
    whatever the national index returns. Refusing is the only safe default.
    """
    info = _state.get("health") or {}
    return bool(info.get("chunks_by_jurisdiction", {}).get("international"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading corpus, vector store and BM25 index...")
    _state["health"] = warm_up()
    problems = verify_anchors()
    _state["anchor_problems"] = problems
    if problems:
        # Loud but not fatal: classification degrades gracefully, and refusing to
        # boot during a demo would be worse than running with a warning.
        logger.error("Definition anchors have problems: %s", problems)
    logger.info("Ready. %s", _state["health"])
    yield


# The interactive docs describe and drive every endpoint, including the ones
# that each cost several upstream LLM calls. Useful while developing, not
# something to leave open on a deployed demo, so they are opt-in.
_DOCS_ENABLED = os.getenv("IPSAKTI_ENABLE_DOCS", "").strip().lower() in {"1", "true", "yes"}

app = FastAPI(
    title="IP-SAKTI Sahayak",
    description="Citation-grounded IP and regulatory guidance for Ayurveda (Indian law).",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
)

# Routes live on a router so they can be served at BOTH /health and /api/health.
# The frontend always calls /api/*; in development Vite proxies that to this
# server, and in production this same server serves the built frontend, so one
# origin covers both. The bare paths are kept because the test suites use them.
api = APIRouter()

# The Vite dev server. Tighten to the deployed origin before going public.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@api.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Readiness plus corpus integrity, so a broken index is visible immediately."""
    info = _state.get("health") or warm_up()
    problems = _state.get("anchor_problems", [])
    return HealthResponse(
        status="degraded" if problems else "ok",
        chunks_in_json=info["chunks_in_json"],
        chunks_in_vector_db=info["chunks_in_vector_db"],
        chunks_by_jurisdiction=info.get("chunks_by_jurisdiction", {}),
        collection=info["collection"],
        embed_model=info["embed_model"],
        generation_model=active_model(),
        llm_chain=[str(e) for e in llm_endpoints()],
        anchor_problems=problems,
        audit=audit.summary(),
    )


@api.post("/classify", response_model=ClassificationResult)
def classify_endpoint(request: QueryRequest) -> ClassificationResult:
    """Formulation classification on its own, for the UI to show early."""
    try:
        return classify(request.question)
    except Exception as exc:  # noqa: BLE001 - surface a clean error, never a stack trace
        # Logged in full server-side; the client gets a message it can act on.
        # Exception text can carry upstream URLs, model ids and request details
        # that a user has no use for and an attacker does.
        logger.exception("Classification failed")
        raise HTTPException(
            status_code=502,
            detail="Classification failed because an upstream service was unavailable. "
                   "Please try again in a moment.",
        ) from exc


@api.post("/query", response_model=Answer)
def query(request: QueryRequest, http_request: Request) -> Answer:
    """The full core loop: classify, retrieve, generate, validate."""
    enforce(query_limiter, http_request)
    # Until the treaty corpus was ingested this branch returned a fixed
    # abstention, because answering an international question from Indian law
    # would have been the worst thing this tool could do. `03_international/`
    # now holds 825 chunks across 11 instruments, so the honest response is to
    # answer from them - and the separation is enforced in retrieval rather
    # than here. The branch remains for the case where that corpus is empty
    # again (a rebuild, a fresh clone), which must still refuse rather than
    # quietly fall back to national law.
    if request.jurisdiction == "international" and not _international_available():
        # Built here rather than in generation.py, so it must set the same
        # fields generation would - including the escalation offer, which is
        # exactly right for this case: a real legal need, outside our corpus.
        escalate, escalation_reason = assess_escalation(
            True, AbstentionKind.FOREIGN_JURISDICTION, None
        )
        answer = Answer(
            question=request.question,
            jurisdiction="international",
            abstained=True,
            abstention_kind=AbstentionKind.FOREIGN_JURISDICTION,
            abstention_message=(
                "The international corpus is not loaded, so I cannot answer this from "
                "treaty sources - and I will not answer it from Indian law instead. "
                "Rebuild the index (pipeline/build_vector_db.py) or switch to India."
            ),
            escalate=escalate,
            escalation_reason=escalation_reason,
            disclaimer=settings.disclaimer,
        )
        audit.log_answer(request.question, answer, consent=request.log_consent)
        return answer

    started = time.time()
    try:
        answer = answer_question(
            request.question, top_k=request.top_k, history=request.history,
            jurisdiction="international" if request.jurisdiction == "international"
            else "national",
        )
        # Style is applied AFTER generation and caching, so switching styles on
        # the same question reuses the generated answer and cannot change what
        # it cited. See plain_language.py for why it is a rewrite rather than a
        # prompt instruction.
        answer = apply_style(answer, request.response_style)
        audit.log_answer(
            request.question, answer,
            consent=request.log_consent, elapsed_s=time.time() - started,
        )
        return answer
    except Exception as exc:  # noqa: BLE001
        # Logged in full server-side; the client gets a message it can act on.
        # Exception text can carry upstream URLs, model ids and request details
        # that a user has no use for and an attacker does.
        logger.exception("Query failed")
        raise HTTPException(
            status_code=502,
            detail="Query failed because an upstream service was unavailable. "
                   "Please try again in a moment.",
        ) from exc


@api.post("/compare", response_model=ComparisonResult)
def compare(request: CompareRequest, http_request: Request) -> ComparisonResult:
    """Show how one product's legal position changes across categories."""
    enforce(compare_limiter, http_request)
    started = time.time()
    try:
        result = compare_categories(request.product)
        audit.log_comparison(
            request.product, result,
            consent=request.log_consent, elapsed_s=time.time() - started,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        # Logged in full server-side; the client gets a message it can act on.
        # Exception text can carry upstream URLs, model ids and request details
        # that a user has no use for and an attacker does.
        logger.exception("Comparison failed")
        raise HTTPException(
            status_code=502,
            detail="Comparison failed because an upstream service was unavailable. "
                   "Please try again in a moment.",
        ) from exc



@api.post("/compare-jurisdictions", response_model=JurisdictionComparison)
def compare_jurisdictions_endpoint(
    request: CompareJurisdictionsRequest, http_request: Request
) -> JurisdictionComparison:
    """The Indian position and the international one, answered separately.

    Costs three generation passes, so it shares the comparison rate-limit bucket
    rather than the query one and is never triggered automatically - the user
    asks for it explicitly.
    """
    enforce(compare_limiter, http_request)
    if not _international_available():
        raise HTTPException(
            status_code=409,
            detail="The international corpus is not loaded, so there is nothing to "
                   "compare against. Rebuild the index with pipeline/build_vector_db.py.",
        )
    started = time.time()
    try:
        result = compare_jurisdictions(
            request.question, top_k=request.top_k,
            national=request.national, international=request.international,
        )
        audit.log_answer(
            request.question, result.national,
            consent=request.log_consent, elapsed_s=time.time() - started,
        )
        audit.log_answer(request.question, result.international, consent=request.log_consent)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("Jurisdiction comparison failed")
        raise HTTPException(
            status_code=502,
            detail="The comparison failed because an upstream service was unavailable. "
                   "Please try again in a moment.",
        ) from exc



@api.post("/export-readiness", response_model=ExportReadinessReport)
def export_readiness_endpoint(
    request: ExportReadinessRequest, http_request: Request
) -> ExportReadinessReport:
    """India-side and target-market readiness for one product.

    Costs a classification, two retrievals (each with its own relevance gate)
    and one generation, so it shares the comparison rate-limit bucket rather
    than the query one.
    """
    enforce(compare_limiter, http_request)
    started = time.time()
    try:
        report = build_export_readiness(request)
        audit.log_readiness(
            request.product, report,
            consent=request.log_consent, elapsed_s=time.time() - started,
        )
        return report
    except Exception as exc:  # noqa: BLE001
        logger.exception("Export readiness failed")
        raise HTTPException(
            status_code=502,
            detail="The readiness report failed because an upstream service was "
                   "unavailable. Please try again in a moment.",
        ) from exc


@api.post("/next-steps", response_model=NextSteps)
def next_steps_endpoint(request: NextStepsRequest, http_request: Request) -> NextSteps:
    """Practical follow-ups for an answer the client already has.

    Takes the answer rather than the question on purpose: this step must not
    retrieve, or it could introduce obligations the answer never established.
    Opt-in - nothing calls it unless the reader asked what to do next.
    """
    enforce(query_limiter, http_request)
    try:
        if request.comparison is not None:
            return next_steps_for_comparison(request.comparison, request.style.value)
        if request.answer is not None:
            return next_steps_for_answer(request.answer, request.style.value)
        raise HTTPException(
            status_code=422, detail="Provide either an answer or a comparison."
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Next steps failed")
        raise HTTPException(
            status_code=502,
            detail="Suggestions could not be generated because an upstream service was "
                   "unavailable. Please try again in a moment.",
        ) from exc


# Mount the API twice: bare for the test suites, /api for the browser.
app.include_router(api)
app.include_router(api, prefix="/api")

# --------------------------------------------------------------------------
# Serve the built frontend from this same process, when it exists.
#
# Two servers and a proxy is fine for development and a liability during a
# demo - one more thing to have forgotten to start. If `frontend/dist` has been
# built, this serves it; if not, the API still runs exactly as before.
# Mounted LAST so it can never shadow the routes above.
# --------------------------------------------------------------------------
FRONTEND_DIST = ROOT / "frontend" / "dist"
# Resolved once, at import: every request compares against this, and comparing
# against an unresolved path would let a symlink or "." component slip through.
DIST_ROOT = FRONTEND_DIST.resolve() if FRONTEND_DIST.is_dir() else FRONTEND_DIST


def resolve_static(full_path: str) -> Path | None:
    """Map a URL path to a file inside the build, or None if it escapes.

    `full_path` is attacker-controlled and Starlette has already percent-decoded
    it, so "..%2f..%2f.env" arrives here as the real path segments "../../.env".
    Joining that onto a directory and serving whatever comes out is an arbitrary
    file read: it handed out `.env` - the live API key - over plain HTTP.

    Two escapes have to be closed, not one:
      * traversal, "../../.env", handled by resolving and then checking
        containment rather than by pattern-matching the string;
      * anchor replacement, "C:/Windows/win.ini" or "//host/share", where
        pathlib DISCARDS the left operand entirely and returns the absolute
        path. No number of ".." checks would catch that; the containment check
        does, because the result is not under DIST_ROOT either.

    Returns the file to serve, or None to fall through to index.html.
    """
    if not full_path:
        return None
    try:
        candidate = (DIST_ROOT / full_path).resolve()
    except (OSError, ValueError):
        # Embedded NULs, over-long names, and other paths the OS refuses to
        # normalise. Unservable by definition - fall back rather than 500.
        return None
    if not candidate.is_relative_to(DIST_ROOT):
        logger.warning("Blocked path traversal attempt: %r", full_path[:200])
        return None
    return candidate if candidate.is_file() else None


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str) -> FileResponse:
        """Single-page app: unknown paths return index.html, not a 404.

        Except under /api/, which must behave like an API. The catch-all used to
        swallow those too, so a mistyped or wrong-method endpoint answered
        `200 text/html`: `response.ok` was true in the client, which then tried
        to parse index.html as JSON and reported something baffling. A 404 that
        says so is worth far more than a 200 that lies.
        """
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such API endpoint.")
        candidate = resolve_static(full_path)
        if candidate is not None:
            return FileResponse(candidate)
        return FileResponse(DIST_ROOT / "index.html")
else:
    logger.info("No frontend build at %s - serving API only", FRONTEND_DIST)
