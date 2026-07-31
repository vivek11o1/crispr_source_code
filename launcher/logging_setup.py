"""
Launcher-level crash/error logging — separate from crispr-core's
per-session transcript log. Catches failures that happen BEFORE the core
runtime is even reached (bad config, network failure fetching manifest,
etc.)
"""


import logging
import sys
from pathlib import Path
from platformdirs import user_config_dir


LOG_DIR = Path(user_config_dir("crispr", appauthor=False))
LOG_FILE = LOG_DIR/"launcher.log"

# logging_setup.py
def setup_logging() -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        sys.excepthook = _log_uncaught_exception
    except (PermissionError, OSError) as e:
        # Logging is best-effort — never let it block the app from running.
        print(f"[warning] Could not set up file logging ({e}). Continuing without it.")
        logging.basicConfig(level=logging.INFO)  # falls back to console-only
    
    
def _log_uncaught_exception(exc_type, exc_value, exc_traceback):
        logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        print(f"crispr hit an unexpected error. Details logged to {LOG_FILE}")
        print("Run 'crispr doctor', or check the log file above, for more information.")    