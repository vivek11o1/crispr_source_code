# resilience.py
"""
Retry/backoff/fallback logic — wraps every LLM call. Exhausted retries
fall through to the configured fallback provider, not just a smaller
model on the same provider (see providers.py's get_llm(use_fallback=True)).

Also owns cooperative cancellation (AgentInterrupted) and the optional
client-side RPM guard (TokenBucket) so rapid/parallel LLM calls are paced
instead of bursting past the provider's rate limit.
"""

import threading
import time
from langchain_core.messages import AIMessageChunk
from providers import get_llm


class AgentInterrupted(Exception):
    """Raised mid-LLM-call when the user asks to stop (ESC pressed)."""


class QuotaExhausted(Exception):
    """The provider's free-tier quota is spent — NOT a transient rate limit.

    Retrying a spent quota just re-bills the full context against a dead
    key, which is exactly how a free tier gets silently drained. Raised
    fast so the user sees a clear message instead of a retry storm.
    """


class TokenBucket:
    """Minimal pacing gate: one call per (60 / rate_per_minute) seconds."""

    def __init__(self, rate_per_minute: int) -> None:
        rate = int(rate_per_minute)
        self._interval = 60.0 / rate if rate > 0 else 0.0
        self._next = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self._interval <= 0.0:
            return  # disabled (rpm_limit = 0)
        with self._lock:
            now = time.monotonic()
            if now < self._next:
                time.sleep(self._next - now)
                now = time.monotonic()
            self._next = now + self._interval


_rate_limiter = TokenBucket(0)

# Built-in per-provider caps used when config.toml has no rpm_limit set
# (the core reads config.toml directly, so it can't rely on launcher
# defaults being merged into the file).
#   groq   — 30 RPM free tier (both llama models in DEFAULTS are 30 RPM)
#   zen    — 1000 RPM per-key default in the Zen gateway limiter
#   openai — ~500 RPM entry tier (account-tier dependent)
#   claude — ~50 RPM lowest Anthropic tier (tier-dependent)
_PROVIDER_DEFAULT_RPM = {
    "groq": 30,
    "zen": 1000,
    "openai": 500,
    "claude": 50,
}


def configure_rate_limiter(cfg: dict) -> None:
    """Resolve the RPM cap for the active provider and install the bucket.

    Precedence: providers.<active>.rpm_limit > top-level rpm_limit >
    built-in per-provider default > disabled (0).
    """
    global _rate_limiter
    provider = cfg.get("active_provider", "zen")
    provider_cfg = cfg.get("providers", {}).get(provider, {})
    rpm = provider_cfg.get("rpm_limit")
    if rpm is None:
        rpm = cfg.get("rpm_limit")
    if rpm is None:
        rpm = _PROVIDER_DEFAULT_RPM.get(provider, 0)
    _rate_limiter = TokenBucket(rpm)


def acquire_rate_limiter() -> None:
    """Pace a direct LLM call (e.g. the compaction summarizer)."""
    _rate_limiter.acquire()


def call_with_retry(llm, messages, config, max_retries=5, stream_handler=None, should_cancel=None):
    for attempt in range(max_retries):
        try:
            _rate_limiter.acquire()
            return _invoke(llm, messages, stream_handler, should_cancel)
        except AgentInterrupted:
            raise
        except Exception as e:
            if _is_quota_exhausted(e):
                # Spent quota is permanent until the tier resets — every
                # retry re-sends the FULL context and gets billed. Fail
                # fast instead of draining the remaining allowance.
                raise QuotaExhausted(
                    "free-tier usage limit reached — the provider says the "
                    "quota is spent, not temporarily busy. Retrying would "
                    "just burn more tokens on the same dead key. Switch "
                    "provider/model or wait for the tier to reset."
                ) from e
            if _is_rate_limit(e):
                wait = min(2 ** attempt, 30)
                time.sleep(wait)
                continue
            raise

    if _fallback_is_redundant(config):
        # Active + fallback share the same account/key, so the fallback
        # call is guaranteed to fail the same way while re-billing the
        # whole context one more time. Skip it.
        raise QuotaExhausted(
            "all LLM retries failed and the fallback provider is the same "
            "account/key as the active provider, so falling back would just "
            "burn another full-context request. Check the provider's quota "
            "or configure a real fallback provider."
        )
    fallback_llm = get_llm(config, use_fallback=True)
    _rate_limiter.acquire()
    return _invoke(fallback_llm, messages, stream_handler, should_cancel)


