"""Thinking indicator – plain-text status line.

Shown while the agent is preparing/executing. Deliberately boxless:
a single bold status line instead of a framed panel.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.text import Text

from .animations import spinner_iterator

if TYPE_CHECKING:
    from .theme import ThemeManager


class ThinkingPanel:
    """Plain-text thinking status.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme
        self._start_time: float = 0.0
        self._prompt_tokens: int = 0
        self._output_tokens: int = 0
        self._current_tool: str = ""
        self._phase: str = "Initializing"
        self._active: bool = False
        self._spinner = spinner_iterator()

    @property
    def is_active(self) -> bool:
        """Whether the thinking indicator is currently displayed."""
        return self._active

    def start(self, phase: str = "Thinking") -> None:
        """Begin the thinking status."""
        self._start_time = time.monotonic()
        self._active = True
        self._phase = phase

    def stop(self) -> None:
        """Stop the thinking status."""
        self._active = False

    def update_tokens(self, prompt_tokens: int, output_tokens: int) -> None:
        """Update the live token counters."""
        self._prompt_tokens = prompt_tokens
        self._output_tokens = output_tokens

    def set_tool(self, tool: str) -> None:
        """Update the currently active tool name."""
        self._current_tool = tool

    def set_phase(self, phase: str) -> None:
        """Update the execution phase label."""
        self._phase = phase

    def render(self) -> Text:
        """Render the thinking status as a plain text line."""
        p = self._theme.palette
        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0

        line = Text()
        if self._active:
            spinner_char = next(self._spinner)
            line.append(f"{spinner_char}  {self._phase}", style=f"bold {p.thinking}")
            line.append(f"  ({elapsed:.1f}s)", style=f"dim {p.text_dim}")
            if self._current_tool:
                line.append(f"  → {self._current_tool}", style=p.text)
            if self._prompt_tokens or self._output_tokens:
                line.append(
                    f"  ({self._prompt_tokens:,}/{self._output_tokens:,} tok)",
                    style=f"dim {p.text_dim}",
                )
        else:
            line.append("✓  Done", style=f"bold {p.success}")
        return line
