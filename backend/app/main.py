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
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .classification import classify, verify_anchors
from .config import settings
from .corpus_index import warm_up
from .generation import answer_question
from .schemas import (
    AbstentionKind,
    Answer,
    ClassificationResult,
    HealthResponse,
    QueryRequest,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_state: dict = {}


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


app = FastAPI(
    title="IP-SAKTI Sahayak",
    description="Citation-grounded IP and regulatory guidance for Ayurveda (Indian law).",
    version="0.1.0",
    lifespan=lifespan,
)

# The Vite dev server. Tighten to the deployed origin before going public.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Readiness plus corpus integrity, so a broken index is visible immediately."""
    info = _state.get("health") or warm_up()
    problems = _state.get("anchor_problems", [])
    return HealthResponse(
        status="degraded" if problems else "ok",
        chunks_in_json=info["chunks_in_json"],
        chunks_in_vector_db=info["chunks_in_vector_db"],
        collection=info["collection"],
        embed_model=info["embed_model"],
        generation_model=settings.model,
        anchor_problems=problems,
    )


@app.post("/classify", response_model=ClassificationResult)
def classify_endpoint(request: QueryRequest) -> ClassificationResult:
    """Formulation classification on its own, for the UI to show early."""
    try:
        return classify(request.question)
    except Exception as exc:  # noqa: BLE001 - surface a clean error, never a stack trace
        logger.exception("Classification failed")
        raise HTTPException(status_code=502, detail=f"Classification failed: {exc}") from exc


@app.post("/query", response_model=Answer)
def query(request: QueryRequest) -> Answer:
    """The full core loop: classify, retrieve, generate, validate."""
    # The toggle is real plumbing, not decoration: the corpus has no treaty texts,
    # so the honest response is to say so rather than answer from Indian law.
    if request.jurisdiction == "international":
        return Answer(
            question=request.question,
            jurisdiction="international",
            abstained=True,
            abstention_kind=AbstentionKind.FOREIGN_JURISDICTION,
            abstention_message=(
                "International coverage is not available yet. The corpus currently holds "
                "Indian law only. Switch to India to get the national position."
            ),
            disclaimer=settings.disclaimer,
        )

    try:
        return answer_question(
            request.question, top_k=request.top_k, history=request.history
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Query failed")
        raise HTTPException(status_code=502, detail=f"Query failed: {exc}") from exc
