"""
Config Manager — the ONLY file that reads/writes ~/.crispr/config.toml.
Owns: schema defaults, atomic writes, corruption recovery (via a rolling
"last known good" snapshot), and provider auto-detection by key prefix.
"""
import shutil, os, tomllib, tomli_w
from pathlib import Path
from platformdirs import user_config_dir

#file_paths
CONFIG_DIR = Path(user_config_dir("crispr"))
CONFIG_FILE = CONFIG_DIR/"config.toml"

#copy_files
BACKUP_FILE = CONFIG_FILE.with_suffix(".toml.bak")
LAST_KNOWN_GOOD_FILE = CONFIG_FILE.with_suffix(".toml.lastgood")

SCHEMA_VERSION = 1

DEFAULTS = {
    "schema_version": SCHEMA_VERSION,
    "active_provider": "groq",
    "max_turn": 15,
    "compaction_threshold_tokens": 6000,
    "license": {"license_key": "", "tier": "free", "last_validated": ""},
    "providers": {
        "groq": {"api_key": "", "model": "openai/gpt-oss-20b", "fallback_model": "openai/gpt-oss-120b", "rpm_limit": 30},
        "openrouter": {"api_key": "", "model": "nvidia/nemotron-3-ultra-550b-a55b:free", "fallback_model": "nvidia/nemotron-3-ultra-550b-a55b:free", "base_url": "https://openrouter.ai/api/v1", "rpm_limit": 20},
        "openai": {"api_key": "", "model": "gpt-4o-mini", "fallback_model": "gpt-4o-mini", "rpm_limit": 500},
        "claude": {"api_key": "", "model": "claude-sonnet-5", "fallback_model": "claude-sonnet-5", "rpm_limit": 50},
        "zen": {"api_key": "", "model": "mimo-v2.5-free", "fallback_model": "mimo-v2.5-free", "base_url": "https://opencode.ai/zen/v1", "rpm_limit": 1000},
    },
    "fallback": {"enabled": True, "provider": "groq"},
    "integrations": {"github": {"token": ""}}
}

_PROVIDER_PREFIXES = [("sk-or", "openrouter"), ("gsk", "groq"), ("sk-ant", "claude"), ("sk-ZE", "zen"), ("sk-", "openai")]

_ENV_PROVIDER_VARS = [
    ("OPENROUTER_API_KEY", "openrouter"),
    ("GROQ_API_KEY", "groq"),
    ("OPENAI_API_KEY", "openai"),
    ("ANTHROPIC_API_KEY", "claude"),
]

def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """
    Recursively merge two dictionaries, with values from `overrides` taking precedence.
    """
    result = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def _parse_config_file(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None
    try:
        with open(file_path, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return None
def load_config():
    if not CONFIG_FILE.exists():
        save_config(dict(DEFAULTS))
        return dict(DEFAULTS)
    user_cfg = _parse_config_file(CONFIG_FILE)
    
    #functioning_path
    if user_cfg is not None:
        return _deep_merge(DEFAULTS, user_cfg)
    
    #currupt_path_
    shutil.copy(CONFIG_FILE, BACKUP_FILE)
    print(f"[warning] config.toml was corrupted. Broken copy saved to {BACKUP_FILE}.")
    #recovery
    recovered_cfg = _parse_config_file(LAST_KNOWN_GOOD_FILE)
    if recovered_cfg is not None:
        print("[info] Recovered your last valid configuration "
              "(license, provider keys, GitHub token included).")
        merged = _deep_merge(DEFAULTS, recovered_cfg)
        save_config(merged)
        return merged
    print("[warning] No recoverable backup found. Starting from defaults.")
    return dict(DEFAULTS)
    

def save_config(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)  #we make a directory in declared given path 
    if CONFIG_FILE.exists() and _parse_config_file(CONFIG_FILE) is not None:
        shutil.copy(CONFIG_FILE, LAST_KNOWN_GOOD_FILE)
        
    #write in the temporary file and then dump it into currupted config file
    tmp_path = CONFIG_FILE.with_suffix(".toml.tmp") #make a temp file path
    with open(tmp_path, "wb") as f:
        tomli_w.dump(data, f)
    os.replace(tmp_path, CONFIG_FILE)
    
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except (NotImplementedError, OSError):
        pass
    shutil.copy(CONFIG_FILE, LAST_KNOWN_GOOD_FILE)
    
def detect_provider(api_key: str) -> str | None:
    for prefix, provider in _PROVIDER_PREFIXES:
        if api_key.startswith(prefix):
            return provider
    return None

def detect_env_provider() -> tuple[str, str] | None:
    """Check environment variables for provider API keys.

    Returns (provider_name, api_key) or None.
    Priority order: openrouter > groq > openai > anthropic.
    """
    for env_var, provider in _ENV_PROVIDER_VARS:
        key = os.environ.get(env_var, "").strip()
        if key:
            return provider, key
    return None

def set_provider_key(config: dict, provider: str, api_key: str) -> dict:
    if provider not in config["providers"]:
        raise ValueError(f"Uknown provider: {provider}")
    config["providers"][provider]["api_key"] = api_key
    save_config(config)
    return config
    
def set_github_token(config: dict, token: str) -> dict:   
    config["integrations"]["github"]["token"] = token
    save_config(config)
    return config