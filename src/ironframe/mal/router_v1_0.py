# ============================================================================
# ironframe/mal/router_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Capability-aware model router with spend tracking.
#
# Routes by PREFERENCE ("fast", "smart", "cheap", "verification"),
# not by model name. Model names live in config, not in calling code.
#
# Usage:
#   from ironframe.mal.router_v1_0 import ModelRouter
#   from ironframe.config_v1_0 import IronFrameConfig
#   from ironframe.mal.budget_v1_0 import BudgetTracker
#
#   config = IronFrameConfig.from_env()
#   budget = BudgetTracker(**config.budget)
#   router = ModelRouter(config, budget)
#
#   route = router.resolve('smart')
#   # route = {'provider': 'anthropic', 'model': 'claude-sonnet-4-6', 'api_key': 'sk-...'}
# ============================================================================

from typing import Dict, Optional

from ironframe.config_v1_0 import IronFrameConfig
from ironframe.mal.budget_v1_0 import BudgetTracker


# Rough cost estimates per 1K tokens (input + output blended) by model.
# Used for budget pre-checks. Actual cost recorded after the call.
_COST_PER_1K_TOKENS = {
    # Anthropic
    "claude-haiku-4-5-20251001": 0.001,
    "claude-sonnet-4-6": 0.009,
    "claude-opus-4-6": 0.045,
    # OpenAI
    "gpt-4o-mini": 0.0003,
    "gpt-4o": 0.0075,
    # Perplexity
    "sonar": 0.001,
    "sonar-pro": 0.003,
    "sonar-deep-research": 0.005,
}

# Fallback chain: if primary preference fails, try these in order
_FALLBACK_CHAIN = {
    "fast": ["cheap", "smart"],
    "smart": ["fast"],
    "cheap": ["fast"],
    "verification": ["smart"],
    "long-context": ["smart"],
}


class ModelRouter:
    """Resolves capability preferences to concrete provider + model + API key.

    Checks budget before returning a route. If budget is exhausted for the
    preferred model, tries the fallback chain (cheaper models first).
    """

    def __init__(self, config: IronFrameConfig, budget: Optional[BudgetTracker] = None):
        self._config = config
        self._budget = budget

    def resolve(
        self,
        preference: str = "smart",
        max_tokens: int = 1024,
        skip_budget_check: bool = False,
    ) -> Dict[str, str]:
        """Resolve a capability preference to a concrete route.

        Returns dict with keys: provider, model, api_key.
        Raises BudgetExhausted if no affordable route is available.
        """
        # Try primary preference
        route = self._try_route(preference, max_tokens, skip_budget_check)
        if route:
            return route

        # Try fallback chain
        for fallback_pref in _FALLBACK_CHAIN.get(preference, []):
            route = self._try_route(fallback_pref, max_tokens, skip_budget_check)
            if route:
                return route

        # Nothing affordable — re-raise the budget check on primary to get clear error
        if self._budget and not skip_budget_check:
            primary = self._config.get_route(preference)
            cost_est = estimate_cost(primary.get("model", ""), max_tokens)
            self._budget.check(cost_est)  # will raise BudgetExhausted

        # No budget constraint but still no route — config issue
        raise ValueError(
            f"No route configured for preference '{preference}'. "
            f"Available: {list(self._config.routing.keys())}"
        )

    def _try_route(
        self,
        preference: str,
        max_tokens: int,
        skip_budget_check: bool,
    ) -> Optional[Dict[str, str]]:
        """Try to resolve a single preference. Returns None if budget blocked."""
        route_config = self._config.get_route(preference)
        if not route_config:
            return None

        provider = route_config.get("provider", "")
        model = route_config.get("model", "")

        if not provider or not model:
            return None

        # Budget pre-check
        if self._budget and not skip_budget_check:
            cost_est = estimate_cost(model, max_tokens)
            try:
                self._budget.check(cost_est)
            except Exception:
                return None  # over budget — try fallback

        # Get API key
        try:
            api_key = self._config.get_api_key(provider)
        except ValueError:
            return None  # no key configured — try fallback

        return {
            "provider": provider,
            "model": model,
            "api_key": api_key,
        }

    def record_cost(self, actual_cost: float) -> None:
        """Record actual cost after a completed API call."""
        if self._budget:
            self._budget.record(actual_cost)


def estimate_cost(model: str, max_tokens: int) -> float:
    """Estimate cost for a request. Conservative (assumes max_tokens used)."""
    per_1k = _COST_PER_1K_TOKENS.get(model, 0.01)  # default to moderate estimate
    return per_1k * (max_tokens / 1000.0)
