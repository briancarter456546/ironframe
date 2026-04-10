# ============================================================================
# ironframe/config_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Iron Frame's own configuration loader. Pluggable credential and settings
# management with NO imports from Brian's domain code.
#
# Priority order (highest wins):
#   1. Constructor kwargs
#   2. JSON config file
#   3. .env file
#   4. OS environment variables
#
# Usage:
#   config = IronFrameConfig.from_env()              # env vars only
#   config = IronFrameConfig.from_env_file('.env')    # .env + env vars
#   config = IronFrameConfig.from_json('config.json') # JSON + env vars
#   config = IronFrameConfig(api_keys={'anthropic': 'sk-...'})  # direct
# ============================================================================

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


# Default budget caps (USD)
_DEFAULT_BUDGET = {
    "per_request": 0.50,
    "per_session": 5.00,
    "per_day": 25.00,
}

# Default routing: preference -> provider + model
_DEFAULT_ROUTING = {
    "fast": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "smart": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    "cheap": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    "verification": {"provider": "perplexity", "model": "sonar"},
    "long-context": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
}

# Default audit settings
_DEFAULT_AUDIT = {
    "backend": "jsonl",
    "output_dir": "output/ironframe",
    "max_output_summary_len": 500,
    "retention_class": "default",
}


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a .env file into a dict. Handles quotes, comments, blank lines."""
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        result[key] = value
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively. Override wins on conflict."""
    merged = base.copy()
    for k, v in override.items():
        if k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


