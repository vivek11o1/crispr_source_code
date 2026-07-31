"""Main UI orchestrator – wires all components together.

This is the ORIGINAL uploaded CRISPRUI class, patched in the places
marked PATCH below to remove the coupling issues flagged earlier
(hardcoded model/provider, its own SESSION_ID/git-branch generation),
plus one addition marked ADDED: render_event(), the real bridge from
graph.stream()'s LangChain messages to this UI's existing imperative
methods (show_tool_card, begin_stream/feed_stream/end_stream, etc.) —
replacing build_demo_response()'s fake data with real agent output.
"""

from __future__ import annotations

import io
import sys
import time
from typing import TYPE_CHECKING, Optional

from rich.console import Console, Group
from rich.text import Text

from . import utils
from .banner import Banner
from .dashboard import Dashboard
from .status import StatusBar
from .thinking import ThinkingPanel
from .streaming import StreamingRenderer
from .tool_cards import ToolCard, ToolTimeline
from .diff_view import DiffViewer
from .notifications import NotificationManager
from .prompt import PromptWidget, CommandPalette
from .theme import ThemeManager

if TYPE_CHECKING:
    pass


class CRISPRUI:
    """Top-level UI manager that owns all sub-components.

    Args:
        session_id: The REAL thread_id from crispr_core/main.py — not
            generated here (PATCH: was utils.SESSION_ID, its own uuid).
        model: Model name — pulled from config by the caller
            (PATCH: was hardcoded default "claude-sonnet-4-20250514").
        provider: Provider name — pulled from config by the caller
            (PATCH: was hardcoded default "anthropic").
        repo_path: SessionState["repo_path"], passed in explicitly.
        git_branch: SessionState["active_branch"], passed in explicitly
            (PATCH: was fetched independently via its own subprocess call
            in utils.gather_system_info — now the caller supplies it,
            single source of truth).
        theme_name: Initial theme name.
        mcp_servers: Count for display, defaults to 0 until v0.1.2 wires
            real MCP support.
        tools_loaded: Count for display — pass len(ALL_TOOLS) from main.py.
    """

    def __init__(
        self,
        session_id: str,
        model: str,
        provider: str,
        repo_path: str,
        git_branch: str = "",
        theme_name: str = "orange",
        mcp_servers: int = 0,
        tools_loaded: int = 0,
    ) -> None:
        self._theme = ThemeManager(default=theme_name)
        out_file = sys.stdout
        if (hasattr(out_file, "encoding") and out_file.encoding
                and out_file.encoding.lower() in ("cp1252", "ascii")):
            try:
                out_file.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
        self._console = Console(
            file=out_file,
            theme=self._theme.get_rich_theme(),
            highlight=False,
            color_system="truecolor",
            legacy_windows=False,
        )

        # PATCH: was utils.gather_system_info(model=model, provider=provider)
        # — that version generated its own SESSION_ID at import time and
        # shelled out to git independently. Now everything is passed in,
        # so there's exactly one source of truth for each value.
        self._info = utils.build_system_info(
            session_id=session_id,
            model=model,
            provider=provider,
            repo_path=repo_path,
            git_branch=git_branch,
            mcp_servers=mcp_servers,
            tools_loaded=tools_loaded,
        )

        # Sub-components
        self._banner = Banner(self._theme)
        self._dashboard = Dashboard(self._theme)
        self._status = StatusBar(self._theme)
        self._thinking = ThinkingPanel(self._theme)
        self._streaming = StreamingRenderer(self._theme)
        self._timeline = ToolTimeline(self._theme)
        self._diff_viewer = DiffViewer(self._theme)
        self._notifications = NotificationManager(self._theme)
        self._prompt = PromptWidget(self._theme)
        self._command_palette = CommandPalette(self._theme)

        # History for scrolling
        self._history: list[Group] = []
        self._history_index: int = -1

        # tracks in-flight tool calls by id, so render_event()
        # can match a later ToolMessage result back to the tool call its
        # originating AIMessage.tool_calls entry described.
        self._pending_calls: dict[str, dict] = {}
        # tracks already-rendered message ids (stream_mode="values"
        # emits the same message through multiple graph nodes)
        self._seen_msg_ids: set[str] = set()

        self._live = None
        self._running = False
        self._banner_shown: bool = False

    # ── Properties ─────────────────────────────────────────────────

    @property
    def console(self) -> Console:
        return self._console

    @property
    def theme(self) -> ThemeManager:
        return self._theme

    @property
    def info(self) -> utils.SystemInfo:
        return self._info

    # ── Startup ────────────────────────────────────────────────────

    def startup(self) -> None:
        """Run the welcome screen with banner animation.

        The banner animation plays only once per CRISPRUI instance
        (i.e. once per CLI session). Subsequent calls skip the
        animation but still render the welcome panel. A new
        CRISPRUI instance (new session) resets this state.
        """
        self._console.clear()
        if not self._banner_shown:
            self._banner.render_startup()
            self._banner_shown = True
            self._console.clear()
        self._render_welcome()

    def _render_welcome(self) -> None:
        self._console.print()
        self._console.print(self._banner.render(self._info, show_info=True))
        self._console.print()
        self._console.print(self._dashboard.render(self._info))
        self._console.print()
        self._console.print(self._status.render(self._info))
        self._console.print()

    # ── Notifications ──────────────────────────────────────────────

    def notify(self, message: str, kind: str = "info") -> None:
        self._notifications.push(message, kind)
        rendered = self._notifications.render()
        if rendered:
            self._console.print(rendered)

    # ── Thinking ───────────────────────────────────────────────────

    def show_thinking(self, phase: str = "Thinking") -> None:
        self._thinking.start(phase)
        self._console.print(self._thinking.render())

    def update_thinking(self, prompt_tokens: int = 0, output_tokens: int = 0,
                         tool: str = "", phase: str = "") -> None:
        if prompt_tokens or output_tokens:
            self._thinking.update_tokens(prompt_tokens, output_tokens)
        if tool:
            self._thinking.set_tool(tool)
        if phase:
            self._thinking.set_phase(phase)
        self._console.print(self._thinking.render())

    def hide_thinking(self) -> None:
        self._thinking.stop()
        self._console.print(self._thinking.render())

    # ── Streaming ──────────────────────────────────────────────────

    @property
    def is_streaming(self) -> bool:
        """Whether a stream is currently in progress."""
        return self._streaming.active

    def begin_stream(self, process_name: Optional[str] = None) -> None:
        self._streaming.begin(process_name or self._info.model)
        self._console.print(self._streaming.render_heading())
        self._console.print()

    def feed_stream(self, token: str) -> None:
        self._streaming.feed(token)
        self._console.print(token, end="", highlight=False)

    def end_stream(self) -> str:
        self._streaming.end()
        self._console.print()
        self._console.print(self._streaming.render_meta(complete=True))
        text = self._streaming.text
        self._history.append(text)
        return text

    # ── Tool Cards ─────────────────────────────────────────────────

    def show_tool_card(self, tool_name: str, description: str, detail: str = "",
                        duration: float = 0.0, success: bool = True) -> None:
        card = ToolCard(tool_name=tool_name, description=description, detail=detail,
                         duration=duration, success=success, theme=self._theme)
        self._console.print(card.render())

    # ── Timeline ───────────────────────────────────────────────────

    def add_timeline_step(self, label: str, completed: bool = False, duration: float = 0.0) -> None:
        self._timeline.add_step(label, completed, duration)

    def render_timeline(self) -> None:
        self._console.print(self._timeline.render())

    def clear_timeline(self) -> None:
        self._timeline.clear()

    # ── Diff Viewer ────────────────────────────────────────────────

    def show_diff(self, old: str, new: str, filename: str = "file", language: str = "python") -> None:
        self._console.print(self._diff_viewer.render_unified(old, new, filename, language))

    # ── Theme ──────────────────────────────────────────────────────

    def switch_theme(self, name: str) -> None:
        self._theme.switch(name)
        self._console = Console(theme=self._theme.get_rich_theme(), highlight=False, force_terminal=True)
        self.notify(f"Switched to {name} theme", "success")

    def cycle_theme(self) -> str:
        name = self._theme.next_theme()
        self._console = Console(theme=self._theme.get_rich_theme(), highlight=False, force_terminal=True)
        self.notify(f"Switched to {name} theme", "success")
        return name

    # ── Commands ───────────────────────────────────────────────────

    def show_command_palette(self, filter_text: str = "") -> None:
        self._console.print(self._command_palette.render(filter_text))

    def handle_command(self, command: str) -> bool:
        cmd = command.strip().lower()
        if cmd == "/help":
            self.show_command_palette()
        elif cmd == "/model":
            self.notify(f"Current model: {self._info.model}", "info")
        elif cmd == "/theme":
            self.notify(f"Theme: {self.cycle_theme()}", "success")
        elif cmd == "/tools":
            self.notify(f"{self._info.tools_loaded} tools loaded", "info")
        elif cmd == "/history":
            self.show_history()
        elif cmd == "/config":
            self.notify("Configuration panel coming soon", "warning")
        elif cmd == "/clear":
            self._console.clear()
        elif cmd == "/exit":
            self._console.print(Text("\n  Goodbye!\n", style=f"bold {self._theme.palette.accent}"))
            return True
        else:
            self.notify(f"Unknown command: {cmd}", "warning")
        return False

    # ── History ────────────────────────────────────────────────────

    def add_history(self, renderable: Group) -> None:
        self._history.append(renderable)

    def show_history(self) -> None:
        p = self._theme.palette
        if not self._history:
            self._console.print(Text(f"  {len(self._history)} entries in session history.", style=p.text))
            return
        self._console.print(Text(
            f"  {len(self._history)} entries in session history.",
            style=p.text,
        ))

    # ── Prompt ─────────────────────────────────────────────────────

    def get_user_input(self) -> Optional[str]:
        return self._prompt.get_input(self._console)

    # ── Misc ───────────────────────────────────────────────────────

    def print(self, *args, **kwargs) -> None:
        self._console.print(*args, **kwargs)

    def clear(self) -> None:
        self._console.clear()

    # ==================================================================
    # ADDED: render_event() — the real bridge from graph.stream()'s
    # LangChain messages into the imperative methods above. This is what
    # was actually missing, not the class itself.
    # ==================================================================

    def render_event(self, message, state: dict | None = None) -> None:
        messages = (state or {}).get("messages", [])
        for msg in messages:
            self._render_one(msg, state=state)

    def _render_one(self, message, state: dict | None = None) -> None:
        msg_type = type(message).__name__
        msg_id = getattr(message, "id", None) or str(id(message))
        if msg_id in self._seen_msg_ids:
            return
        self._seen_msg_ids.add(msg_id)

        if msg_type in ("AIMessage", "AIMessageChunk"):
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                line = Text()
                line.append("⟳  ", style=f"bold {self._theme.palette.thinking}")
                line.append("Running tools: ", style=f"bold {self._theme.palette.thinking}")
                line.append(
                    ", ".join(call["name"] for call in tool_calls),
                    style=f"bold {self._theme.palette.accent}",
                )
                self._console.print(line)
                for call in tool_calls:
                    self._pending_calls[call["id"]] = call
                    self.add_timeline_step(f"{call['name']}...", completed=False)

            content = getattr(message, "content", "")
            if content:
                if self._streaming.active:
                    self.end_stream()
                else:
                    self.begin_stream()
                    self.feed_stream(content)
                    self.end_stream()

        elif msg_type == "ToolMessage":
            call_id = getattr(message, "tool_call_id", None)
            call = self._pending_calls.pop(call_id, None)
            content = str(getattr(message, "content", ""))
            success = not content.lower().startswith("error")

            tool_name = call["name"] if call else "unknown_tool"

            if call:
                self._timeline.update_step(f"{call['name']}...", completed=True)

            # edit_file: diff is built straight from the tool call's own
            # args (old_str/new_str) — no state lookup needed.
            if call and call["name"] == "edit_file" and success:
                args = call.get("args", {})
                old_str = args.get("old_str", "")
                new_str = args.get("new_str", "")
                path = args.get("path", "file")
                if old_str or new_str:
                    self.show_diff(old_str, new_str, filename=path)
                    return

            # write_file: diff comes from state["_last_write_diff"],
            # stashed there by tools.py's write_file() since the tool
            # call itself only ever has the NEW content, never the old.
            if call and call["name"] == "write_file" and success and state:
                diff_info = state.get("_last_write_diff")
                if diff_info and diff_info.get("path") == call.get("args", {}).get("path"):
                    self.show_diff(diff_info["old"], diff_info["new"], filename=diff_info["path"])
                    return

            self.show_tool_card(
                tool_name=tool_name,
                description=_describe_call(tool_name),
                detail=utils.truncate(content, 80),
                success=success,
            )

    def shutdown(self, session_id: str, resumable: bool) -> None:
        """Session end — timeline summary + resume hint."""
        if self._timeline._steps:
            self.render_timeline()
        self._console.print(f"\n[dim]session: {session_id}[/dim]")
        if resumable:
            self._console.print(f"[dim]resume with --session {session_id}[/dim]")


def _describe_call(tool_name: str) -> str:
    descriptions = {
        "read_file": "Read file", "write_file": "Write file", "edit_file": "Edit file",
        "grep": "Search files", "list_files": "List directory", "run_shell": "Run shell command",
        "git_diff": "Show git diff", "git_status": "Check git status", "git_commit": "Commit changes",
        "git_branch_create": "Create branch", "manage_tasks": "Update task plan",
        "github_push": "Push to GitHub", "github_create_pr": "Create pull request",
        "github_fetch_repo_info": "Fetch repo info", "github_fetch_issues": "Fetch issues",
    }
    return descriptions.get(tool_name, tool_name)