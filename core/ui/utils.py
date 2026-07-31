"""Utility helpers — re-exports from theme.py for backwards compatibility.

All constants, SystemInfo, build_system_info, truncate, THEMES, etc.
are defined in theme.py. This module re-exports them so existing
`from . import utils` / `utils.truncate(...)` code keeps working.
"""

from .theme import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    BOX_CHARS,
    SPINNER_FRAMES,
    SPINNER_DOT_FRAMES,
    Palette,
    THEMES,
    ThemeManager,
    SystemInfo,
    build_system_info,
    _get_memory_usage,
    make_accent,
    make_muted,
    truncate,
    pad_center,
    empty_line,
    WELCOME_PROMPTS,
    COMMANDS,
)

__all__ = [
    "APP_NAME", "APP_TAGLINE", "APP_VERSION",
    "BOX_CHARS", "SPINNER_FRAMES", "SPINNER_DOT_FRAMES",
    "Palette", "THEMES", "ThemeManager",
    "SystemInfo", "build_system_info",
    "make_accent", "make_muted", "truncate", "pad_center", "empty_line",
    "WELCOME_PROMPTS", "COMMANDS",
]
