"""Banner component – large CRISPR logo with startup animation.

Renders the ASCII logo line-by-line with a reveal effect,
then displays an animated mascot robot on the right side.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import utils
from .animations import line_by_line, _silent_sleep

if TYPE_CHECKING:
    from .theme import ThemeManager

# ── ASCII Logo ─────────────────────────────────────────────────────

LOGO_LINES: list[str] = [
    " ██████╗ ██████╗ ██╗███████╗██████╗ ██████╗",
    "██╔════╝██╔══██╗██║██╔════╝██╔══██╗██╔══██╗",
    "██║     ██████╔╝██║███████╗██████╔╝██████╔╝",
    "██║     ██╔══██╗██║╚════██║██╔═══╝ ██╔══██╗",
    "╚██████╗██║  ██║██║███████║██║     ██║  ██║",
    " ╚═════╝╚═╝  ╚═╝╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝",
    "",
    "                            ██████████████      ██████████████",
    "                            ██░░░░░░░░░░██══════██░░░░░░░░░░██",
    "                            ██  ◉     ◉ ██══════██  ████    ██",
    "                            ██    ▄▄    ██══════██  ████    ██",
    "                            ██████████████══════██████████████",
]

MASCOT: list[str] = [
    "    ┌──────┐    ",
    "   ╱ ◉  ◉ ╲   ",
    "  │  ────  │   ",
    "  │  ╰──╯  │   ",
    "   ╲──────╱    ",
    "    ││  ││     ",
    "   ═╧╧══╧╧═    ",
]

MASCOT_BLINK: list[str] = [
    "    ┌──────┐    ",
    "   ╱ ─  ─ ╲   ",
    "  │  ────  │   ",
    "  │  ╰──╯  │   ",
    "   ╲──────╱    ",
    "    ││  ││     ",
    "   ═╧╧══╧╧═    ",
]


class Banner:
    """Renders the CRISPR logo banner and system info panel.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme
        self._blink_state = True

    def render_startup(self) -> None:
        """Animate the logo appearing line-by-line."""
        palette = self._theme.palette
        for frame in line_by_line(LOGO_LINES, rate=0.04):
            print(f"\033[H\033[J", end="", flush=True)
            t = Text(frame, style=f"bold {palette.accent}")
            Console(force_terminal=True).print(t)
            _silent_sleep(0.01)
        _silent_sleep(0.3)

    def render(self, info: utils.SystemInfo, show_info: bool = True) -> Group:
        """Build the banner + info panel as a Rich Group renderable.

        Args:
            info: Detected system information.
            show_info: Whether to render the info panel below the logo.

        Returns:
            A ``rich.console.Group`` containing the logo and optional info panel.
        """
        palette = self._theme.palette
        parts: list[Text | Panel] = []

        logo = Text()
        for line in LOGO_LINES:
            logo.append(line + "\n", style=f"bold {palette.accent}")
        parts.append(logo)

        tagline = Text(f"  {utils.APP_TAGLINE}", style=f"dim {palette.text_dim}")
        version = Text(f"  v{utils.APP_VERSION}", style=f"dim {palette.muted}")
        tagline.append_text(version)
        parts.append(tagline)

        if show_info:
            info_panel = self._build_info_panel(info)
            parts.append(info_panel)

        return Group(*parts)

    def _build_info_panel(self, info: utils.SystemInfo) -> Panel:
        """Build the rounded system info panel."""
        palette = self._theme.palette
        grid = Table(
            show_header=False,
            box=None,
            padding=(0, 2),
            expand=True,
        )
        grid.add_column(min_width=18)
        grid.add_column()
        grid.add_column(min_width=18)
        grid.add_column()

        rows = [
            ("  ⚙  Model", info.model, "  ☁  Provider", info.provider),
            ("  📁 Workspace", utils.truncate(info.workspace, 30), "  🐍 Python", info.python_version),
        ]
        if info.git_branch:
            rows.append(
                (
                    "  🌿 Branch",
                    info.git_branch,
                    "  📊 Git",
                    info.git_status or "clean",
                )
            )
        rows.append(
            (
                "  🔌 MCP Servers",
                str(info.mcp_servers),
                "  🛠  Tools",
                str(info.tools_loaded),
            )
        )
        rows.append(
            ("  \U0001f194 Session", info.session_id, "  \u23f1  Started", info.started_at.strftime("%H:%M:%S") if info.started_at else "N/A")
        )

        for label1, val1, label2, val2 in rows:
            grid.add_row(
                Text(label1, style=f"dim {palette.text_dim}"),
                Text(val1, style=f"{palette.text}"),
                Text(label2, style=f"dim {palette.text_dim}"),
                Text(val2, style=f"{palette.text}"),
            )

        return Panel(
            grid,
            title=f"[bold {palette.accent}]System Info[/]",
            border_style=f"dim {palette.muted}",
            box=box.ROUNDED,
            padding=(1, 1),
            expand=True,
        )

    def toggle_blink(self) -> list[str]:
        """Toggle the mascot blink state and return the current frame."""
        self._blink_state = not self._blink_state
        return MASCOT if self._blink_state else MASCOT_BLINK

    @staticmethod
    def mascot_text(blink: bool = True) -> Text:
        """Return the mascot as a styled Text object.

        Args:
            blink: If True, use the open-eyes frame.
        """
        lines = MASCOT if blink else MASCOT_BLINK
        t = Text()
        for line in lines:
            t.append(line + "\n", style="dim")
        return t