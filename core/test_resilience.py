"""Extreme-case tests for resilience.py / graph.py token-safety fixes.

Standalone script (no pytest), same style as test_session_banner.py.
Run:  core\\core_venv\\Scripts\\python.exe core\\test_resilience.py

Covers the token-drain regressions found in sessions.db:
  1. FreeUsageLimitError (out of quota) must fail FAST — exactly 1 request.
  2. Transient 429 must retry then succeed.
  3. Retries exhausted + redundant fallback (same key) must NOT make a
     fallback request.
  4. Retries exhausted + real cross-provider fallback must still work.
  5. Non-rate-limit errors must raise immediately (no retry storm).
  6. AgentInterrupted must propagate untouched.
  7. ESC stop-at-node-boundary: resuming a session must not re-run a
     committed LLM call.
  8. _is_quota_exhausted / _fallback_is_redundant edge cases.
  9. TokenBucket pacing math.
"""

import sys
import os
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import AIMessageChunk

import resilience
from resilience import (
    AgentInterrupted,
    QuotaExhausted,
    TokenBucket,
    call_with_retry,
    _is_quota_exhausted,
    _fallback_is_redundant,
)


class FakeLLM:
    """stream()/invoke() share one outcome queue; Exceptions raise."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def _next_outcome(self):
        self.calls += 1
        return self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        outcome = self._next_outcome()
        if isinstance(outcome, Exception):
            raise outcome
        return AIMessageChunk(content=outcome)

    def stream(self, messages):
        outcome = self._next_outcome()
        if isinstance(outcome, Exception):
            raise outcome
        yield AIMessageChunk(content=outcome)


QUOTA_ERR = Exception(
    "RateLimitError: Error code: 429 - {'error': {'type': 'FreeUsageLimitError', "
    "'message': 'Error from provider (Console): Rate limit exceeded. Please try again later.'}}"
)
TRANSIENT_ERR = Exception("RateLimitError: Error code: 429 - Too many requests, retry after 2s")
AUTH_ERR = Exception("AuthenticationError: Error code: 401 - Incorrect API key")

# Default config: zen active, zen fallback (the config.toml on disk)
CFG_SAME_KEY = {
    "active_provider": "zen",
    "providers": {"zen": {"api_key": "K", "model": "m"}, "groq": {"api_key": "", "model": "g"}},
    "fallback": {"enabled": True, "provider": "zen"},
}
# Real cross-provider fallback
CFG_CROSS = {
    "active_provider": "zen",
    "providers": {"zen": {"api_key": "K1", "model": "m"}, "groq": {"api_key": "K2", "model": "g"}},
    "fallback": {"enabled": True, "provider": "groq"},
}
CFG_FALLBACK_DISABLED = {
    "active_provider": "zen",
    "providers": {"zen": {"api_key": "K1", "model": "m"}, "groq": {"api_key": "K2", "model": "g"}},
    "fallback": {"enabled": False, "provider": "groq"},
}
CFG_FALLBACK_NO_KEY = {
    "active_provider": "zen",
    "providers": {"zen": {"api_key": "K1", "model": "m"}, "groq": {"api_key": "", "model": "g"}},
    "fallback": {"enabled": True, "provider": "groq"},
}


def _fast(config=None):
    """Neutralize sleeping + pacing so tests run in milliseconds."""
    resilience._rate_limiter = TokenBucket(0)
    patcher = patch.object(resilience.time, "sleep")
    patcher.start()
    return patcher


passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[PASS] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {extra}")


def expect_raises(exc_type, fn, name):
    global passed, failed
    try:
        fn()
    except exc_type:
        passed += 1
        print(f"[PASS] {name}")
        return True
    except Exception as e:
        failed += 1
        print(f"[FAIL] {name} (wrong exception: {type(e).__name__}: {e})")
        return False
    failed += 1
    print(f"[FAIL] {name} (nothing raised)")
    return False


# ── 1. Out-of-quota must fail fast: exactly 1 request, QuotaExhausted ──
def test_quota_fail_fast():
    p = _fast()
    try:
        llm = FakeLLM([QUOTA_ERR])
        config = dict(CFG_SAME_KEY)
        ok = expect_raises(
            QuotaExhausted,
            lambda: call_with_retry(llm, ["m"], config),
            "1a. FreeUsageLimitError -> QuotaExhausted",
        )
        check("1b. quota fail-fast makes exactly 1 request", llm.calls == 1, f"(calls={llm.calls})")
        return ok
    finally:
        p.stop()


# ── 2. Transient 429 retries then succeeds ──
def test_transient_then_success():
    p = _fast()
    try:
        llm = FakeLLM([TRANSIENT_ERR, TRANSIENT_ERR, "hello"])
        result = call_with_retry(llm, ["m"], dict(CFG_SAME_KEY))
        check("2a. transient 429 retried then succeeded", llm.calls == 3, f"(calls={llm.calls})")
        check("2b. merged content correct", result.content == "hello")
        return True
    finally:
        p.stop()


# ── 3. Retries exhausted + same-key fallback: NO fallback request ──
def test_exhausted_redundant_fallback_skipped():
    p = _fast()
    try:
        llm = FakeLLM([TRANSIENT_ERR])
        config = dict(CFG_SAME_KEY)  # zen->zen, same key
        ok = expect_raises(
            QuotaExhausted,
            lambda: call_with_retry(llm, ["m"], config, max_retries=3),
            "3a. exhausted + redundant fallback -> QuotaExhausted",
        )
        check(
            "3b. no redundant fallback request (calls == max_retries)",
            llm.calls == 3,
            f"(calls={llm.calls}, expected 3)",
        )
        return ok
    finally:
        p.stop()


# ── 4. Retries exhausted + real fallback provider: fallback is used ──
def test_exhausted_real_fallback_used():
    p = _fast()
    try:
        primary = FakeLLM([TRANSIENT_ERR])
        fallback_llm = FakeLLM(["from fallback"])
        with patch.object(resilience, "get_llm", return_value=fallback_llm):
            result = call_with_retry(primary, ["m"], dict(CFG_CROSS), max_retries=2)
        check("4a. fallback provider was called", fallback_llm.calls == 1, f"(calls={fallback_llm.calls})")
        check("4b. fallback response returned", result.content == "from fallback")
        check("4c. primary made exactly max_retries calls", primary.calls == 2, f"(calls={primary.calls})")
        return True
    finally:
        p.stop()


# ── 5. Non-rate-limit errors raise immediately ──
def test_auth_error_no_retry():
    p = _fast()
    try:
        llm = FakeLLM([AUTH_ERR])
        ok = expect_raises(
            Exception,
            lambda: call_with_retry(llm, ["m"], dict(CFG_SAME_KEY), max_retries=5),
            "5a. 401 raises through",
        )
        check("5b. 401 made exactly 1 request", llm.calls == 1, f"(calls={llm.calls})")
        return ok
    finally:
        p.stop()


# ── 6. AgentInterrupted propagates untouched ──
def test_agent_interrupted_propagates():
    p = _fast()
    try:
        llm = FakeLLM([AgentInterrupted()])
        ok = expect_raises(
            AgentInterrupted,
            lambda: call_with_retry(llm, ["m"], dict(CFG_SAME_KEY), max_retries=5),
            "6a. AgentInterrupted re-raised",
        )
        check("6b. AgentInterrupted not retried", llm.calls == 1, f"(calls={llm.calls})")
        return ok
    finally:
        p.stop()


# ── 7. Graph integration: 1 LLM call per turn; resume does not re-run ──
def test_graph_integration():
    from langgraph.checkpoint.memory import InMemorySaver
    import graph as graph_mod

    p = _fast()
    try:
        # 7a. Happy path: one user message -> exactly 1 LLM call.
        llm = FakeLLM(["hello from agent"])
        cp = InMemorySaver()
        g = graph_mod.build_graph(
            llm, [], cp, dict(CFG_SAME_KEY),
            stream_handler=lambda t: None,
        )
        initial = {
            "messages": [{"role": "user", "content": "hi"}],
            "turn_count": 0,
            "task_plan": [],
            "edited_files": [],
            "repo_path": ".",
            "active_branch": "main",
            "session_summary": None,
            "approved_tool_call_ids": [],
        }
        events = list(g.stream(initial, {"configurable": {"thread_id": "t1"}}, stream_mode="values"))
        check("7a. one turn -> one LLM call", llm.calls == 1, f"(calls={llm.calls})")
        check(
            "7a2. response in final state",
            any(m.content == "hello from agent" for m in events[-1]["messages"]),
        )

        # 7b. Simulate ESC stop-at-node-boundary: break right after the
        # agent node commits, then resume. The committed LLM call must
        # NOT be re-run (with the old in-stream cancel it was re-billed
        # in full on resume).
        llm2 = FakeLLM(["first", "second"])
        cp2 = InMemorySaver()
        g2 = graph_mod.build_graph(
            llm2, [], cp2, dict(CFG_SAME_KEY),
            stream_handler=lambda t: None,
        )
        cfg2 = {"configurable": {"thread_id": "t2"}}
        gen = g2.stream(initial, cfg2, stream_mode="values")
        for ev in gen:
            if any(getattr(m, "type", None) == "ai" for m in ev["messages"]):
                break  # ESC pressed right after the agent node committed
        check(
            "7b. interrupt after commit leaves exactly 1 LLM call",
            llm2.calls == 1,
            f"(calls={llm2.calls})",
        )
        # resume with a follow-up message -> turn 2, exactly +1 call
        resume = {"messages": [{"role": "user", "content": "continue"}]}
        list(g2.stream(resume, cfg2, stream_mode="values"))
        check(
            "7b2. resume does NOT re-run committed call (2 total)",
            llm2.calls == 2,
            f"(calls={llm2.calls})",
        )

        # 7c. Quota error propagates through the graph and makes 1 request.
        llm3 = FakeLLM([QUOTA_ERR])
        cp3 = InMemorySaver()
        g3 = graph_mod.build_graph(
            llm3, [], cp3, dict(CFG_SAME_KEY),
            stream_handler=lambda t: None,
        )
        raised = False
        try:
            list(g3.stream(initial, {"configurable": {"thread_id": "t3"}}, stream_mode="values"))
        except QuotaExhausted:
            raised = True
        check("7c. QuotaExhausted propagates from graph.stream", raised)
        check("7c2. quota error makes exactly 1 LLM call", llm3.calls == 1, f"(calls={llm3.calls})")

        # 7d. call_with_retry is invoked WITHOUT should_cancel (the
        # mid-stream AgentInterrupted path is no longer wired up).
        with patch.object(graph_mod, "call_with_retry", wraps=graph_mod.call_with_retry) as spy:
            llm4 = FakeLLM(["ok"])
            cp4 = InMemorySaver()
            g4 = graph_mod.build_graph(
                llm4, [], cp4, dict(CFG_SAME_KEY),
                stream_handler=lambda t: None,
            )
            list(g4.stream(initial, {"configurable": {"thread_id": "t4"}}, stream_mode="values"))
            kwargs = [c.kwargs for c in spy.call_args_list]
            check("7d. no should_cancel passed to call_with_retry", all("should_cancel" not in k for k in kwargs))
        return True
    finally:
        p.stop()


# ── 8. Detection helpers, edge cases ──
def test_detection_helpers():
    check("8a. FreeUsageLimitError detected", _is_quota_exhausted(QUOTA_ERR))
    check("8b. transient 429 NOT quota", not _is_quota_exhausted(TRANSIENT_ERR))
    check("8c. auth 401 NOT quota", not _is_quota_exhausted(AUTH_ERR))
    check("8d. insufficient_quota detected", _is_quota_exhausted(
        Exception("openai.insufficient_quota: You exceeded your current quota")))
    check("8e. empty message not quota", not _is_quota_exhausted(Exception("")))
    check("8f. plain 'rate' string not quota", not _is_quota_exhausted(Exception("rate limit")))

    check("8g. same provider redundant", _fallback_is_redundant(CFG_SAME_KEY))
    check("8h. cross-provider not redundant", not _fallback_is_redundant(CFG_CROSS))
    check("8i. fallback disabled redundant", _fallback_is_redundant(CFG_FALLBACK_DISABLED))
    check("8j. fallback w/o key redundant (degrades to active)", _fallback_is_redundant(CFG_FALLBACK_NO_KEY))

    same_key_cross = {
        "active_provider": "zen",
        "providers": {"zen": {"api_key": "K"}, "groq": {"api_key": "K"}},
        "fallback": {"enabled": True, "provider": "groq"},
    }
    check("8k. different provider, same key redundant", _fallback_is_redundant(same_key_cross))

    # 8l. Ordering guarantee: quota check wins over rate-limit match even
    # when the message ALSO contains "rate limit exceeded".
    check("8l. quota beats rate-limit matcher", _is_quota_exhausted(QUOTA_ERR))
    return True


# ── 9. TokenBucket pacing math ──
def test_token_bucket():
    b = TokenBucket(0)
    t0 = time.monotonic()
    b.acquire()
    b.acquire()
    check("9a. rpm=0 means no pacing", time.monotonic() - t0 < 0.25)

    b = TokenBucket(600)  # 0.1s interval
    t0 = time.monotonic()
    b.acquire()
    b.acquire()
    elapsed = time.monotonic() - t0
    check("9b. 600rpm paces to ~0.1s", elapsed >= 0.09, f"(elapsed={elapsed:.3f})")
    return True


if __name__ == "__main__":
    tests = [
        test_quota_fail_fast,
        test_transient_then_success,
        test_exhausted_redundant_fallback_skipped,
        test_exhausted_real_fallback_used,
        test_auth_error_no_retry,
        test_agent_interrupted_propagates,
        test_graph_integration,
        test_detection_helpers,
        test_token_bucket,
    ]
    for t in tests:
        t()
    print(f"\n==== {passed} passed, {failed} failed ====")
    sys.exit(1 if failed else 0)
