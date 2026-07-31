"""Dashboard component – icon-labelled information cards.

Displays system information in a grid of styled cards with icons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text

from . import utils

if TYPE_CHECKING:
    from .theme import ThemeManager


class DashboardCard:
    """A single dashboard info card.

    Args:
        icon: Emoji or unicode icon prefix.
        label: Card title.
        value: Card value text.
        accent: Accent colour hex for the label.
        dim: Dim colour hex for muted text.
    """

    def __init__(self, icon: str, label: str, value: str, accent: str, dim: str) -> None:
        self.icon = icon
        self.label = label
        self.value = value
        self.accent = accent
        self.dim = dim

    def render(self) -> Panel:
        """Render the card as a Rich Panel."""
        title = Text(f"{self.icon} {self.label}", style=f"bold {self.accent}")
        body = Text(self.value, style=self.accent)
        return Panel(
            body,
            title=title,
            border_style=f"dim {self.dim}",
            box=box.ROUNDED,
            padding=(0, 1),
            expand=True,
        )


class Dashboard:
    """Renders a grid of dashboard info cards.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme

    def render(self, info: utils.SystemInfo) -> Columns:
        """Build all dashboard cards and return as a Columns layout.

        Args:
            info: System information to populate the cards.

        Returns:
            A ``rich.columns.Columns`` with all cards.
        """
        p = self._theme.palette
        cards = [
            DashboardCard("⚙", "Model", info.model, p.accent, p.muted),
            DashboardCard("☁", "Provider", info.provider, p.info, p.muted),
            DashboardCard("📁", "Workspace", utils.truncate(info.workspace, 35), p.text, p.muted),
            DashboardCard("🌿", "Git", info.git_branch or "N/A", p.success, p.muted).render(),
            DashboardCard("🐍", "Python", info.python_version, p.warning, p.muted),
            DashboardCard("🔌", "MCP Servers", str(info.mcp_servers), p.info, p.muted),
            DashboardCard("🛠", "Tools", str(info.tools_loaded), p.accent, p.muted),
        ]

        rendered = []
        for card in cards:
            if isinstance(card, Panel):
                rendered.append(card)
            else:
                rendered.append(card.render())

        return Columns(rendered, equal=True, expand=True, padding=(0, 1))