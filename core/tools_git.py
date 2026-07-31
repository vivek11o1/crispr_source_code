# crispr_core/tools_git.py
"""
Local git tools — safe, reversible, never leave the user's machine.
Lower trust tier than tools_github.py. All shell out to the real git
binary; env_check.py's `git` check is what crispr doctor uses to catch
a missing installation before these ever get called.
"""

import subprocess
from typing import Annotated
from langgraph.prebuilt import InjectedState
from states import SessionState


def _run_git(args: list[str], cwd: str, timeout: int = 15) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output or "(no output)"
    except FileNotFoundError:
        return False, "git not found. Run 'crispr doctor' for details."
    except subprocess.TimeoutExpired:
        return False, f"git command timed out after {timeout}s"


def git_diff(
    path: str = ".",
    state: Annotated[SessionState, InjectedState] = None,
) -> str:
    """AUTO-tier."""
    repo_path = state["repo_path"] if state else "."
    ok, output = _run_git(["diff", path], cwd=repo_path)
    return output if ok else f"Error: {output}"


def git_status(
    state: Annotated[SessionState, InjectedState] = None,
) -> str:
    """AUTO-tier."""
    repo_path = state["repo_path"] if state else "."
    ok, output = _run_git(["status", "--short"], cwd=repo_path)
    if not ok:
        return f"Error: {output}"
    return output if output.strip() else "Working tree clean."


def git_log(
    max_count: int = 10,
    state: Annotated[SessionState, InjectedState] = None,
) -> str:
    """AUTO-tier."""
    repo_path = state["repo_path"] if state else "."
    ok, output = _run_git(["log", f"-{max_count}", "--oneline"], cwd=repo_path)
    return output if ok else f"Error: {output}"


def git_commit(
    message: str,
    state: Annotated[SessionState, InjectedState] = None,
) -> str:
    """PROMPT-tier."""
    repo_path = state["repo_path"] if state else "."
    ok, output = _run_git(["add", "-A"], cwd=repo_path)
    if not ok:
        return f"Error staging changes: {output}"
    ok, output = _run_git(["commit", "-m", message], cwd=repo_path)
    return output if ok else f"Error committing: {output}"


def git_branch_create(
    name: str,
    state: Annotated[SessionState, InjectedState] = None,
) -> tuple[str, dict]:
    """PROMPT-tier. Only tool that mutates active_branch — returns a
    state update as a direct side effect of actually switching branches."""
    repo_path = state["repo_path"] if state else "."
    ok, output = _run_git(["checkout", "-b", name], cwd=repo_path)
    if not ok:
        return f"Error creating branch: {output}", {}
    return f"Created and switched to branch '{name}'", {"active_branch": name}