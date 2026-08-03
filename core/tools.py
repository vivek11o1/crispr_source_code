# crispr_core/tools.py
"""
Core file/shell tools — read_file, write_file, edit_file, list_files,
grep, run_shell. Every function follows the (str, dict) convention:
str goes to the model as the ToolMessage, dict merges into SessionState.
Every function catches its own exceptions — never raises, always returns
an error string the model can see and react to.
"""

import glob
import subprocess
from pathlib import Path
from typing import Annotated
from langgraph.prebuilt import InjectedState
from states import SessionState


def read_file(path: str) -> str:
    """AUTO-tier. Read a file's full contents."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content if content else "(file is empty)"
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except OSError as e:
        return f"Error reading {path}: {e}"


def write_file(
    path: str,
    content: str,
    state: Annotated[SessionState, InjectedState] = None,
) -> tuple[str, dict]:
    """PROMPT-tier. Create or overwrite a file. Tracks edited_files.
    Reads the file's PREVIOUS content before overwriting it, so
    render_event() (in ui.py) can build a real before/after diff instead
    of showing a plain tool card — write_file's tool call args only ever
    contain the NEW content, so this is the only place the old version
    can still be captured, before it's gone."""

    old_content = ""
    try:
        if Path(path).exists():
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                old_content = f.read()
    except OSError:
        old_content = ""  # unreadable old file — diff will just show as a full add

    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return f"Error writing {path}: {e}", {}

    edited = list(state.get("edited_files", []))
    if path not in edited:
        edited.append(path)

    return f"Wrote {len(content)} chars to {path}", {
        "edited_files": edited,
        # Stashed here, not returned as part of the ToolMessage content —
        # ui.py's render_event() reads this off the NEXT state snapshot,
        # since ToolMessage itself only ever carries the string result.
        "_last_write_diff": {"path": path, "old": old_content, "new": content},
    }


def edit_file(
    path: str,
    old_str: str,
    new_str: str,
    state: Annotated[SessionState, InjectedState] = None,
) -> tuple[str, dict]:
    """PROMPT-tier. Targeted find-and-replace edit. old_str must match
    exactly once — safer than a full overwrite for existing files."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"Error: file not found: {path}", {}
    except OSError as e:
        return f"Error reading {path}: {e}", {}

    count = content.count(old_str)
    if count == 0:
        return f"Error: old_str not found in {path}. No changes made.", {}
    if count > 1:
        return (
            f"Error: old_str matches {count} times in {path} — must match exactly "
            "once. Add more surrounding context to old_str.",
            {},
        )

    new_content = content.replace(old_str, new_str, 1)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
    except OSError as e:
        return f"Error writing {path}: {e}", {}

    edited = list(state.get("edited_files", []))
    if path not in edited:
        edited.append(path)

    return f"Edited {path}", {"edited_files": edited}


def list_files(path: str = ".", pattern: str = "*") -> str:
    """AUTO-tier. List files matching a glob pattern under path."""
    try:
        base = Path(path)
        if not base.exists():
            return f"Error: path not found: {path}"
        matches = sorted(str(p) for p in base.rglob(pattern) if p.is_file())
        if not matches:
            return f"No files matching '{pattern}' under {path}"
        return "\n".join(matches[:50])  # cap output to avoid flooding context
    except OSError as e:
        return f"Error listing {path}: {e}"


def grep(pattern: str, path: str = ".") -> str:
    """AUTO-tier. Search file contents for pattern, using ripgrep if
    available, falling back to Python if not."""
    try:
        result = subprocess.run(
            ["rg", "--line-number", pattern, path],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        if result.returncode in (0, 1):  # 1 = no matches, still a valid run
            return result.stdout.strip() or "No matches found."
        return f"rg error: {result.stderr.strip()}"
    except FileNotFoundError:
        return _grep_fallback(pattern, path)
    except subprocess.TimeoutExpired:
        return "Error: grep timed out after 15s — narrow the search path."


def _grep_fallback(pattern: str, path: str) -> str:
    matches = []
    for filepath in glob.glob(f"{path}/**/*", recursive=True):
        p = Path(filepath)
        if not p.is_file():
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    if pattern in line:
                        matches.append(f"{filepath}:{i}:{line.rstrip()}")
                        if len(matches) >= 200:
                            return "\n".join(matches)
        except OSError:
            continue
    return "\n".join(matches) if matches else "No matches found."


def run_shell(command: str, timeout: int = 30) -> str:
    """PROMPT-tier (further gated by permissions.py's allowlist for
    known-safe commands like pytest/npm test — see permissions.py)."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout + result.stderr
        status = "OK" if result.returncode == 0 else f"exit code {result.returncode}"
        return f"[{status}]\n{output.strip() or '(no output)'}"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except OSError as e:
        return f"Error running command: {e}"