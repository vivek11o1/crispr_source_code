"""Footer status bar – persistent bottom bar with runtime info.

Displays current mode, git branch, model, MCP status, memory, and
keyboard shortcut hints.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import utils

if TYPE_CHECKING:
    from .theme import ThemeManager


class StatusBar:
    """Persistent footer status bar.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme
        self._mode: str = "chat"

    def set_mode(self, mode: str) -> None:
        """Update the current operating mode."""
        self._mode = mode

    def render(self, info: utils.SystemInfo) -> Panel:
        """Render the status bar as a Panel.

        Args:
            info: System information for populating bar fields.

        Returns:
            A full-width ``rich.panel.Panel`` suitable for the bottom of the screen.
        """
        p = self._theme.palette
        table = Table(show_header=False, box=None, expand=True, padding=(0, 1))
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)
        table.add_column(ratio=1)

        mode_text = Text(f" ◉ {self._mode.upper()} ", style=f"bold white on {p.accent}")
        branch_text = Text(f" 🌿 {info.git_branch or 'N/A'} ", style=f"dim {p.text_dim}")
        model_text = Text(f" ⚙ {info.model} ", style=f"{p.text}")
        mcp_text = Text(f" 🔌 MCP: {info.mcp_servers} ", style=f"{p.info}")
        mem_text = Text(f" 📊 {info.memory_mb:.1f} MB ", style=f"dim {p.muted}")
        hints = Text(" Ctrl+C  interrupt · /help  commands ", style=f"dim {p.muted}")

        table.add_row(mode_text, branch_text, model_text, mcp_text, mem_text, hints)

        return Panel(
            table,
            border_style=f"dim {p.border}",
            box=box.HORIZONTALS,
            expand=True,
        )