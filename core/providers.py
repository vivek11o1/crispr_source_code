# crispr_core/providers.py
"""
Provider Factory — turns a config dict into a real LangChain chat model
client. Knows nothing about config.toml, prompting, or GitHub — only
consumes an already-resolved config dict passed in from main.py.
"""

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

PROVIDER_FACTORY = {
    "groq": lambda cfg: ChatGroq(api_key=cfg["api_key"], model=cfg["model"]),
    "openai": lambda cfg: ChatOpenAI(api_key=cfg["api_key"], model=cfg["model"]),
    "claude": lambda cfg: ChatAnthropic(api_key=cfg["api_key"], model=cfg["model"]),
    "zen": lambda cfg: ChatOpenAI(
        api_key=cfg["api_key"],
        model=cfg["model"],
        base_url=cfg.get("base_url", "https://opencode.ai/zen/v1"),
    ),
}


def get_llm(config: dict, use_fallback: bool = False):
    if use_fallback:
        provider_name = config["fallback"]["provider"]
    else:
        provider_name = config["active_provider"]

    if provider_name not in config["providers"]:
        raise RuntimeError(f"Unknown provider in config: {provider_name}")

    provider_cfg = config["providers"][provider_name]
    if not provider_cfg.get("api_key"):
        raise RuntimeError(f"No API key configured for provider: {provider_name}")

    return PROVIDER_FACTORY[provider_name](provider_cfg)


def get_fallback_model_name(config: dict) -> str:
    """Used by resilience.py to build a fallback-specific config dict when
    swapping providers mid-session, in case the fallback provider's model
    differs from its default 'model' field."""
    provider_name = config["fallback"]["provider"]
    provider_cfg = config["providers"][provider_name]
    return provider_cfg.get("fallback_model", provider_cfg["model"])