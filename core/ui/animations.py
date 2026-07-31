"""Animation primitives for the CRISPR terminal UI.

Provides frame-based animation helpers: blink, spinner, fade, and
line-by-line reveal – all designed for smooth Rich Live rendering.
"""

from __future__ import annotations

import itertools
import time
from typing import Iterator, List


def blink_iterator(
    interval: float = 1.5,
    on_char: str = "●",
    off_char: str = "○",
) -> Iterator[str]:
    """Infinite iterator that toggles between on/off characters.

    Args:
        interval: Seconds between state changes.
        on_char: Character for the "on" state.
        off_char: Character for the "off" state.
    """
    while True:
        yield on_char
        _silent_sleep(interval)
        yield off_char
        _silent_sleep(interval)


def spinner_iterator(frames: list[str] | None = None, rate: float = 0.08) -> Iterator[str]:
    """Infinite iterator cycling through spinner frames.

    Args:
        frames: List of single-character frames. Defaults to braille dots.
        rate: Seconds between frame advances.
    """
    if frames is None:
        frames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    for frame in itertools.cycle(frames):
        yield frame
        _silent_sleep(rate)


def dot_pulse(count: int = 3, rate: float = 0.4) -> Iterator[str]:
    """Yields growing dot strings: '.', '..', '...', then resets."""
    while True:
        for i in range(1, count + 1):
            yield "." * i
            _silent_sleep(rate)


def fade_lines(lines: List[str], char: str = "█", rate: float = 0.015) -> Iterator[str]:
    """Yield characters progressively revealing a block of text.

    Simulates a "fade-in" by printing characters left-to-right, top-to-bottom.

    Args:
        lines: The lines of text to reveal.
        char: Overlay character used during the reveal sweep.
        rate: Seconds between each character reveal.
    """
    grid = [list(line) for line in lines]
    height = len(grid)
    if height == 0:
        return
    width = max(len(row) for row in grid)

    # Build a progressive mask
    for step in range(width):
        result_lines: list[str] = []
        for row in grid:
            parts: list[str] = []
            for ci, ch in enumerate(row):
                if ci <= step:
                    parts.append(ch)
                else:
                    parts.append(char)
            result_lines.append("".join(parts))
        yield "\n".join(result_lines)
        _silent_sleep(rate)


def typewriter(text: str, rate: float = 0.01) -> Iterator[str]:
    """Yield one character at a time to simulate a typewriter effect.

    Args:
        text: Full text to type out.
        rate: Seconds between each character.
    """
    buffer = ""
    for ch in text:
        buffer += ch
        yield buffer
        _silent_sleep(rate)


def line_by_line(lines: List[str], rate: float = 0.04) -> Iterator[str]:
    """Yield progressively more lines from a list.

    Args:
        lines: Complete list of lines.
        rate: Seconds between each new line.
    """
    for i in range(1, len(lines) + 1):
        yield "\n".join(lines[:i])
        _silent_sleep(rate)


def progress_wave(width: int = 30, rate: float = 0.05) -> Iterator[str]:
    """Animated wave progress bar placeholder.

    Args:
        width: Total bar width in characters.
        rate: Seconds between frames.
    """
    pos = 0
    while True:
        chars = []
        for i in range(width):
            dist = abs(i - pos)
            if dist == 0:
                chars.append("█")
            elif dist <= 2:
                chars.append("▓")
            elif dist <= 4:
                chars.append("▒")
            else:
                chars.append("░")
        pos = (pos + 1) % width
        yield "".join(chars)
        _silent_sleep(rate)


def _silent_sleep(duration: float) -> None:
    """Sleep without raising on interrupts.

    Args:
        duration: Time in seconds to sleep.
    """
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        pass