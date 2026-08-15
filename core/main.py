# crispr_core/main.py
"""
Runtime entrypoint — compiles to crispr-core(.exe). Invoked by the
launcher via subprocess, never run directly by the user. Reads config
directly from the same config.toml the launcher already wrote to
(path passed via CRISPR_CONFIG_PATH), resolves the session, builds the
graph, and runs it — now rendering through CRISPRUI instead of print().
"""

import argparse
import sys
import tomllib
import os
import subprocess
import threading
import time
import uuid

try:
    import msvcrt  # Windows-only console key polling (no extra deps)
except ImportError:
    msvcrt = None

from states import SessionState
from providers import get_llm
from tools import read_file, write_file, edit_file, list_files, grep, run_shell
from tools_git import git_diff, git_status, git_log, git_commit, git_branch_create
from tools_github import (
    github_push as _github_push,
    github_create_pr as _github_create_pr,
    github_fetch_repo_info as _github_fetch_repo_info,
    github_fetch_issues as _github_fetch_issues,
)
from manage_task import manage_tasks
from persistence import get_checkpointer
from graph import build_graph
from resilience import AgentInterrupted, QuotaExhausted, configure_rate_limiter
from ui import CRISPRUI


def load_config_from_env() -> dict:
    config_path = os.environ.get("CRISPR_CONFIG_PATH")
    if not config_path or not os.path.exists(config_path):
        raise RuntimeError(
            "No config passed from launcher. crispr-core must be invoked via the crispr launcher."
        )
    with open(config_path, "rb") as f:  # tomllib requires binary mode
        return tomllib.load(f)


