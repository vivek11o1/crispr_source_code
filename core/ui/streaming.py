"""Streaming renderer – token-by-token output.

Provides a StreamingRenderer that accumulates tokens as they arrive and
renders them as plain text under a heading naming the generating
process. No box/panel chrome — text is written straight to the console.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rich.text import Text

if TYPE_CHECKING:
    from .theme import ThemeManager


class StreamingRenderer:
    """Accumulates tokens and renders them as plain streamed text.

    Args:
        theme: The active ThemeManager instance.
    """

    def __init__(self, theme: ThemeManager) -> None:
        self._theme = theme
        self._buffer: str = ""
        self._start_time: float = 0.0
        self._token_count: int = 0
        self._process_name: str = "Response"
        self._active: bool = False

    @property
    def text(self) -> str:
        """Return the full accumulated text."""
        return self._buffer

    @property
    def token_count(self) -> int:
        """Return the number of tokens received."""
        return self._token_count

    @property
    def active(self) -> bool:
        """Whether a stream is currently in progress."""
        return self._active

    def begin(self, process_name: str = "Response") -> None:
        """Reset the renderer for a new streaming response.

        Args:
            process_name: Heading shown above the streamed text.
        """
        self._buffer = ""
        self._start_time = time.monotonic()
        self._token_count = 0
        self._process_name = process_name
        self._active = True

    def end(self) -> None:
        """Mark the current stream as finished."""
        self._active = False

    def feed(self, token: str) -> None:
        """Add a single token to the streaming buffer.

        Args:
            token: The token string to append.
        """
        self._buffer += token
        self._token_count += 1

    def render_heading(self) -> Text:
        """Heading naming the process currently streaming."""
        p = self._theme.palette
        heading = Text()
        heading.append("▶ ", style=f"bold {p.streaming}")
        heading.append(self._process_name, style=f"bold {p.streaming}")
        return heading

    def render(self) -> Text:
        """Return the accumulated text as a plain ``Text`` renderable."""
        p = self._theme.palette
        return Text(self._buffer, style=p.text)

    def render_meta(self, complete: bool = False) -> Text:
        """Metadata line: elapsed time, token count, completion state."""
        p = self._theme.palette
        elapsed = time.monotonic() - self._start_time if self._start_time else 0.0
        meta = Text()
        meta.append(f"  ⏱ {elapsed:.1f}s", style=f"dim {p.text_dim}")
        meta.append("  │  ", style=f"dim {p.muted}")
        meta.append(f"  📝 {self._token_count} tokens", style=f"dim {p.text_dim}")
        if complete:
            meta.append("  │  ", style=f"dim {p.muted}")
            meta.append("✓ Complete", style=f"bold {p.success}")
        return meta
