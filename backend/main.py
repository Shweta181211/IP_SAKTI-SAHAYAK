"""
main.py -- FastAPI server for IP Sakti Sahayak.

Run locally from the repo root:
    uvicorn backend.main:app --reload

Then open http://127.0.0.1:8000 in a browser. This single server both
answers the frontend's API calls and serves the frontend's static files, so
there is nothing else to run and no CORS configuration is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Make sure this file's own directory is importable as a plain module path
# (works whether uvicorn loads this as `backend.main` or `main`).
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import rag_engine  # noqa: E402

REPO_ROOT = _THIS_DIR.parent
FRONTEND_DIR = REPO_ROOT / "frontend"

app = FastAPI(title="IP Sakti Sahayak API")


@app.on_event("startup")
def _startup() -> None:
    # Load once at process start rather than on the first request, so the
    # first user doesn't pay the model-loading latency.
    rag_engine.load_backend()


class QueryRequest(BaseModel):
    # Keep API input bounded too (not only the browser UI), so an accidental
    # or hostile oversized request cannot create an unbounded embedding job.
    question: str = Field(min_length=2, max_length=1500)
    # NOTE: Pydantic resolves these annotations at runtime to build its
    # validator, so `Optional[str]` is used instead of the `str | None`
    # syntax -- the latter needs Python 3.10+ and breaks on 3.9.
    regime_type: Optional[str] = None
    formulation_category_id: Optional[str] = None
    top_k: int = Field(default=6, ge=1, le=12)
    use_llm: bool = False
    # Local-only audit logging (see rag_engine.log_interaction). Defaults to
    # on but the frontend exposes a toggle so a user can opt out per session.
    log_consent: bool = True


@app.get("/api/health")
def health() -> dict:
    return rag_engine.status()


@app.get("/api/formulation-categories")
def formulation_categories() -> list[dict]:
    return rag_engine.FORMULATION_CATEGORIES


@app.get("/api/regime-types")
def regime_types() -> list[dict]:
    # Kept in sync by hand with the corpus metadata (see Corpus_Pipeline.md /
    # all_chunks.json). National scope only, per current project scope.
    return [
        {"id": None, "label": "All regimes"},
        {"id": "drug_regulatory_classification", "label": "Drug / regulatory classification"},
        {"id": "ip_statute", "label": "IP statute"},
        {"id": "registry_guideline", "label": "Registry / guideline"},
        {"id": "pharmacopoeia_reference", "label": "Pharmacopoeia reference"},
    ]


@app.post("/api/query")
def query(req: QueryRequest) -> dict:
    return rag_engine.answer_query(
        question=req.question,
        regime_type=req.regime_type,
        formulation_category_id=req.formulation_category_id,
        top_k=req.top_k,
        use_llm=req.use_llm,
        log_consent=req.log_consent,
    )


# Serve the frontend last so it doesn't shadow the /api/* routes above.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
