# crispr_core/permissions.py
"""
Permission Gate — sits between the agent's tool request and actual
execution. This is the piece that was missing from graph.py: without it,
CONFIRM-tier actions (github_push, github_create_pr) would auto-run
ungated the moment ToolNode processes them.

v0.1: flat per-tool tiers, plus a small allowlist for run_shell commands.
v0.1.1 (deferred): per-repo trust settings, richer ruleset — see roadmap.
"""

from typing import Literal

Tier = Literal["auto", "prompt", "confirm"]

PERMISSION_TIERS: dict[str, Tier] = {
    # AUTO — read-only, safe to run without asking
    "read_file": "auto",
    "grep": "auto",
    "list_files": "auto",
    "git_diff": "auto",
    "git_status": "auto",
    "git_log": "auto",
    "manage_tasks": "auto",

    # PROMPT — local, reversible, but should ask (once per session, allowlistable)
    "write_file": "prompt",
    "edit_file": "prompt",
    "run_shell": "prompt",
    "git_commit": "prompt",
    "git_branch_create": "prompt",

    # CONFIRM — remote, externally visible, always ask, never allowlisted
    "github_push": "confirm",
    "github_create_pr": "confirm",
    "github_fetch_repo_info": "confirm",
    "github_fetch_issues": "confirm",
}

# Known-safe run_shell commands that can auto-run despite run_shell's
# default PROMPT tier — matches the "let tests run without interrupting
# every time" design from earlier.
RUN_SHELL_ALLOWLIST = [
    "pytest", "python -m pytest", "npm test", "npm run test",
    "yarn test", "cargo test", "go test",
]

# Tools the user has approved for the rest of THIS session (in-memory,
# not persisted). Populated by main.py when the user answers "yes, and
# don't ask again this session" to a PROMPT-tier request.
_session_allowlist: set[str] = set()


def get_tier(tool_name: str, tool_args: dict | None = None) -> Tier:
    if tool_name == "run_shell" and tool_args:
        command = tool_args.get("command", "")
        if any(command.strip().startswith(safe) for safe in RUN_SHELL_ALLOWLIST):
            return "auto"

    return PERMISSION_TIERS.get(tool_name, "confirm")  # unknown tool -> safest default


def allow_for_session(tool_name: str) -> None:
    _session_allowlist.add(tool_name)


def needs_confirmation(tool_name: str, tool_args: dict | None = None) -> bool:
    tier = get_tier(tool_name, tool_args)
    if tier == "auto":
        return False
    if tier == "prompt" and tool_name in _session_allowlist:
        return False
    return True  # prompt (not yet allowlisted) or confirm — always ask


def permission_gate(state, ask_user_fn) -> dict:
    """Graph node. Inspects the last message's tool_calls; for anything
    needing confirmation, calls ask_user_fn(tool_name, tool_args) -> bool.
    Denied calls are converted into a ToolMessage explaining the denial,
    so the model sees it and can adjust — same 'never crash, inform the
    model' pattern as every other tool failure."""
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        return {}

    denied_ids = []
    for call in tool_calls:
        if needs_confirmation(call["name"], call.get("args")):
            approved = ask_user_fn(call["name"], call.get("args", {}))
            if not approved:
                denied_ids.append(call["id"])
            elif get_tier(call["name"], call.get("args")) == "prompt":
                allow_for_session(call["name"])

    if not denied_ids:
        return {}

    from langchain_core.messages import ToolMessage
    denial_messages = [
        ToolMessage(content="User denied this action.", tool_call_id=cid)
        for cid in denied_ids
    ]
    return {"messages": denial_messages}