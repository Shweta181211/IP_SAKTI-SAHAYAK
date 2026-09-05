"""Thin OpenRouter client.

OpenRouter exposes an OpenAI-compatible /chat/completions endpoint, so we use
the `openai` package pointed at their base URL - not the `anthropic` one.

Two things this module exists to handle:
  1. Free-tier models return 429 routinely. A bare call is not good enough.
  2. Models wrap JSON in prose or markdown fences no matter how firmly asked
     not to. Parsing must be defensive.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from openai import OpenAI
from openai import APIError, APITimeoutError, RateLimitError

from .config import api_key, settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def client() -> OpenAI:
    """Lazily built so importing this module never requires a key."""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=api_key(),
            base_url=settings.openrouter_base_url,
            timeout=settings.request_timeout_s,
            # We run our own backoff-and-fallback loop below. Leaving the SDK's
            # default retries on stacks a second, invisible retry layer inside
            # each of ours - which quietly multiplies the time it takes to give
            # up on a model that is out of daily quota and can never succeed.
            max_retries=0,
        )
    return _client


class LLMUnavailable(RuntimeError):
    """Every model and retry was exhausted. Callers must abstain, not invent."""


# OpenRouter returns 429 for two completely different situations, and retrying
# is right for only one of them:
#
#   * a transient per-minute/per-provider limit - backing off works;
#   * the account's free-tier DAILY allowance ("free-models-per-day", 50/day on
#     an account with no credits) - no amount of backoff helps until midnight.
#
# Measured on this account: with the daily allowance exhausted, 17 of 19 free
# models 429 instantly. Retrying each one four times with exponential backoff
# costs ~16s per model and cannot succeed, so a three-model fallback list added
# ~48s of dead air to every request before failing anyway. Detecting the daily
# cap and moving straight to the next model turns that into well under a second.
_DAILY_CAP_MARKERS = ("free-models-per-day", "openrouter_free_tier_daily")


def _is_daily_cap(exc: Exception) -> bool:
    """True when a 429 means 'out of quota until reset', not 'slow down'."""
    return any(marker in str(exc) for marker in _DAILY_CAP_MARKERS)


def complete(prompt: str, *, max_tokens: int | None = None) -> str:
    """Return raw model text, retrying across backoff and fallback models.

    Raises LLMUnavailable rather than returning a degraded answer - a legal tool
    must fail visibly, never quietly.
    """
    models = [settings.model, *(m for m in settings.fallback_models if m != settings.model)]
    last_error: Exception | None = None

    for model in models:
        for attempt in range(settings.max_retries):
            try:
                response = client().chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=settings.temperature,
                    max_tokens=max_tokens or settings.max_tokens,
                )
                text = (response.choices[0].message.content or "").strip()
                if text:
                    return text
                last_error = LLMUnavailable(f"{model} returned empty content")
            except (RateLimitError, APITimeoutError, APIError) as exc:
                last_error = exc
                if _is_daily_cap(exc):
                    # Out of daily quota. Waiting cannot help; try another model.
                    logger.warning("%s is out of daily free quota; skipping to next model", model)
                    break
                # Jittered exponential backoff: free capacity frees up in seconds,
                # and synchronised retries from parallel calls would collide.
                delay = (2**attempt) + random.uniform(0, 1)
                logger.warning("%s attempt %d failed (%s); retrying in %.1fs",
                               model, attempt + 1, type(exc).__name__, delay)
                time.sleep(delay)
        else:
            logger.warning("Model %s exhausted; trying next fallback", model)

    raise LLMUnavailable(f"All models failed. Last error: {last_error}")


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def complete_json(prompt: str, *, max_tokens: int | None = None) -> dict[str, Any]:
    """Call the model and parse a JSON object out of its reply.

    Models emit fences, preambles and trailing commentary. We strip fences, then
    take the outermost {...} span. If that still is not valid JSON we raise -
    guessing at a malformed legal answer is worse than failing.
    """
    raw = complete(prompt, max_tokens=max_tokens)
    text = _FENCE.sub("", raw).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    raise LLMUnavailable(f"Model did not return parseable JSON. Got: {raw[:300]}")
