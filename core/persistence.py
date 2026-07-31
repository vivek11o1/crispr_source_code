# crispr_core/persistence.py
"""
Persistence — SqliteSaver checkpointer (official session state) and an
independent JSONL transcript logger (debug trail that survives even if
the SQLite DB gets corrupted). Both are local, per-user, no server.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from platformdirs import user_data_dir

DATA_DIR = Path(user_data_dir("crispr", appauthor=False))
SESSIONS_DB = DATA_DIR / "sessions.db"
LOGS_DIR = DATA_DIR / "logs"


def get_checkpointer() -> SqliteSaver:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SESSIONS_DB), check_same_thread=False)
    return SqliteSaver(conn)


def get_transcript_path(thread_id: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"{thread_id}.jsonl"


def log_transcript_event(thread_id: str, event_type: str, data: dict) -> None:
    """Append-only, best-effort. Never raises — a logging failure should
    never interrupt the actual agent loop."""
    try:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "data": data,
        }
        path = get_transcript_path(thread_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # logging is best-effort, never fatal