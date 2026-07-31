"""Diff viewer – syntax-highlighted side-by-side and unified diffs.

Supports added, removed, and modified lines with colour-coded
rendering inside Rich panels.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, List, Optional

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from . import utils

if TYPE_CHECKING:
    from .theme import ThemeManager


class DiffViewer:
    """Renders syntax-highlighted diffs.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme

    def render_unified(
        self,
        old: str,
        new: str,
        filename: str = "file",
        language: str = "python",
    ) -> Panel:
        """Render a unified diff between two strings.

        Args:
            old: The original content.
            new: The modified content.
            filename: Name to display in the panel title.
            language: Language for syntax highlighting hints.

        Returns:
            A ``rich.panel.Panel`` with the rendered diff.
        """
        p = self._theme.palette
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)

        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))

        text = Text()
        for line in diff:
            line_s = line.rstrip("\n")
            if line_s.startswith("+++") or line_s.startswith("---"):
                text.append(line_s + "\n", style=f"bold {p.text}")
            elif line_s.startswith("@@"):
                text.append(line_s + "\n", style=f"bold {p.info}")
            elif line_s.startswith("+"):
                text.append(line_s + "\n", style=f"{p.diff_add}")
            elif line_s.startswith("-"):
                text.append(line_s + "\n", style=f"{p.diff_remove}")
            else:
                text.append(line_s + "\n", style=f"dim {p.text_dim}")

        title_text = f"📄 {filename}"
        return Panel(
            text,
            title=f"[bold {p.accent}]{title_text}[/]",
            border_style=f"dim {p.border}",
            box=box.ROUNDED,
            padding=(1, 1),
            expand=True,
        )

    def render_file_diff(
        self,
        old_path: str,
        new_path: str,
        language: str = "python",
    ) -> Panel:
        """Render a diff between two files on disk.

        Args:
            old_path: Path to the original file.
            new_path: Path to the modified file.
            language: Language for syntax highlighting.

        Returns:
            A ``rich.panel.Panel`` with the file diff.
        """
        try:
            with open(old_path, "r", encoding="utf-8", errors="replace") as f:
                old = f.read()
        except FileNotFoundError:
            old = ""
        try:
            with open(new_path, "r", encoding="utf-8", errors="replace") as f:
                new = f.read()
        except FileNotFoundError:
            new = ""

        import os

        name = os.path.basename(new_path or old_path)
        return self.render_unified(old, new, filename=name, language=language)

    def render_hunks(
        self,
        hunks: list[dict],
        filename: str = "changes",
    ) -> Panel:
        """Render pre-parsed diff hunks.

        Each hunk dict should contain:
            - ``old_start``: int
            - ``old_lines``: list[str]
            - ``new_start``: int
            - ``new_lines``: list[str]

        Args:
            hunks: List of hunk dictionaries.
            filename: Display name for the panel title.
        """
        p = self._theme.palette
        text = Text()

        for hunk in hunks:
            text.append(
                f"@@ -{hunk['old_start']} +{hunk['new_start']} @@\n",
                style=f"bold {p.info}",
            )
            for line in hunk.get("old_lines", []):
                text.append(f"-{line}\n", style=f"{p.diff_remove}")
            for line in hunk.get("new_lines", []):
                text.append(f"+{line}\n", style=f"{p.diff_add}")

        return Panel(
            text,
            title=f"[bold {p.accent}]📄 {filename}[/]",
            border_style=f"dim {p.border}",
            box=box.ROUNDED,
            padding=(1, 1),
            expand=True,
        )