def get_current_branch(repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_path, capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        return result.stdout.strip() or "unknown"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def build_initial_state(prompt: str, repo_path: str) -> SessionState:
    return {
        "messages": [{"role": "user", "content": prompt}],
        "turn_count": 0,
        "task_plan": [],
        "edited_files": [],
        "repo_path": repo_path,
        "active_branch": get_current_branch(repo_path),
        "session_summary": None,
        "approved_tool_call_ids": [],
    }


class EscInterceptor:
    """Watches for the ESC key in a background thread while the graph runs.

    On Windows this polls the console with ``msvcrt`` (no dependencies).
    Pressing ESC mid-process sets ``interrupted``; the caller can then stop
    the current run and return to the same session's prompt. The thread
    only reads keys while the graph is executing, so it never steals
    keystrokes meant for the input prompt.
    """

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._interrupted = threading.Event()
        self._paused = threading.Event()

    def start(self) -> None:
        """Clear any prior interrupt and spawn a fresh listener thread."""
        self._interrupted.clear()
        self._stop.clear()
        self._paused.clear()
        threading.Thread(target=self._listen, daemon=True).start()

    def stop(self) -> None:
        """Signal the listener thread to exit (takes effect within 50ms)."""
        self._stop.set()

    def pause(self) -> None:
        """Stop polling while a blocking console read (permission prompt)
        is active, so it never steals the user's approval keystrokes."""
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    @property
    def interrupted(self) -> bool:
        return self._interrupted.is_set()

    def _listen(self) -> None:
        while not self._stop.is_set():
            if self._paused.is_set():
                time.sleep(0.05)
                continue
            if msvcrt and msvcrt.kbhit() and msvcrt.getwch() == "\x1b":
                self._interrupted.set()
                return
            time.sleep(0.05)


class NoopEscInterceptor:
    """Non-Windows fallback — ESC interruption is unavailable."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def pause(self) -> None:
        pass

    def resume(self) -> None:
        pass

    @property
    def interrupted(self) -> bool:
        return False


def main():
    parser = argparse.ArgumentParser(prog="crispr-core")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--session", default=None)
    parser.add_argument("--once", action="store_true",
                        help="Answer a single prompt and exit (skip interactive loop).")
    args = parser.parse_args()

    config = load_config_from_env()
    configure_rate_limiter(config)
    repo_path = os.getcwd()
    active_branch = get_current_branch(repo_path)

    # Wrap GitHub tools so config is injected via closure instead of
    # being exposed in the tool schema (the LLM can't provide it).
    def github_push(owner_repo: str, branch: str):
        """Push a branch to a GitHub remote repository."""
        return _github_push(owner_repo, branch, config=config)

    def github_create_pr(owner_repo: str, title: str, body: str, base: str):
        """Create a pull request on a GitHub repository."""
        return _github_create_pr(owner_repo, title, body, base, config=config)

    def github_fetch_repo_info(owner_repo: str):
        """Fetch repository information from GitHub."""
        return _github_fetch_repo_info(owner_repo, config=config)

    def github_fetch_issues(owner_repo: str, state_filter: str = "open"):
        """Fetch issues from a GitHub repository."""
        return _github_fetch_issues(owner_repo, state_filter=state_filter, config=config)

    ALL_TOOLS = [
        read_file, write_file, edit_file, list_files, grep, run_shell,
        git_diff, git_status, git_log, git_commit, git_branch_create,
        github_push, github_create_pr, github_fetch_repo_info, github_fetch_issues,
        manage_tasks,
    ]

    checkpointer = get_checkpointer()
    llm = get_llm(config)

    thread_id = args.session or str(uuid.uuid4())[:8]
    graph_config = {"configurable": {"thread_id": thread_id}}

    is_resumed_session = bool(args.session)
    if args.session:
        try:
            existing = checkpointer.get_tuple(graph_config)
        except Exception:
            existing = None
        if existing:
            input_state = {"messages": [{"role": "user", "content": args.prompt}]}
        else:
            is_resumed_session = False
            input_state = build_initial_state(args.prompt, repo_path)
    else:
        input_state = build_initial_state(args.prompt, repo_path)

    # UI setup — every value here comes from something we already have
    # (config, thread_id, repo_path, active_branch), never regenerated
    # independently by the UI layer. Built BEFORE the graph, since
    # ask_user_fn (used by permission_gate inside the graph) needs it.
    active_provider = config["active_provider"]
    model_name = config["providers"][active_provider]["model"]

    ui = CRISPRUI(
        session_id=thread_id,
        model=model_name,
        provider=active_provider,
        repo_path=repo_path,
        git_branch=active_branch,
        tools_loaded=len(ALL_TOOLS),
    )

    interceptor = EscInterceptor() if msvcrt else NoopEscInterceptor()

    # ADDED: UI-based confirmation prompt, replaces graph.py's plain
    # print()/input() fallback for CONFIRM/PROMPT-tier tool calls. The
    # ESC interceptor is paused while this blocks on input() so it can
    # never swallow the user's approval keystroke.
    def ask_user_fn(tool_name: str, tool_args: dict) -> bool:
        ui.console.print(
            f"\n[bold yellow]crispr wants to run:[/bold yellow] "
            f"[cyan]{tool_name}[/cyan]({tool_args})"
        )
        interceptor.pause()
        try:
            answer = ui.console.input("[bold]Allow? \\[y/N]: [/bold]").strip().lower()
        finally:
            interceptor.resume()
        return answer == "y"

    # Streams the model's reply token-by-token under a heading naming
    # the generating process (the active model). The AIMessage state
    # event emitted later is deduped against this live stream in
    # CRISPRUI._render_one via the streaming renderer's active flag.
    def stream_handler(token: str) -> None:
        if not ui.is_streaming:
            ui.begin_stream(process_name=ui.info.model)
        ui.feed_stream(token)

    graph = build_graph(
        llm, ALL_TOOLS, checkpointer, config,
        ask_user_fn=ask_user_fn, stream_handler=stream_handler,
    )

    if not is_resumed_session:
        ui.startup()

    try:
        at_prompt = False
        while True:
            if at_prompt:
                next_prompt = ui.get_user_input()
                if next_prompt is None:
                    break  # EOF / Ctrl+C
                command = next_prompt.strip()
                if command.lower() in ("exit", "quit", "/exit"):
                    break
                if not command:
                    continue
                if command.startswith("/"):
                    if ui.handle_command(command):
                        break
                    continue
                input_state = {"messages": [{"role": "user", "content": command}]}

            at_prompt = True
            interceptor.start()
            interrupted = False
            try:
                for event in graph.stream(input_state, graph_config, stream_mode="values"):
                    if interceptor.interrupted:
                        interrupted = True
                        break
                    ui.render_event(None, state=event)
            except AgentInterrupted:
                interrupted = True
            except QuotaExhausted as e:
                ui.console.print(f"\n[bold red]free-tier quota exhausted:[/bold red] {e}")
                ui.shutdown(session_id=thread_id, resumable=True)
                sys.exit(1)
            finally:
                interceptor.stop()

            if interrupted:
                ui.console.print(
                    "\n[bold yellow]⏹ interrupted[/bold yellow] — "
                    "[dim]session state saved, still in this session[/dim]"
                )
                if args.once:
                    break
                continue

            if args.once:
                break
    except Exception:
        import traceback
        ui.console.print("\n[bold red]session crashed unexpectedly[/bold red]")
        ui.console.print(traceback.format_exc())
        ui.shutdown(session_id=thread_id, resumable=True)
        sys.exit(1)

    ui.shutdown(session_id=thread_id, resumable=True)


if __name__ == "__main__":
    main()