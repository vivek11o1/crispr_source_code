# crispr

AI-powered agentic coding CLI. Point it at a repo, describe what you want, and it reads, edits, commits, and pushes — with a permission gate so nothing dangerous runs without your approval.

## Project Structure

```
New folder/
├── launcher/                  # CLI entrypoint — compiles to crispr(.exe)
│   ├── main.py                # Typer app: version, doctor, config, health, prompt dispatch
│   ├── config.py              # Config manager: ~/.config/crispr/config.toml (read/write/recover)
│   ├── license.py             # License validation (with offline grace period)
│   ├── manifest.py            # Manifest trust layer: checksum verification for crispr-core
│   ├── env_check.py           # Environment checks: git, network, disk, config, license
│   ├── updater.py             # Update manager: download + atomic swap for crispr-core
│   ├── logging_setup.py       # Launcher-level crash logging
│   ├── UI.py                  # Rich tables/panels for doctor, config, health output
│   ├── requirements.txt       # Launcher dependencies
│   └── crispr_launcher_venv/  # Launcher virtual environment
│
├── core/                      # Agent runtime — compiles to crispr-core(.exe)
│   ├── main.py                # Runtime entrypoint: reads config, builds graph, runs agent loop
│   ├── graph.py               # LangGraph agent loop: compact -> agent -> permission_gate -> tools
│   ├── states.py              # SessionState TypedDict, Task, SessionSummary
│   ├── providers.py           # Provider factory: Zen, Groq, OpenAI, Claude via LangChain
│   ├── tools.py               # File/shell tools: read_file, write_file, edit_file, grep, run_shell
│   ├── tools_git.py           # Local git tools: diff, status, log, commit, branch
│   ├── tools_github.py        # Remote GitHub tools: push, create_pr, fetch_repo_info, fetch_issues
│   ├── manage_task.py         # Task planner: create, update_status, list
│   ├── permissions.py         # Permission gate: auto/prompt/confirm tiers per tool
│   ├── compaction.py          # Context compaction: summarizes long sessions to save tokens
│   ├── resilience.py          # Retry/backoff/fallback: wraps every LLM call
│   ├── persistence.py         # SQLite checkpointer + JSONL transcript logger
│   ├── requirements.txt       # Core dependencies
│   ├── crispr_core_venv/      # Core virtual environment
│   └── ui/                    # Rich terminal UI subpackage
│       ├── ui.py              # CRISPRUI orchestrator: wires all components, render_event()
│       ├── banner.py          # ASCII logo + system info panel
│       ├── dashboard.py       # Icon-labelled info cards
│       ├── status.py          # Footer status bar
│       ├── thinking.py        # Animated thinking panel with token counters
│       ├── streaming.py       # Token-by-token markdown renderer
│       ├── tool_cards.py      # Tool invocation cards + execution timeline
│       ├── diff_view.py       # Syntax-highlighted unified diffs
│       ├── notifications.py   # Auto-dismissing toast notifications
│       ├── prompt.py          # Custom input prompt + command palette
│       ├── theme.py           # ThemeManager, Palette, color themes (orange/blue/green/purple)
│       ├── utils.py           # Re-exports from theme.py for backwards compatibility
│       └── animations.py      # Spinner, typewriter, fade, line-by-line reveal
│
└── README.md                  # This file
```

## Setup

### Prerequisites
- Python 3.11+ (tested with 3.13)
- Git
- An LLM provider API key (OpenCode Zen, Groq, OpenAI, or Claude)

### 1. Create virtual environments

```bash
# Launcher venv
cd launcher
python -m venv crispr_launcher_venv
crispr_launcher_venv\Scripts\activate      # Windows
pip install -r requirements.txt

# Core venv
cd ../core
python -m venv crispr_core_venv
crispr_core_venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Configure your API key

Edit the config file at `%LOCALAPPDATA%\crispr\crispr\config.toml` (Windows) or `~/.config/crispr/config.toml` (Linux/Mac):

```toml
schema_version = 1
active_provider = "zen"
max_turn = 25
compaction_threshold_tokens = 6000

[license]
key = ""
tier = "free"
last_validated = "2026-07-22T00:00:00+00:00"

[providers.zen]
api_key = "sk-ZE_YOUR_ZEN_KEY_HERE"
model = "mimo-v2.5-free"
fallback_model = "north-mini-code-free"
base_url = "https://opencode.ai/zen/v1"

[providers.groq]
api_key = "gsk_YOUR_GROQ_KEY_HERE"
model = "llama-3.1-8b-instant"
fallback_model = "llama-3.3-70b-versatile"

[providers.openai]
api_key = ""
model = "gpt-4o-mini"
fallback_model = "gpt-4o-mini"

[providers.claude]
api_key = ""
model = "claude-sonnet-5"
fallback_model = "claude-sonnet-5"

[fallback]
enabled = true
provider = "zen"

