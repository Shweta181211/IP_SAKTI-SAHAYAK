"""Single source of truth for paths, model IDs and thresholds.

Nothing else in the app should hardcode a model name, a path or a tuning
constant. If you are tempted to inline one, put it here instead.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Environment-driven config. Overrides use the IPSAKTI_ prefix."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_prefix="IPSAKTI_", extra="ignore"
    )

    # --- Paths -------------------------------------------------------------
    chunks_path: Path = ROOT / "data" / "chunks" / "all_chunks.json"
    vector_db_dir: Path = ROOT / "data" / "vector_db"
    collection_name: str = "ip_sakti_corpus"

    # --- Embeddings --------------------------------------------------------
    # E5 needs "query: " / "passage: " prefixes; see embed helpers.
    embed_model: str = "intfloat/multilingual-e5-base"

    # --- Generation (OpenRouter, OpenAI-compatible endpoint) ---------------
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Free by default because the account has no credits. Swap to
    # anthropic/claude-sonnet-5 via IPSAKTI_MODEL once it does.
    model: str = "minimax/minimax-m3:free"
    # Free-model capacity is shared and flaky; 429s are routine, not exceptional.
    fallback_models: tuple[str, ...] = ("minimax/minimax-m3:free",)
    temperature: float = 0.0
    max_tokens: int = 1500
    request_timeout_s: float = 120.0
    max_retries: int = 4

    # Evidence passed to the generator. Measured: the decisive Section 3(p)
    # chunk ranks between 4 and 7 depending on which expansions the model
    # produces, so a window of 8 buried it on some runs. 12 costs ~3.5k extra
    # prompt tokens against a 1M context - cheap insurance for recall.
    top_k: int = 12

    # --- Behaviour ---------------------------------------------------------
    disclaimer: str = (
        "This is information, not legal advice. It cites primary legal sources "
        "but is not a substitute for a qualified IP practitioner."
    )


settings = Settings()


def api_key() -> str:
    """Read the OpenRouter key at call time so a missing key fails loudly here."""
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key "
            "from https://openrouter.ai/keys"
        )
    return key
