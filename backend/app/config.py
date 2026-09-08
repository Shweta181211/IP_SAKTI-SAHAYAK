"""Single source of truth for paths, model IDs and thresholds.

Nothing else in the app should hardcode a model name, a path or a tuning
constant. If you are tempted to inline one, put it here instead.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
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

    # --- Generation: a provider chain, not a single vendor -----------------
    #
    # Falling back to a second MODEL inside one provider does nothing when the
    # provider itself is the thing that ran out - and that is exactly what
    # happened twice during the September 2026 evaluation. OpenRouter's
    # free-models-per-day cap took out all 19 of its free models at once, and
    # Gemini's PerDay quota took out both Gemini models at once. A fallback
    # list that shares a quota pool is not a fallback list.
    #
    # So each tier below is a genuinely independent account and quota. A tier is
    # skipped silently when its key is absent, so contributors with only one key
    # still work.
    #
    # Order, and why:
    #   1. google  - fastest measured (1.2 s) and the current default.
    #   2. groq    - separate quota, and qwen3.8-27b answered the gate's strict
    #                250-token JSON prompt in 0.4 s. gpt-oss-120b is the
    #                strongest free model reachable from here (2.4 s).
    #   3. openrouter - third independent pool; slowest and most contended.
    #
    # Models that FAILED the real workload and are deliberately absent:
    #   openai/gpt-oss-20b   needs ~800 tokens to emit JSON; returns empty at
    #                        the gate's 250-token budget, i.e. fails closed.
    #   qwen/qwen3.6-27b     emits a <think> monologue instead of JSON.
    #   gemini-3.6-flash     thinking model; same truncation problem (6k).
    llm_chain: tuple[dict, ...] = (
        {
            "name": "google",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key_env": "GEMINI_API_KEY",
            "models": ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"),
        },
        {
            "name": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "models": ("openai/gpt-oss-120b", "qwen/qwen3.8-27b"),
            # gpt-oss-120b leads on measurement, not size: qwen3.8-27b answers
            # faster when it answers (0.4 s vs 2.4 s) but 429s persistently on
            # the free per-minute allowance, costing ~16 s of backoff before
            # failing over. A model that is slower but available beats a faster
            # one that is not.
        },
        {
            "name": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "models": ("minimax/minimax-m3:free",
                       "nvidia/nemotron-3-super-120b-a12b:free"),
            # nemotron-3-ULTRA is deliberately absent: measured at 102 s for a
            # trivial JSON reply against ~3 s for these two. A fallback that
            # slow is worse than the next provider in the chain.
        },
    )

    # The strongest model reachable for free, used only where conflating two
    # jurisdictions would be the failure. Empty string means "use the chain".
    strong_model: str = "openai/gpt-oss-120b"

    # Seconds to leave between consecutive outbound LLM calls, process-wide.
    #
    # A Compare request fires several calls back to back, and firing them
    # instantly is how a per-minute cap gets tripped by our own traffic rather
    # than by load. Measured: the checklist suite with no pacing drove every
    # query to 63-90 s of provider backoff; the same build unthrottled answers
    # in 5-7 s. Paying ~1.5 s deliberately is cheaper than a 30 s retry chain.
    #
    # Set to 0.0 to disable (the test suites do, since they measure behaviour
    # rather than politeness).
    min_call_interval_s: float = 1.5

    # --- Generation (any OpenAI-compatible endpoint) -----------------------
    #
    # Not OpenRouter-specific any more. Google's Generative Language API exposes
    # an OpenAI-compatible surface too, and during the September 2026 evaluation
    # OpenRouter's free tier was exhausted while Gemini was not - so which
    # provider answers has to be configuration, not a code edit under pressure.
    #
    # The old name is kept as an alias so existing .env files and shell exports
    # keep working.
    llm_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices(
            "IPSAKTI_LLM_BASE_URL", "IPSAKTI_OPENROUTER_BASE_URL"
        ),
    )

    # WHICH environment variable holds the key. The key itself never lives in
    # this file. Point it at GEMINI_API_KEY to run on Gemini without renaming
    # anybody's secret, which is what the alternative required and it was
    # genuinely confusing: a Gemini key in a variable called OPENROUTER_API_KEY.
    api_key_env: str = "OPENROUTER_API_KEY"
    # Free by default because the account has no credits. Swap to
    # anthropic/claude-sonnet-5 via IPSAKTI_MODEL once it does.
    # Empty means "use llm_chain". Set IPSAKTI_MODEL only to pin one specific
    # model ahead of the whole chain - it is prepended and logged as "override".
    #
    # This defaulted to a real model id, which quietly made every run an
    # override: the default put OpenRouter's minimax first even after the chain
    # was introduced, i.e. the one provider whose quota was exhausted.
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 1500
    request_timeout_s: float = 120.0
    max_retries: int = 4

    # Evidence passed to the generator. Measured: the decisive Section 3(p)
    # chunk ranks between 4 and 7 depending on which expansions the model
    # produces, so a window of 8 buried it on some runs. 12 costs ~3.5k extra
    # prompt tokens against a 1M context - cheap insurance for recall.
    top_k: int = 12

    #: How many provisions the graph may add on top of fused retrieval.
    #:
    #: **Zero, and that is a measured decision rather than a default.** Feeding
    #: cross-referenced provisions into the evidence set was built and then
    #: measured on six questions: it helped on three (the GI question gained
    #: ss.3, 6 and 12; ABS gained s.23; the licensing question gained ss.5, 20
    #: and 21) and added noise on three - including the flagship, where it
    #: pulled Patents Act ss.84, 87 and 88 into the prompt. Those are compulsory
    #: licensing; they have nothing to do with the traditional-knowledge bar.
    #: Restricting the expansion to the top 3 passages instead of all 12 did not
    #: change that, so it is not a tuning problem.
    #:
    #: The cause is structural: statutes cross-reference for procedural plumbing
    #: far more often than for substantive relevance, so "referenced by" is a
    #: poor proxy for "bears on this question". More candidate provisions in the
    #: prompt is exactly how section 6f's "settled for a neighbouring clause"
    #: failure happens.
    #:
    #: The graph therefore ships as navigation, not as evidence: every citation
    #: shows what it points at, and a reader can follow it, but no answer
    #: changes. Raise this only with a measurement that shows the flagship still
    #: cites 3(p) and gains nothing irrelevant.
    graph_expansion_slots: int = 0

    # Evidence for a CATEGORY COMPARISON, which must cover four regulatory
    # regimes in one prompt rather than answer one question. At top_k = 12 the
    # product's own vocabulary filled every slot with one act: two of the four
    # categories retrieved nothing and the patentability column was empty for
    # all four. This is one call, so the extra prompt tokens are paid once.
    compare_top_k: int = 24

    # Slots RESERVED for each compared category, retrieved from that category's
    # own statutory probe and merged into the fused set. Guarantees every
    # category has evidence to be judged on, instead of leaving the two whose
    # vocabulary the product happens not to share with nothing to cite.
    compare_probe_slots: int = 4

    # --- Rate limiting -----------------------------------------------------
    # Requests per minute per client, for the endpoints that cost upstream LLM
    # calls. Generous for a person demonstrating the tool, restrictive for a
    # script. Set either to 0 to disable - which the test suites do, since a
    # warm answer cache lets them fire far faster than any human would.
    rate_limit_query: int = 12
    rate_limit_compare: int = 6

    # --- Behaviour ---------------------------------------------------------
    disclaimer: str = (
        "This is information, not legal advice. It cites primary legal sources "
        "but is not a substitute for a qualified IP practitioner."
    )


settings = Settings()


def provider_key(env_name: str = "", required: bool = True) -> str:
    """Read a provider's key at call time, by variable NAME.

    Keys are looked up per provider rather than from one global variable,
    because the fallback chain spans three independent accounts. `required`
    is False when probing which tiers are usable: an absent key means that
    provider is simply skipped, not that the system is misconfigured.
    """
    import os

    from dotenv import load_dotenv

    # override=True because .env is this project's documented source of truth
    # for provider keys (6k). Without it load_dotenv leaves an already-loaded
    # value in place, so a key edited in a RUNNING server is silently ignored -
    # the process keeps calling the old, exhausted key forever. Deployments that
    # set real environment variables ship no .env, so nothing is overridden
    # there and this stays a local-development convenience.
    load_dotenv(ROOT / ".env", override=True)
    name = env_name or settings.api_key_env
    key = os.getenv(name, "").strip().strip('"').strip("'")
    if not key and required:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and add a key for at least "
            "one provider in the fallback chain (see config.llm_chain)."
        )
    return key


def api_key() -> str:
    """Backwards-compatible single-key accessor."""
    return provider_key()


def active_model() -> str:
    """The model a request would use right now: the head of the chain."""
    from .llm import endpoints  # local import: llm imports config

    chain = endpoints()
    return str(chain[0]) if chain else "none configured"
