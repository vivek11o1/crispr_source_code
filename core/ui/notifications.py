"""Notifications – top-right temporary toast messages.

Manages a queue of auto-dismissing notifications displayed in the
top-right area of the terminal.
"""

from __future__ import annotations

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Deque, List, Optional

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.text import Text

from . import utils

if TYPE_CHECKING:
    from .theme import ThemeManager


@dataclass
class Notification:
    """A single notification entry.

    Attributes:
        message: Notification text.
        kind: One of ``"info"``, ``"success"``, ``"warning"``.
        timestamp: When the notification was created.
        ttl: Time-to-live in seconds before auto-dismiss.
    """

    message: str
    kind: str = "info"
    timestamp: float = field(default_factory=time.monotonic)
    ttl: float = 4.0

    @property
    def expired(self) -> bool:
        """Return True if the notification has exceeded its TTL."""
        return (time.monotonic() - self.timestamp) > self.ttl


class NotificationManager:
    """Manages auto-dismissing notifications.

    Args:
        theme: The active ThemeManager instance.
        max_visible: Maximum number of notifications visible at once.
        default_ttl: Default time-to-live in seconds.
    """

    def __init__(
        self,
        theme: ThemeManager,
        max_visible: int = 3,
        default_ttl: float = 4.0,
    ) -> None:
        self._theme = theme
        self._max_visible = max_visible
        self._default_ttl = default_ttl
        self._notifications: Deque[Notification] = deque()

    def push(self, message: str, kind: str = "info", ttl: float | None = None) -> None:
        """Add a new notification to the queue.

        Args:
            message: Notification text.
            kind: ``"info"``, ``"success"``, or ``"warning"``.
            ttl: Override the default time-to-live.
        """
        notif = Notification(
            message=message,
            kind=kind,
            ttl=ttl if ttl is not None else self._default_ttl,
        )
        self._notifications.append(notif)

    def info(self, message: str) -> None:
        """Shorthand to push an info notification."""
        self.push(message, kind="info")

    def success(self, message: str) -> None:
        """Shorthand to push a success notification."""
        self.push(message, kind="success")

    def warning(self, message: str) -> None:
        """Shorthand to push a warning notification."""
        self.push(message, kind="warning")

    def _prune(self) -> None:
        """Remove expired notifications."""
        while self._notifications and self._notifications[0].expired:
            self._notifications.popleft()

    def render(self) -> Group | None:
        """Render the active notifications.

        Returns:
            A ``rich.console.Group`` of notification panels, or ``None``
            if no notifications are active.
        """
        self._prune()
        if not self._notifications:
            return None

        p = self._theme.palette
        kind_styles = {
            "info": p.info,
            "success": p.success,
            "warning": p.warning,
        }
        kind_icons = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
        }

        panels = []
        visible = list(self._notifications)[-self._max_visible :]

        for notif in visible:
            color = kind_styles.get(notif.kind, p.text)
            icon = kind_icons.get(notif.kind, "•")
            remaining = max(0, notif.ttl - (time.monotonic() - notif.timestamp))

            content = Text()
            content.append(f" {icon} ", style=f"bold {color}")
            content.append(notif.message, style=p.text)
            content.append(f"  ({remaining:.0f}s)", style=f"dim {p.muted}")

            panels.append(
                Panel(
                    content,
                    border_style=f"dim {color}",
                    box=box.ROUNDED,
                    padding=(0, 0),
                    expand=False,
                )
            )

        if len(panels) == 1:
            return panels[0]
        return Group(*panels)

    def render_latest(self) -> Panel | None:
        """Render only the most recent notification.

        Returns:
            A ``rich.panel.Panel`` for the latest notification, or ``None``.
        """
        self._prune()
        if not self._notifications:
            return None

        p = self._theme.palette
        kind_styles = {
            "info": p.info,
            "success": p.success,
            "warning": p.warning,
        }
        kind_icons = {
            "info": "ℹ",
            "success": "✓",
            "warning": "⚠",
        }

        notif = self._notifications[-1]
        color = kind_styles.get(notif.kind, p.text)
        icon = kind_icons.get(notif.kind, "•")
        remaining = max(0, notif.ttl - (time.monotonic() - notif.timestamp))

        content = Text()
        content.append(f" {icon} ", style=f"bold {color}")
        content.append(notif.message, style=p.text)
        content.append(f"  ({remaining:.0f}s)", style=f"dim {p.muted}")

        return Panel(
            content,
            border_style=f"dim {color}",
            box=box.ROUNDED,
            padding=(0, 0),
            expand=False,
        )

    def clear(self) -> None:
        """Remove all notifications."""
        self._notifications.clear()