# crispr_core/compaction.py
"""
Context Compaction Node — runs before every agent call (via graph.py's
compact -> agent edge, and tools -> compact loop-back). No-ops when
under the token threshold, so it costs nothing when not needed.
files_touched is copied directly from state["edited_files"] (ground
truth) rather than LLM-inferred, to avoid two independent trackers of
the same thing drifting apart.
"""

from pydantic import BaseModel
from langchain_core.messages import RemoveMessage
from states import SessionState, SessionSummary
from resilience import acquire_rate_limiter

COMPACTION_SYSTEM_PROMPT = """
Summarize this coding session densely. Focus on: decisions made, the
current task being worked on, and any open issues or blockers. Do not
list files touched — that is tracked separately. Be dense, not
conversational.
"""


class _SummaryLLMOutput(BaseModel):
    """What the summarizer LLM actually infers — deliberately excludes
    files_touched, which comes from state directly, not the model."""
    decisions_made: list[str]
    current_task_id: str | None
    open_issues: list[str]


def _estimate_tokens(messages: list) -> int:
    # Rough heuristic: ~4 chars per token. Good enough for a threshold
    # check, not meant to be precise.
    total_chars = 0
    for m in messages:
        content = m.content if hasattr(m, "content") else m.get("content", "")
        total_chars += len(content or "")
    return total_chars // 4


def compact_node(state: SessionState, summarizer_llm, config: dict) -> dict:
    threshold = config.get("compaction_threshold_tokens", 6000)
    messages = state["messages"]

    if _estimate_tokens(messages) < threshold:
        return {}  # no-op — under threshold, nothing to do

    if len(messages) <= 4:
        return {}  # not enough history to bother compacting

    to_summarize, keep = messages[:-4], messages[-4:]

    old_summary = state.get("session_summary")
    prior_context = []
    if old_summary:
        prior_context = [{
            "role": "system",
            "content": f"Existing summary to update, not replace: {old_summary}",
        }]

    try:
        acquire_rate_limiter()
        llm_output: _SummaryLLMOutput = summarizer_llm.with_structured_output(
            _SummaryLLMOutput
        ).invoke([
            {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
            *prior_context,
            *to_summarize,
        ])
    except Exception:
        # Compaction failing should never break the session — skip this
        # round and let the LLM proceed with full (uncompacted) history.
        return {}

    full_summary = SessionSummary(
        files_touched=state.get("edited_files", []),  # ground truth, not LLM-guessed
        decisions_made=llm_output.decisions_made,
        current_task_id=llm_output.current_task_id,
        open_issues=llm_output.open_issues,
    )

    summary_message = {
        "role": "system",
        "content": f"[Session summary]: {full_summary.model_dump_json()}",
    }

    # With the add_messages reducer, state messages only grow. To
    # compact, explicitly drop the summarized messages (RemoveMessage
    # removes them from the accumulated history). The tail (keep) stays
    # untouched in state — no need to re-add it.
    removals = [
        RemoveMessage(id=_message_id(m))
        for m in to_summarize
        if _message_id(m) is not None
    ]

    return {
        "messages": removals + [summary_message],
        "session_summary": full_summary,
    }


def _message_id(m) -> str | None:
    """Return a stable id for either a LangChain message or a dict."""
    if hasattr(m, "id"):
        return getattr(m, "id", None)
    return (m or {}).get("id") if isinstance(m, dict) else None