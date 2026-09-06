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
import threading
import time
from dataclasses import dataclass
from typing import Any

# Imported eagerly, not for our own use: the OpenAI SDK reaches for httpx
# lazily while BUILDING a request, and the jurisdiction comparison is the first
# code path with four threads doing that at once (two jurisdictions, each
# running classification and query expansion concurrently). Two threads hitting
# a first-time module import together produced
#     AttributeError: partially initialized module 'httpx' has no attribute
#     'Timeout' (most likely due to a circular import)
# which surfaced as the comparison crashing rather than as an import error.
# Importing here, at module load, means it is complete before any thread runs.
import httpx  # noqa: F401

from openai import OpenAI
from openai import APIError, APITimeoutError, RateLimitError

from .config import provider_key, settings

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Endpoint:
    """One (provider, model) pair we can actually call."""

    provider: str
    base_url: str
    api_key_env: str
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


_clients: dict[tuple[str, str], OpenAI] = {}
_clients_lock = threading.Lock()


def _client_for(endpoint: Endpoint) -> OpenAI:
    """One client per (base_url, key VALUE), reused across models on a provider.

    Keyed on the key itself, never on the NAME of the variable holding it.
    Keyed on the name, a client built with a since-revoked or exhausted key was
    reused for the life of the process, so rotating a key in .env changed
    nothing until a restart. The symptom is badly misleading: every question
    fails the relevance gate with `gate_unavailable` while a hand-run probe
    reading the same .env succeeds, which looks like a code bug and is not one.
    """
    key = provider_key(endpoint.api_key_env)
    cache_key = (endpoint.base_url, key)
    with _clients_lock:
        client = _clients.get(cache_key)
        if client is None:
            client = OpenAI(
                api_key=key,
                base_url=endpoint.base_url,
                timeout=settings.request_timeout_s,
                # We run our own backoff-and-fallback loop below. Leaving the
                # SDK's default retries on stacks a second, invisible retry
                # layer inside each of ours, which quietly multiplies the time
                # it takes to give up on a model that can never succeed.
                max_retries=0,
            )
            _clients[cache_key] = client
        return client


def endpoints(strong_first: bool = False) -> list[Endpoint]:
    """The call order: every reachable (provider, model), best first.

    A tier whose key is not configured is dropped rather than attempted, so a
    contributor with only one of the three keys still gets a working system and
    no misleading auth errors in the log.
    """
    found: list[Endpoint] = []
    for tier in settings.llm_chain:
        if not provider_key(tier["api_key_env"], required=False):
            continue
        for model in tier["models"]:
            found.append(
                Endpoint(tier["name"], tier["base_url"], tier["api_key_env"], model)
            )

    # Legacy single-provider override. IPSAKTI_MODEL used to be the whole
    # configuration, and anyone who has set it means it, so it goes first.
    if settings.model:
        override = Endpoint("override", settings.llm_base_url, settings.api_key_env,
                            settings.model)
        found = [override] + [e for e in found if e.model != override.model]

    if strong_first and settings.strong_model:
        strong = [e for e in found if e.model == settings.strong_model]
        found = strong + [e for e in found if e.model != settings.strong_model]
    return found


# A provider that reported a DAILY cap stays capped for everyone, not just for
# the call that discovered it. Without this memo every LLM call re-probes the
# dead provider first: measured on one four-call query with Google exhausted,
# that was four wasted round trips before reaching a provider that could answer.
#
# The memo expires rather than lasting forever, because daily quotas do reset
# and a long-running server should notice. Twenty minutes is short enough to
# pick the provider back up soon after a reset and long enough to stop us
# hammering a dead endpoint in between.
_CAP_MEMO_SECONDS = 20 * 60
_capped_until: dict[str, float] = {}
_cap_lock = threading.Lock()


def _mark_capped(scope: str) -> None:
    """Remember a capped scope: either "provider" or "provider:model"."""
    with _cap_lock:
        _capped_until[scope] = time.monotonic() + _CAP_MEMO_SECONDS


