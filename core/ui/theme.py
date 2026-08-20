"""Theme Manager — central colour palette system for the CRISPR UI.

Provides ThemeManager with palette cycling, and the Palette dataclass
that every UI component reads from (via self._theme.palette).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict

from rich.text import Text
from rich.console import Console
from rich.theme import Theme

# ── Constants ──────────────────────────────────────────────────────

APP_NAME: str = "crispr"
APP_TAGLINE: str = "AI Software Engineer"
APP_VERSION: str = "0.3.1"

BOX_CHARS = {
    "rounded": ("╭", "╮", "╰", "╯", "─", "│"),
    "heavy": ("┏", "┓", "┗", "┛", "━", "┃"),
    "double": ("╔", "╗", "╚", "╝", "═", "║"),
    "simple": ("┌", "┐", "└", "┘", "─", "│"),
}

SPINNER_FRAMES: list[str] = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
SPINNER_DOT_FRAMES: list[str] = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# ── Palette Dataclass ──────────────────────────────────────────────

@dataclass
class Palette:
    """Named colour tokens for every UI component to reference."""
    accent: str
    text: str
    text_dim: str
    muted: str
    border: str
    success: str
    error: str
    warning: str
    info: str
    thinking: str
    streaming: str
    diff_add: str
    diff_remove: str


# ── Built-in Themes ────────────────────────────────────────────────

THEMES: dict[str, Palette] = {
    "orange": Palette(
        accent="bold #FF8C00",
        text="#FFFFFF",
        text_dim="#888888",
        muted="#555555",
        border="#444444",
        success="bold #00CC66",
        error="bold #FF4444",
        warning="bold #FFD700",
        info="bold #00AAFF",
        thinking="bold #FF8C00",
        streaming="bold #FF8C00",
        diff_add="bold #00CC66",
        diff_remove="bold #FF4444",
    ),
    "blue": Palette(
        accent="bold #4488FF",
        text="#FFFFFF",
        text_dim="#888888",
        muted="#555555",
        border="#444444",
        success="bold #00CC66",
        error="bold #FF4444",
        warning="bold #FFD700",
        info="bold #4488FF",
        thinking="bold #4488FF",
        streaming="bold #4488FF",
        diff_add="bold #00CC66",
        diff_remove="bold #FF4444",
    ),
    "green": Palette(
        accent="bold #00CC88",
        text="#FFFFFF",
        text_dim="#888888",
        muted="#555555",
        border="#444444",
        success="bold #00CC66",
        error="bold #FF4444",
        warning="bold #FFD700",
        info="bold #00AAFF",
        thinking="bold #00CC88",
        streaming="bold #00CC88",
        diff_add="bold #00CC66",
        diff_remove="bold #FF4444",
    ),
    "purple": Palette(
        accent="bold #AA66FF",
        text="#FFFFFF",
        text_dim="#888888",
        muted="#555555",
        border="#444444",
        success="bold #00CC66",
        error="bold #FF4444",
        warning="bold #FFD700",
        info="bold #00AAFF",
        thinking="bold #AA66FF",
        streaming="bold #AA66FF",
        diff_add="bold #00CC66",
        diff_remove="bold #FF4444",
    ),
}


# ── Theme Manager ──────────────────────────────────────────────────

class ThemeManager:
    """Manages the active colour palette and provides a Rich Theme.

    Args:
        default: Initial theme name. Must be a key in THEMES.
    """

    _theme_names: list[str] = list(THEMES.keys())

    def __init__(self, default: str = "orange") -> None:
        if default not in THEMES:
            default = "orange"
        self._current = default

    @property
    def palette(self) -> Palette:
        return THEMES[self._current]

    @property
    def name(self) -> str:
        return self._current

    def switch(self, name: str) -> None:
        if name in THEMES:
            self._current = name

    def next_theme(self) -> str:
        idx = self._theme_names.index(self._current)
        self._current = self._theme_names[(idx + 1) % len(self._theme_names)]
        return self._current

    def get_rich_theme(self) -> Theme:
        """Build a Rich Theme from the current palette for Console."""
        p = self.palette
        return Theme({
            "bold": p.accent,
            "dim": p.text_dim,
            "success": p.success,
            "error": p.error,
            "warning": p.warning,
            "info": p.info,
            "thinking": p.thinking,
            "streaming": p.streaming,
        })


# ── System Info Dataclass ──────────────────────────────────────────

@dataclass
class SystemInfo:
    """Holds display info for the banner/dashboard/status bar. All
    fields are passed in explicitly by CRISPRUI.__init__ — this class
    never fetches anything itself (no subprocess calls, no uuid
    generation), so there is exactly one source of truth for each value,
    owned by crispr_core/main.py and SessionState."""

    session_id: str = ""
    started_at: datetime | None = None
    python_version: str = ""
    git_branch: str = ""
    git_status: str = ""
    workspace: str = ""
    model: str = ""
    provider: str = ""
    mcp_servers: int = 0
    tools_loaded: int = 0
    memory_mb: float = 0.0


def build_system_info(
    session_id: str,
    model: str,
    provider: str,
    repo_path: str,
    git_branch: str,
    mcp_servers: int = 0,
    tools_loaded: int = 0,
) -> SystemInfo:
    """Constructs SystemInfo purely from values the caller already has —
    no independent detection logic. Replaces the old gather_system_info()
    which shelled out to git and generated its own session id."""
    return SystemInfo(
        session_id=session_id,
        started_at=datetime.now(),
        python_version=sys.version.split()[0],
        git_branch=git_branch,
        git_status="",
        workspace=repo_path,
        model=model,
        provider=provider,
        mcp_servers=mcp_servers,
        tools_loaded=tools_loaded,
        memory_mb=_get_memory_usage(),
    )


def _get_memory_usage() -> float:
    try:
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


# ── Text Helpers ───────────────────────────────────────────────────

def make_accent(text: str, color: str) -> Text:
    return Text(text, style=f"bold {color}")


def make_muted(text: str, color: str) -> Text:
    return Text(text, style=f"dim {color}")


def truncate(text: str, max_len: int = 40) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def pad_center(text: str, width: int, fill: str = " ") -> str:
    return text.center(width, fill)


def empty_line() -> Text:
    return Text("")


# ── Welcome prompts ────────────────────────────────────────────────

WELCOME_PROMPTS: list[str] = [
    "Explain this repository",
    "Fix failing tests",
    "Generate a README",
    "Optimize performance",
    "Run /help for commands",
]

# ── Command palette ────────────────────────────────────────────────

COMMANDS: Dict[str, str] = {
    "/help": "Show available commands",
    "/model": "Switch AI model",
    "/theme": "Switch colour theme",
    "/tools": "List loaded tools",
    "/history": "View session history",
    "/config": "Open configuration",
    "/clear": "Clear the screen",
    "/exit": "Exit crispr",
}
