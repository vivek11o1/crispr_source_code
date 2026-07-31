"""Prompt widget – custom input prompt with multiline support.

Provides a styled prompt using Rich's Prompt class with
custom styling and command detection.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from rich.console import Console
from rich.prompt import Prompt as RichPrompt
from rich.text import Text

from . import utils

if TYPE_CHECKING:
    from .theme import ThemeManager


class PromptWidget:
    """Custom styled prompt for user input.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme
        self._history: list[str] = []
        self._history_index: int = -1

    def render_prefix(self) -> Text:
        """Render the prompt prefix symbol."""
        p = self._theme.palette
        return Text(" ❯ ", style=f"bold {p.accent}")

    def get_input(self, console: Console) -> Optional[str]:
        """Display the prompt and read user input.

        Args:
            console: The Rich Console to render into.

        Returns:
            The user's input string, or ``None`` on EOF/empty.
        """
        p = self._theme.palette
        prefix = Text()
        prefix.append(" ❯ ", style=f"bold {p.accent}")

        try:
            user_input = RichPrompt.ask(prefix, console=console, default="")
        except (EOFError, KeyboardInterrupt):
            return None

        if user_input and user_input.strip():
            self._history.append(user_input.strip())

        return user_input

    def read_multiline(self, console: Console, end_marker: str = "") -> Optional[str]:
        """Read multiline input until the user submits.

        Supports pasted code blocks. Input ends on double-newline
        or when the end_marker is encountered.

        Args:
            console: The Rich Console.
            end_marker: Optional string that signals end of input.

        Returns:
            The collected multiline input, or ``None`` on EOF.
        """
        lines: list[str] = []
        p = self._theme.palette

        console.print(
            Text(" ❯ ", style=f"bold {p.accent}"),
            end="",
        )

        try:
            while True:
                line = input()
                if end_marker and line.strip() == end_marker:
                    break
                if not line and lines and not lines[-1]:
                    break
                lines.append(line)
        except EOFError:
            return None
        except KeyboardInterrupt:
            console.print()
            return None

        result = "\n".join(lines).strip()
        if result:
            self._history.append(result)
        return result or None

    @property
    def history(self) -> list[str]:
        """Return the input history list."""
        return self._history.copy()

    @property
    def is_command(self) -> bool:
        """Check if the last input was a slash command."""
        if not self._history:
            return False
        return self._history[-1].startswith("/")

    def get_last_command(self) -> str | None:
        """Return the last slash command, or None."""
        if self._history and self._history[-1].startswith("/"):
            return self._history[-1]
        return None


class CommandPalette:
    """Renders the command palette when '/' is typed.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme

    def render(self, filter_text: str = "") -> Text:
        """Render the list of available commands, optionally filtered.

        Args:
            filter_text: Text after '/' to filter commands.

        Returns:
            A ``rich.text.Text`` with the command list.
        """
        p = self._theme.palette
        text = Text()
        text.append("\n  Commands\n", style=f"bold {p.accent}")
        text.append("  " + "─" * 36 + "\n", style=f"dim {p.muted}")

        for cmd, desc in utils.COMMANDS.items():
            if filter_text and filter_text.lower() not in cmd.lower():
                continue
            text.append(f"  {cmd:<14}", style=f"bold {p.accent}")
            text.append(f"  {desc}\n", style=f"dim {p.text_dim}")

        text.append("\n", style=p.text)
        return text