def _is_capped(scope: str) -> bool:
    with _cap_lock:
        until = _capped_until.get(scope)
        if until is None:
            return False
        if time.monotonic() >= until:
            del _capped_until[scope]           # expired - let it be retried
            return False
        return True


def reset_cap_memo() -> None:
    """Forget which providers were capped. For tests."""
    with _cap_lock:
        _capped_until.clear()


# Process-wide pacing. Several calls fire back to back inside one request, and
# bursting them is how our own traffic trips a per-minute cap.
_pace_lock = threading.Lock()
_last_call_at = 0.0


def _pace() -> None:
    global _last_call_at
    gap = settings.min_call_interval_s
    if gap <= 0:
        return
    with _pace_lock:
        wait = gap - (time.monotonic() - _last_call_at)
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()


class LLMUnavailable(RuntimeError):
    """Every provider, model and retry was exhausted. Callers must abstain."""


# A 429 means two completely different things and retrying is right for only one:
#
#   * a transient per-minute/per-provider limit - backing off works;
#   * the account's DAILY allowance - no amount of backoff helps until reset.
#
# Measured on this project: with OpenRouter's daily allowance gone, 17 of 19
# free models 429 instantly, and retrying each four times with exponential
# backoff cost ~16 s per model and could not succeed. Detecting the daily cap
# and moving straight on turns ~48 s of dead air into well under a second.
_DAILY_CAP_MARKERS = (
    "free-models-per-day",
    "openrouter_free_tier_daily",
    "limit_rpd",
    "perday",
    "per day",
    "quota_exceeded",
    "resource_exhausted",
)


# A cap that applies to the whole ACCOUNT, so the provider's other models
# cannot help either. OpenRouter says so in as many words ("Add 10 credits to
# unlock 1000 free model requests per day"). Everything else in
# _DAILY_CAP_MARKERS is assumed per-model until a provider tells us otherwise,
# because the cost of guessing wrong in this direction is only one wasted call,
# while guessing wrong the other way discards a working endpoint for 20 minutes.
_ACCOUNT_CAP_MARKERS = (
    "free-models-per-day",
    "openrouter_free_tier_daily",
    "free_tier_daily",
)


# A 429 naming a PER-MINUTE limit is transient by definition, and this check
# runs FIRST because the daily markers below match it too.
#
# Gemini reports a per-minute limit with status RESOURCE_EXHAUSTED - the same
# status it uses for a daily one - so "resource_exhausted" matched both.
# Measured on a free-tier burst:
#     quotaId: 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'
#     limit: 15, retryDelay: 31s
# and the old code retired that model for the full 20-minute memo over a
# thirty-second limit. With BOTH Gemini models retired that way and OpenRouter
# genuinely out of daily quota, the whole chain collapsed onto Groq, which then
# tripped its own per-minute token limit and the request failed closed. That is
# the cascade behind five spurious benchmark failures and the user-visible
# "Safety check unavailable".
#
# Deliberately no bare "rpm": too short not to appear inside unrelated text.
_PER_MINUTE_MARKERS = (
    "perminute",
    "per minute",
    "requests per minute",
    "tokens per minute",
    "itpm",
)


def _is_per_minute_limit(exc: Exception) -> bool:
    """True when a 429 names a limit that resets within the minute."""
    return any(marker in str(exc).lower() for marker in _PER_MINUTE_MARKERS)


def _is_daily_cap(exc: Exception) -> bool:
    """True when a 429 means 'out until reset', not 'slow down'."""
    # Order matters: a per-minute limit must never be memoised as a daily cap.
    if _is_per_minute_limit(exc):
        return False
    text = str(exc).lower()
    return any(marker in text for marker in _DAILY_CAP_MARKERS)


def _is_account_cap(exc: Exception) -> bool:
    """True when the cap retires the whole provider rather than one model."""
    text = str(exc).lower()
    return any(marker in text for marker in _ACCOUNT_CAP_MARKERS)


