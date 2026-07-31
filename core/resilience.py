# resilience.py
"""
Retry/backoff/fallback logic — wraps every LLM call. Exhausted retries
fall through to the configured fallback provider, not just a smaller
model on the same provider (see providers.py's get_llm(use_fallback=True)).
"""

import time
from langchain_core.messages import AIMessageChunk
from providers import get_llm


def call_with_retry(llm, messages, config, max_retries=5, stream_handler=None):
    for attempt in range(max_retries):
        try:
            return _invoke(llm, messages, stream_handler)
        except Exception as e:
            if _is_rate_limit(e):
                wait = min(2 ** attempt, 30)
                time.sleep(wait)
                continue
            raise

    fallback_llm = get_llm(config, use_fallback=True)
    return _invoke(fallback_llm, messages, stream_handler)


def _invoke(llm, messages, stream_handler=None):
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