@dataclass
class IronFrameConfig:
    """Central configuration for all Iron Frame components.

    api_keys: provider name -> API key string
    routing: preference name -> {provider, model} mapping
    audit: audit logger settings
    budget: spend cap settings (per_request, per_session, per_day in USD)
    extra: arbitrary additional config for extensions
    """

    api_keys: Dict[str, str] = field(default_factory=dict)
    routing: Dict[str, Dict[str, str]] = field(default_factory=lambda: _DEFAULT_ROUTING.copy())
    audit: Dict[str, Any] = field(default_factory=lambda: _DEFAULT_AUDIT.copy())
    budget: Dict[str, float] = field(default_factory=lambda: _DEFAULT_BUDGET.copy())
    extra: Dict[str, Any] = field(default_factory=dict)

    # --- Factory methods ---

    @classmethod
    def from_env(cls, **overrides) -> "IronFrameConfig":
        """Build config from OS environment variables only.

        Recognized env vars:
          ANTHROPIC_API_KEY, OPENAI_API_KEY, PERPLEXITY_API_KEY
          IRONFRAME_BUDGET_PER_REQUEST, IRONFRAME_BUDGET_PER_SESSION,
          IRONFRAME_BUDGET_PER_DAY
          IRONFRAME_AUDIT_DIR
        """
        api_keys = {}
        for provider, env_var in [
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
            ("perplexity", "PERPLEXITY_API_KEY"),
        ]:
            val = os.environ.get(env_var, "")
            if val:
                api_keys[provider] = val

        budget = _DEFAULT_BUDGET.copy()
        for cap_name in ("per_request", "per_session", "per_day"):
            env_val = os.environ.get(f"IRONFRAME_BUDGET_{cap_name.upper()}", "")
            if env_val:
                try:
                    budget[cap_name] = float(env_val)
                except ValueError:
                    pass

        audit = _DEFAULT_AUDIT.copy()
        audit_dir = os.environ.get("IRONFRAME_AUDIT_DIR", "")
        if audit_dir:
            audit["output_dir"] = audit_dir

        return cls(
            api_keys=_deep_merge(api_keys, overrides.get("api_keys", {})),
            routing=_deep_merge(_DEFAULT_ROUTING.copy(), overrides.get("routing", {})),
            audit=_deep_merge(audit, overrides.get("audit", {})),
            budget=_deep_merge(budget, overrides.get("budget", {})),
            extra=overrides.get("extra", {}),
        )

    @classmethod
    def from_env_file(cls, env_path: str = ".env", **overrides) -> "IronFrameConfig":
        """Build config from a .env file, falling back to OS env vars.

        .env values take priority over OS env vars. Constructor overrides
        take priority over everything.
        """
        env_vars = _parse_env_file(Path(env_path))

        api_keys = {}
        for provider, env_var in [
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
            ("perplexity", "PERPLEXITY_API_KEY"),
        ]:
            val = env_vars.get(env_var, "") or os.environ.get(env_var, "")
            if val:
                api_keys[provider] = val

        budget = _DEFAULT_BUDGET.copy()
        for cap_name in ("per_request", "per_session", "per_day"):
            env_key = f"IRONFRAME_BUDGET_{cap_name.upper()}"
            env_val = env_vars.get(env_key, "") or os.environ.get(env_key, "")
            if env_val:
                try:
                    budget[cap_name] = float(env_val)
                except ValueError:
                    pass

        audit = _DEFAULT_AUDIT.copy()
        audit_dir = env_vars.get("IRONFRAME_AUDIT_DIR", "") or os.environ.get("IRONFRAME_AUDIT_DIR", "")
        if audit_dir:
            audit["output_dir"] = audit_dir

        return cls(
            api_keys=_deep_merge(api_keys, overrides.get("api_keys", {})),
            routing=_deep_merge(_DEFAULT_ROUTING.copy(), overrides.get("routing", {})),
            audit=_deep_merge(audit, overrides.get("audit", {})),
            budget=_deep_merge(budget, overrides.get("budget", {})),
            extra=overrides.get("extra", {}),
        )

    @classmethod
    def from_json(cls, json_path: str, **overrides) -> "IronFrameConfig":
        """Build config from a JSON file, falling back to OS env vars for keys.

        JSON structure:
        {
            "api_keys": {"anthropic": "sk-...", ...},
            "routing": {"fast": {"provider": "anthropic", "model": "..."}},
            "audit": {"backend": "jsonl", "output_dir": "..."},
            "budget": {"per_request": 0.50, ...},
            "extra": {}
        }

        API keys in JSON take priority over env vars. Constructor overrides
        take priority over everything.
        """
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Iron Frame config file not found: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Start with env vars as base for api_keys
        api_keys = {}
        for provider, env_var in [
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
            ("perplexity", "PERPLEXITY_API_KEY"),
        ]:
            val = os.environ.get(env_var, "")
            if val:
                api_keys[provider] = val

        # JSON overrides env vars
        api_keys = _deep_merge(api_keys, data.get("api_keys", {}))

        return cls(
            api_keys=_deep_merge(api_keys, overrides.get("api_keys", {})),
            routing=_deep_merge(
                _deep_merge(_DEFAULT_ROUTING.copy(), data.get("routing", {})),
                overrides.get("routing", {}),
            ),
            audit=_deep_merge(
                _deep_merge(_DEFAULT_AUDIT.copy(), data.get("audit", {})),
                overrides.get("audit", {}),
            ),
            budget=_deep_merge(
                _deep_merge(_DEFAULT_BUDGET.copy(), data.get("budget", {})),
                overrides.get("budget", {}),
            ),
            extra=_deep_merge(data.get("extra", {}), overrides.get("extra", {})),
        )

    # --- Accessors ---

    def get_api_key(self, provider: str) -> str:
        """Get API key for a provider. Raises if not found."""
        key = self.api_keys.get(provider, "")
        if not key:
            raise ValueError(
                f"No API key configured for provider '{provider}'. "
                f"Set it via env var, .env file, JSON config, or constructor."
            )
        return key

    def get_route(self, preference: str) -> Dict[str, str]:
        """Get provider+model for a capability preference. Falls back to 'smart'."""
        return self.routing.get(preference, self.routing.get("smart", {}))

    def get_audit_dir(self) -> Path:
        """Get the audit output directory, creating it if needed."""
        p = Path(self.audit.get("output_dir", "output/ironframe"))
        p.mkdir(parents=True, exist_ok=True)
        return p


if __name__ == "__main__":
    # Quick sanity check
    cfg = IronFrameConfig.from_env()
    print(f"Iron Frame Config v1.0")
    print(f"  API keys configured: {list(cfg.api_keys.keys())}")
    print(f"  Routing preferences: {list(cfg.routing.keys())}")
    print(f"  Budget caps: {cfg.budget}")
    print(f"  Audit dir: {cfg.get_audit_dir()}")