def _invoke(llm, messages, stream_handler=None, should_cancel=None):
    if should_cancel is None:
        if stream_handler is None:
            return llm.invoke(messages)

        chunks = []
        for chunk in llm.stream(messages):
            chunks.append(chunk)
            content = chunk.content if isinstance(chunk.content, str) else ""
            if content:
                stream_handler(content)
        if not chunks:
            return llm.invoke(messages)

        return _merge_stream_chunks(chunks)

    # Cancellation-aware path: stream so we can bail out the instant the
    # user hits ESC instead of letting the whole call run to completion.
    chunks = []
    for chunk in llm.stream(messages):
        if should_cancel():
            raise AgentInterrupted()
        if stream_handler is not None:
            content = chunk.content if isinstance(chunk.content, str) else ""
            if content:
                stream_handler(content)
        chunks.append(chunk)
    if not chunks:
        return llm.invoke(messages)

    return _merge_stream_chunks(chunks)


def _merge_stream_chunks(chunks) -> AIMessageChunk:
    """Combine streamed AIMessageChunks into one complete message.

    ``AIMessageChunk.__add__`` keeps only the last tool-call args
    fragment, which corrupts incremental streamed tool calls. Here
    fragments with the same tool-call index are concatenated so the
    final ``tool_calls`` parse to the complete arguments.
    """
    last = chunks[-1]
    content_parts = []
    merged_calls: dict = {}
    order: list = []

    for chunk in chunks:
        if isinstance(chunk.content, str) and chunk.content:
            content_parts.append(chunk.content)
        for tcc in (chunk.tool_call_chunks or []):
            index = tcc.get("index")
            if index is None:
                continue
            entry = merged_calls.get(index)
            if entry is None:
                entry = {"name": "", "id": "", "args": ""}
                merged_calls[index] = entry
                order.append(index)
            if tcc.get("name"):
                entry["name"] = tcc["name"]
            if tcc.get("id"):
                entry["id"] = tcc["id"]
            entry["args"] += tcc.get("args") or ""

    tool_call_chunks = [
        {
            "name": merged_calls[i]["name"],
            "args": merged_calls[i]["args"],
            "id": merged_calls[i]["id"],
            "index": i,
            "type": "tool_call_chunk",
        }
        for i in order
    ]

    return AIMessageChunk(
        content="".join(content_parts),
        tool_call_chunks=tool_call_chunks,
        additional_kwargs=last.additional_kwargs,
        response_metadata=last.response_metadata,
        usage_metadata=last.usage_metadata,
        id=last.id,
    )


def _is_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    return any(x in msg for x in ["rate", "429", "413", "tokens per minute", "tpm", "rpm"])


def _is_quota_exhausted(e: Exception) -> bool:
    """True when the provider says the account/tier is OUT of quota.

    Must be checked BEFORE _is_rate_limit: Zen's exhausted-tier error is
    a 429 whose message contains "Rate limit exceeded" — which the naive
    rate-limit matcher would otherwise treat as transient and retry.
    """
    msg = str(e).lower()
    return any(x in msg for x in (
        "freeusagelimit", "free_usage_limit", "usage limit",
        "insufficient_quota", "insufficient quota", "out of quota",
        "quota exceeded", "billing", "out of credits",
    ))


def _fallback_is_redundant(config: dict) -> bool:
    """True when a fallback call would hit the same account/key as active.

    Mirrors get_llm's own degradation rules: when the fallback is
    disabled or its provider has no key, get_llm silently degrades back
    to the ACTIVE provider — so the fallback call would re-bill the same
    quota that just failed. Treat all of those as redundant.
    """
    providers = config.get("providers", {})
    active = config.get("active_provider")
    fb = config.get("fallback", {})
    fallback = fb.get("provider", active)

    if not fb.get("enabled", True):
        return True  # get_llm degrades to active
    if fallback == active:
        return True
    a_key = providers.get(active, {}).get("api_key")
    f_key = providers.get(fallback, {}).get("api_key")
    if not f_key:
        return True  # get_llm degrades to active (same key)
    return bool(a_key and a_key == f_key)