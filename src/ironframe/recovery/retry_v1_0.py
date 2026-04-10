# ============================================================================
# ironframe/recovery/retry_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Retry with variation for Iron Frame.
#
# NOT identical retries. Each retry varies one or more of:
#   - Temperature (different sampling)
#   - Model (fallback via MAL router)
#   - Prompt phrasing (rephrase instruction)
#
# Error context preserved across retries so the system knows WHY it failed
# (rate limit vs content policy vs reasoning error vs timeout).
#
# Usage:
#   from ironframe.recovery.retry_v1_0 import RetryExecutor
#   from ironframe.mal import get_client
#
#   client = get_client()
#   executor = RetryExecutor(client, max_retries=3)
#   result = executor.complete_with_retry(
#       prompt='Explain quantum entanglement',
#       preference='smart',
#   )
# ============================================================================

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RetryAttempt:
    """Record of a single retry attempt."""
    attempt: int
    variation: str       # what was varied: 'original', 'temperature', 'model', 'rephrase'
    success: bool
    error: str = ""
    error_type: str = ""
    cost_usd: float = 0.0
    duration_ms: float = 0.0


@dataclass
class RetryResult:
    """Full result of a retry sequence."""
    success: bool
    result: Optional[Dict[str, Any]] = None
    attempts: List[RetryAttempt] = field(default_factory=list)
    total_cost_usd: float = 0.0
    final_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "attempts": len(self.attempts),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "variations_tried": [a.variation for a in self.attempts],
            "final_error": self.final_error,
        }


# Error classification for choosing retry strategy
_RATE_LIMIT_ERRORS = ("rate_limit", "429", "too many requests", "rate limit")
_CONTENT_POLICY_ERRORS = ("content_policy", "content policy", "safety", "refused")
_TIMEOUT_ERRORS = ("timeout", "timed out", "deadline exceeded")


def _classify_error(error: str) -> str:
    """Classify an error to determine retry strategy."""
    error_lower = error.lower()
    for pattern in _RATE_LIMIT_ERRORS:
        if pattern in error_lower:
            return "rate_limit"
    for pattern in _CONTENT_POLICY_ERRORS:
        if pattern in error_lower:
            return "content_policy"
    for pattern in _TIMEOUT_ERRORS:
        if pattern in error_lower:
            return "timeout"
    return "unknown"


# Retry variations: each attempt varies something different
_RETRY_VARIATIONS = [
    {"variation": "temperature", "temp_delta": -0.3},
    {"variation": "model", "preference": "fast"},     # try cheaper/different model
    {"variation": "rephrase", "prefix": "Please try again. "},
]


class RetryExecutor:
    """Executes MAL calls with variation-based retries.

    Each retry changes something about the request rather than
    sending an identical request. Error context is preserved.
    """

    def __init__(
        self,
        client,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        backoff_factor: float = 2.0,
    ):
        self._client = client
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_factor = backoff_factor

    def complete_with_retry(
        self,
        prompt: str,
        system: str = "",
        preference: str = "smart",
        max_tokens: int = 1024,
        temperature: float = 1.0,
    ) -> RetryResult:
        """Complete with automatic retry on failure.

        Varies temperature, model, or phrasing on each retry.
        Backs off exponentially between attempts.
        """
        attempts = []
        total_cost = 0.0

        # Attempt 0: original request
        attempt = self._try_call(
            prompt=prompt, system=system, preference=preference,
            max_tokens=max_tokens, temperature=temperature,
            attempt_num=0, variation="original",
        )
        attempts.append(attempt)
        total_cost += attempt.cost_usd

        if attempt.success:
            return RetryResult(success=True, result=attempt.__dict__.get("_result"),
                               attempts=attempts, total_cost_usd=total_cost)

        # Retries with variation
        for i in range(min(self.max_retries, len(_RETRY_VARIATIONS))):
            error_class = _classify_error(attempt.error)

            # Don't retry content policy errors -- they won't change
            if error_class == "content_policy":
                break

            # Backoff
            wait = self.backoff_base * (self.backoff_factor ** i)
            if error_class == "rate_limit":
                wait = max(wait, 5.0)  # minimum 5s for rate limits
            time.sleep(wait)

            # Apply variation
            var = _RETRY_VARIATIONS[i]
            var_prompt = prompt
            var_temp = temperature
            var_pref = preference

            if var["variation"] == "temperature":
                var_temp = max(0.0, temperature + var.get("temp_delta", 0))
            elif var["variation"] == "model":
                var_pref = var.get("preference", "fast")
            elif var["variation"] == "rephrase":
                var_prompt = var.get("prefix", "") + prompt

            attempt = self._try_call(
                prompt=var_prompt, system=system, preference=var_pref,
                max_tokens=max_tokens, temperature=var_temp,
                attempt_num=i + 1, variation=var["variation"],
            )
            attempts.append(attempt)
            total_cost += attempt.cost_usd

            if attempt.success:
                return RetryResult(success=True, result=attempt.__dict__.get("_result"),
                                   attempts=attempts, total_cost_usd=total_cost)

        # All retries exhausted
        return RetryResult(
            success=False,
            attempts=attempts,
            total_cost_usd=total_cost,
            final_error=attempts[-1].error if attempts else "No attempts made",
        )

    def _try_call(
        self,
        prompt: str,
        system: str,
        preference: str,
        max_tokens: int,
        temperature: float,
        attempt_num: int,
        variation: str,
    ) -> RetryAttempt:
        """Execute a single call attempt."""
        start = time.time()
        try:
            result = self._client.complete(
                prompt=prompt,
                system=system,
                preference=preference,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            elapsed = (time.time() - start) * 1000
            attempt = RetryAttempt(
                attempt=attempt_num,
                variation=variation,
                success=True,
                cost_usd=result.get("cost_usd", 0.0),
                duration_ms=elapsed,
            )
            attempt.__dict__["_result"] = result
            return attempt
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            return RetryAttempt(
                attempt=attempt_num,
                variation=variation,
                success=False,
                error=str(exc),
                error_type=type(exc).__name__,
                duration_ms=elapsed,
            )
