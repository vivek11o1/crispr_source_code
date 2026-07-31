"""crispr — terminal UI subpackage, lives inside crispr_core.

Rich-based rendering for the live agent loop: banner, dashboard, thinking
panel, streaming markdown, tool cards, diffs, notifications. Driven by
CRISPRUI.render_event(), called from crispr_core/main.py's graph.stream()
loop — not the launcher, which stays plain Rich tables for its own
doctor/config/health commands.
"""

from .ui import CRISPRUI

__all__ = ["CRISPRUI"]