[integrations.github]
token = ""
```

Or use the CLI:
```bash
python main.py config set zen
# Paste your API key when prompted
```

### 3. Create the core wrapper

The launcher expects a `crispr-core.bat` (or `.exe`) next to its venv's `Scripts/` directory. Create a wrapper:

```bat
@echo off
"C:\path\to\core\crispr_core_venv\Scripts\python.exe" "C:\path\to\core\main.py" %*
```

### 4. Create the manifest

Place `manifest.json` next to the launcher venv's `Scripts/` directory:

```json
{
  "launcher_version": "0.1.0",
  "core_version": "0.1.0",
  "core_path": "crispr-core.bat",
  "sha256": "<sha256 of your wrapper>",
  "core_download_url": "https://yourdocsite.com/releases/crispr-core"
}
```

Get the SHA256:
```bash
certutil -hashfile launcher\crispr_launcher_venv\Scripts\crispr-core.bat SHA256
```

## Usage

All commands run from the `launcher/` directory.

### Prompt mode (the main thing)
```bash
# Natural language — no quotes needed
python main.py list the files in the current directory
python main.py fix the bug in paymentgateway.py
python main.py add error handling to the API client
python main.py write tests for the auth module
```

### Subcommands
```bash
python main.py version       # Show launcher and core versions
python main.py doctor        # Run environment checks (git, network, disk, config, license)
python main.py health        # Quick status: license valid? core present?
python main.py config show   # Show provider configuration
python main.py config set zen   # Switch provider and set API key
python main.py repair        # Re-download manifest + fix corrupted config
python main.py update        # Check for and apply core updates
```

### Resume a session
```bash
python main.py --session <session-id> continue working on the auth module
```

## Architecture

### How a prompt flows through the system

```
User types: python main.py fix the bug in auth.py
       |
       v
launcher/main.py  ──── Detects no subcommand, enters prompt mode
       |
       ├── load_config()        reads config.toml
       ├── ensure_valid_license()   validates license (with offline grace)
       ├── _verify_core()       reads manifest.json, checks SHA256
       |
       v
subprocess.run([crispr-core.bat, "--prompt", "fix the bug in auth.py"])
       |
       v
core/main.py      ──── Reads config from CRISPR_CONFIG_PATH env var
       |
       ├── get_checkpointer()   SQLite session persistence
       ├── get_llm(config)      Creates LangChain chat model (Zen/Groq/OpenAI/Claude)
       ├── CRISPRUI(...)        Sets up Rich terminal UI
       ├── build_graph(...)     Compiles the LangGraph agent loop
       |
       v
graph.stream()    ──── Agent loop:
       |
       ├── compact              Summarize context if over token threshold
       ├── agent                Send messages to LLM, get response + tool calls
       ├── permission_gate      Check tool tier (auto/prompt/confirm), ask user if needed
       ├── tools                Execute approved tool calls
       └── loop back to compact
```

### Tool permission tiers

| Tier | Tools | Behavior |
|------|-------|----------|
| **AUTO** | read_file, grep, list_files, git_diff, git_status, git_log | Runs without asking |
| **PROMPT** | write_file, edit_file, run_shell, git_commit, git_branch_create, manage_tasks | Asks once per session; can be allowlisted |
| **CONFIRM** | github_push, github_create_pr, github_fetch_repo_info, github_fetch_issues | Always asks, never allowlisted |

### Provider fallback

If the primary provider hits rate limits (5 retries with exponential backoff), the system automatically falls back to the configured fallback provider using the same conversation context.

### Context compaction

When the conversation exceeds `compaction_threshold_tokens` (default: 6000), the older messages are summarized by a cheap/fast model into a `SessionSummary` containing decisions made, current task, and open issues. The summary is injected as a system message so the LLM never loses track.

## Configuration

Config file location: `platformdirs.user_config_dir("crispr")` + `config.toml`

| Key | Default | Description |
|-----|---------|-------------|
| `active_provider` | `zen` | Which LLM provider to use |
| `max_turn` | `25` | Max agent loop iterations per session |
| `compaction_threshold_tokens` | `6000` | Token count before context is summarized |
| `providers.<name>.api_key` | `""` | API key for the provider |
| `providers.<name>.model` | varies | Model name to use |
| `providers.<name>.fallback_model` | varies | Fallback model for the provider |
| `fallback.enabled` | `true` | Whether to fall back on rate limits |
| `fallback.provider` | `zen` | Which provider to fall back to |
| `integrations.github.token` | `""` | GitHub PAT for remote tools |

## Session Persistence

Sessions are stored in SQLite at `platformdirs.user_data_dir("crispr")/sessions.db`. Resume a session with `--session <id>`.

Transcript logs (JSONL) are written to `platformdirs.user_data_dir("crispr")/logs/<thread_id>.jsonl`.

## E2E Test Recipe

### Quick smoke test (no LLM needed)

```bash
cd launcher
python main.py version        # prints launcher/core versions
python main.py doctor         # shows 5 PASS checks
python main.py config show    # shows provider table with key status
python main.py health         # shows License: OK, Core: OK
```

### Full prompt test (needs API key)

```bash
cd launcher
python main.py list the files in the current directory
python main.py what is this project about
python main.py create a file called hello.py with a print hello world
```

### Verify config is correct

```python
python -c "
import tomllib, platformdirs
from pathlib import Path
p = Path(platformdirs.user_config_dir('crispr')) / 'config.toml'
with open(p, 'rb') as f:
    c = tomllib.load(f)
print('Provider:', c['active_provider'])
print('Key set:', bool(c['providers'][c['active_provider']]['api_key']))
print('Model:', c['providers'][c['active_provider']]['model'])
print('License OK:', bool(c['license']['last_validated']))
"
```

### Check the logs

```bash
# Launcher crash log
type %LOCALAPPDATA%\crispr\launcher.log

# Core session transcript
type %LOCALAPPDATA%\crispr\crispr\logs\<session-id>.jsonl
```

## Known Issues

1. **License server is fake** — `http://127.0.0.1:8000/api/license/validate` doesn't exist. Set `last_validated` in config.toml to a recent ISO timestamp to bypass.
2. **Docs site is placeholder** — `https://yourdocsite.com/` URLs in manifest.py and license.py are not real.
3. **GitHub tools are partial** — `github_push` is a stub that returns a fake success message.
4. **Windows cp1252 encoding** — The launcher sets `PYTHONIOENCODING=utf-8` when spawning core to handle Rich's Unicode output.
5. **Groq model name** — The default `openai/gpt-OSS-120B` in config.py defaults was replaced with `llama-3.3-70b-versatile`.