def complete(prompt: str, *, max_tokens: int | None = None, strong: bool = False) -> str:
    """Return raw model text, walking providers until one answers.

    Raises LLMUnavailable rather than returning a degraded answer - a legal tool
    must fail visibly, never quietly. Callers turn that into an explicit
    abstention; none of them guess.

    `strong=True` puts the strongest configured model first. Reserved for the
    one step where the failure mode is conflating two jurisdictions rather than
    merely being terse.
    """
    chain = endpoints(strong_first=strong)
    if not chain:
        raise LLMUnavailable(
            "No generation provider is configured. Set one of "
            + ", ".join(t["api_key_env"] for t in settings.llm_chain)
            + " in .env"
        )

    last_error: Exception | None = None
    # Two scopes, because a daily cap can be either. Google meters each model
    # separately - 3.5-flash-lite can be out while 3.1-flash-lite answers in a
    # second - whereas OpenRouter's free allowance is spent by the account.
    # Retiring a whole provider on one model's 429 cost us every Gemini call for
    # 20 minutes while a working endpoint sat idle, so the scope is now read off
    # the error rather than assumed.
    exhausted_providers: set[str] = {
        tier["name"] for tier in settings.llm_chain if _is_capped(tier["name"])
    }
    exhausted_models: set[str] = {
        f"{e.provider}:{e.model}" for e in chain if _is_capped(f"{e.provider}:{e.model}")
    }

    for endpoint in chain:
        if endpoint.provider in exhausted_providers:
            continue
        if f"{endpoint.provider}:{endpoint.model}" in exhausted_models:
            continue
        # Retry hard only when there is nothing else to fall back to. With four
        # other endpoints available, spending ~16 s of exponential backoff on a
        # per-minute limit is worse than trying the next provider immediately -
        # measured: qwen3.8-27b burned four attempts before failover while
        # gpt-oss-120b was sitting idle and answered in 2.4 s.
        is_last = endpoint is chain[-1]
        attempts = settings.max_retries if is_last else min(2, settings.max_retries)
        for attempt in range(attempts):
            try:
                _pace()
                response = _client_for(endpoint).chat.completions.create(
                    model=endpoint.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=settings.temperature,
                    max_tokens=max_tokens or settings.max_tokens,
                )
                text = (response.choices[0].message.content or "").strip()
                if text:
                    return text
                # Empty content is a real failure mode, not a quirk: a thinking
                # model that spent its whole budget reasoning returns finish
                #_reason="length" and no content. Treat it as this endpoint
                # failing so the chain moves on.
                last_error = LLMUnavailable(f"{endpoint} returned empty content")
                break
            except (RateLimitError, APITimeoutError, APIError) as exc:
                last_error = exc
                if _is_daily_cap(exc):
                    if _is_account_cap(exc):
                        exhausted_providers.add(endpoint.provider)
                        _mark_capped(endpoint.provider)
                        logger.warning(
                            "%s is out of daily quota for the whole account; "
                            "skipping the rest of provider %r",
                            endpoint, endpoint.provider)
                    else:
                        scope = f"{endpoint.provider}:{endpoint.model}"
                        exhausted_models.add(scope)
                        _mark_capped(scope)
                        logger.warning(
                            "%s is out of daily quota; trying the next model on %r",
                            endpoint, endpoint.provider)
                    break
                delay = (2**attempt) + random.uniform(0, 1)
                logger.warning("%s attempt %d failed (%s); retrying in %.1fs",
                               endpoint, attempt + 1, type(exc).__name__, delay)
                time.sleep(delay)
        else:
            logger.warning("%s exhausted; trying next endpoint", endpoint)
        if endpoint is not chain[-1]:
            logger.info("Falling back from %s", endpoint)

    raise LLMUnavailable(
        f"All {len(chain)} endpoints across "
        f"{len({e.provider for e in chain})} providers failed. Last error: {last_error}"
    )


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def complete_json(prompt: str, *, max_tokens: int | None = None,
                  strong: bool = False) -> dict[str, Any]:
    """Call the model and parse a JSON object out of its reply.

    Models emit fences, preambles and trailing commentary. We strip fences, then
    take the outermost {...} span. If that still is not valid JSON we raise -
    guessing at a malformed legal answer is worse than failing.
    """
    raw = complete(prompt, max_tokens=max_tokens, strong=strong)
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
