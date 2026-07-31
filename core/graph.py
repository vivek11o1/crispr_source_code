# crispr_core/graph.py
"""
The agent loop: compact -> agent -> permission_gate -> tools -> compact -> ...

permission_gate sits between the agent's tool request and ToolNode's
execution, so CONFIRM-tier actions can no longer auto-run ungated.
Approved tool calls are tracked in state and filtered before ToolNode
runs, so denied tools are never executed even if the agent requested
multiple tools in one turn.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from states import SessionState
from compaction import compact_node
from resilience import call_with_retry
from providers import get_llm
from langchain_core.messages import ToolMessage

SYSTEM_PROMPT = """
You are crispr, an AI assistant. Your ONLY job is to fulfill the user's
exact request — no more, no less. Follow these rules strictly:

1. Read the user's prompt carefully and do EXACTLY what they asked. Do
   not explore unrelated files, do not make unsolicited edits, do not go
   on tangents, do not ask "what would you like me to do".
2. Use tools to gather whatever information you need, then give a
   complete answer in your text response. Do not stop halfway.
3. After running tools, explain the result to the user in plain text.
4. Never return only tool calls without a text explanation.
5. If you don't know something, say so. Do not invent answers.
"""


def build_graph(llm, tools: list, checkpointer, config: dict, ask_user_fn=None, stream_handler=None):
    llm_with_tools = llm.bind_tools(tools)
    summarizer_llm = get_llm(config, use_fallback=True)

    if ask_user_fn is None:
        ask_user_fn = _default_ask_user

    def compaction_node(state: SessionState) -> dict:
        return compact_node(state, summarizer_llm, config)

    def agent_node(state: SessionState) -> dict:
        summary_block = []
        if state.get("session_summary"):
            summary_block = [{
                "role": "system",
                "content": f"Session summary so far: {state['session_summary']}",
            }]

        repo_path = state.get("repo_path", ".")
        context_msg = (
            f"Working directory: {repo_path}\n"
            f"To list files in the current directory, call list_files with "
            f"path=\"{repo_path}\". To read a file, use its full path under "
            f"that directory."
        )

        system_content = SYSTEM_PROMPT
        if state["turn_count"] == 0:
            system_content = SYSTEM_PROMPT + "\n" + context_msg

        full_messages = (
            [{"role": "system", "content": system_content}]
            + summary_block
            + state["messages"]
        )
        response = call_with_retry(llm_with_tools, full_messages, config, stream_handler=stream_handler)
        return {"messages": [response], "turn_count": state["turn_count"] + 1}

    def permission_node(state: SessionState) -> dict:
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", None)
        if not tool_calls:
            return {"approved_tool_call_ids": []}

        from permissions import needs_confirmation, get_tier, allow_for_session
        from langchain_core.messages import ToolMessage

        approved_ids = []
        denied_ids = []
        for call in tool_calls:
            if needs_confirmation(call["name"], call.get("args")):
                approved = ask_user_fn(call["name"], call.get("args", {}))
                if not approved:
                    denied_ids.append(call["id"])
                else:
                    approved_ids.append(call["id"])
                    if get_tier(call["name"], call.get("args")) == "prompt":
                        allow_for_session(call["name"])
            else:
                approved_ids.append(call["id"])

        result = {"approved_tool_call_ids": approved_ids}

        if denied_ids:
            result["messages"] = [
                ToolMessage(content="User denied this action.", tool_call_id=cid)
                for cid in denied_ids
            ]

        return result

    def filtered_tools_node(state: SessionState) -> dict:
        """Execute only approved tool calls directly, add denial messages
        for denied ones. Bypasses ToolNode to avoid state ordering issues."""
        last_message = state["messages"][-1]
        tool_calls = getattr(last_message, "tool_calls", None)
        if not tool_calls:
            return {}

        approved_ids = set(state.get("approved_tool_call_ids", []))
        tool_map = {t.__name__: t for t in tools}

        # Inject state via config the same way ToolNode does
        from langchain_core.runnables import RunnableConfig
        tool_config = RunnableConfig(configurable={"state": state})

        results = []
        for tc in tool_calls:
            if tc["id"] in approved_ids:
                tool_fn = tool_map.get(tc["name"])
                if tool_fn is None:
                    results.append(ToolMessage(
                        content=f"Unknown tool: {tc['name']}",
                        tool_call_id=tc["id"],
                    ))
                    continue
                try:
                    import inspect
                    sig = inspect.signature(tool_fn)
                    needs_state = any(
                        p.name == "state"
                        for p in sig.parameters.values()
                    )
                    args = dict(tc.get("args", {}))
                    if needs_state:
                        args["state"] = state
                    result = tool_fn(**args)
                    if isinstance(result, tuple):
                        content = result[0]
                    elif isinstance(result, str):
                        content = result
                    else:
                        content = str(result)
                except Exception as e:
                    content = f"Error invoking tool '{tc['name']}': {e}"
                results.append(ToolMessage(content=content, tool_call_id=tc["id"]))
            else:
                results.append(ToolMessage(
                    content="User denied this action.",
                    tool_call_id=tc["id"],
                ))

        return {"messages": results}

    def should_continue(state: SessionState) -> str:
        last_message = state["messages"][-1]
        if state["turn_count"] >= config.get("max_turns", 25):
            return END
        if getattr(last_message, "tool_calls", None):
            return "permission_gate"
        return END

    def after_permission_gate(state: SessionState) -> str:
        approved_ids = state.get("approved_tool_call_ids", [])
        if not approved_ids:
            # All tools denied — go to agent so it sees the denials
            return "compact"
        return "tools"

    graph = StateGraph(SessionState)
    graph.add_node("compact", compaction_node)
    graph.add_node("agent", agent_node)
    graph.add_node("permission_gate", permission_node)
    graph.add_node("tools", filtered_tools_node)

    graph.set_entry_point("compact")
    graph.add_edge("compact", "agent")
    graph.add_conditional_edges(
        "agent", should_continue, {"permission_gate": "permission_gate", END: END}
    )
    graph.add_conditional_edges(
        "permission_gate", after_permission_gate, {"tools": "tools", "compact": "compact"}
    )
    graph.add_edge("tools", "compact")

    return graph.compile(checkpointer=checkpointer)


def _default_ask_user(tool_name: str, tool_args: dict) -> bool:
    print(f"\ncrispr wants to run: {tool_name}({tool_args})")
    answer = input("Allow? [y/N]: ").strip().lower()
    return answer == "y"
