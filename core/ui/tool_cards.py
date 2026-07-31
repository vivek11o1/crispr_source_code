"""Tool invocation output and execution timeline.

Renders individual tool invocations as plain text lines (no boxes),
plus a plain-text list of execution steps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text

from . import utils

if TYPE_CHECKING:
    from .theme import ThemeManager


class ToolCard:
    """A single tool invocation, rendered as plain text.

    Args:
        tool_name: Name of the tool invoked.
        description: Brief description of what it did.
        detail: Extra detail (e.g. file path, line count).
        duration: How long the tool took (seconds).
        success: Whether the invocation succeeded.
        theme: The active ThemeManager instance.
    """

    def __init__(
        self,
        tool_name: str,
        description: str,
        detail: str = "",
        duration: float = 0.0,
        success: bool = True,
        theme: "ThemeManager | None" = None,
    ) -> None:
        self.tool_name = tool_name
        self.description = description
        self.detail = detail
        self.duration = duration
        self.success = success
        self._theme = theme

    def render(self) -> Text:
        """Render the tool invocation as a plain text line."""
        p = self._theme.palette if self._theme else utils.THEMES["orange"]
        status_color = p.success if self.success else p.error
        status_icon = "✓" if self.success else "✗"

        line = Text()
        line.append(f"🔧 {self.tool_name}", style=f"bold {p.accent}")
        line.append(f"  {self.description}", style=p.text)
        line.append(f"  {status_icon}", style=f"bold {status_color}")
        line.append(f"  ({self.duration:.2f}s)", style=f"dim {p.text_dim}")
        if self.detail:
            for detail_line in self.detail.splitlines():
                line.append("\n  ", style=p.text)
                line.append(detail_line, style=f"dim {p.text_dim}")
        return line


class ToolTimeline:
    """Execution timeline showing step-by-step progress.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme
        self._steps: list[tuple[str, bool, float]] = []

    def add_step(self, label: str, completed: bool = False, duration: float = 0.0) -> None:
        """Add a step to the timeline.

        Args:
            label: Description of the step.
            completed: Whether the step has finished.
            duration: Time taken in seconds.
        """
        self._steps.append((label, completed, duration))

    def update_step(self, label: str, completed: bool = True, duration: float = 0.0) -> None:
        for i, (lbl, _, old_dur) in enumerate(self._steps):
            if lbl == label:
                self._steps[i] = (label, completed, duration or old_dur)
                return

    def clear(self) -> None:
        """Remove all steps from the timeline."""
        self._steps.clear()

    def render(self) -> Text:
        """Render the timeline as plain text lines."""
        p = self._theme.palette
        lines = Text()
        lines.append("Execution Timeline", style=f"bold {p.accent}")
        for label, completed, duration in self._steps:
            if completed:
                icon = Text("  ✓ ", style=f"bold {p.success}")
                lbl = Text(label, style=p.text)
            else:
                icon = Text("  … ", style=f"bold {p.thinking}")
                lbl = Text(label, style=f"dim {p.text_dim}")
            lines.append("\n", style=p.text)
            lines.append_text(icon)
            lines.append_text(lbl)
            if duration > 0:
                lines.append_text(Text(f"  {duration:.1f}s", style=f"dim {p.text_dim}"))
        return lines
