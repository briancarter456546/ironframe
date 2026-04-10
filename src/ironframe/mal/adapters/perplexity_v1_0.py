# ============================================================================
# ironframe/mal/adapters/perplexity_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Perplexity Sonar adapter for Iron Frame MAL.
#
# Perplexity uses an OpenAI-compatible API at https://api.perplexity.ai.
# This adapter uses the openai SDK with a custom base_url.
#
# Key difference from Anthropic: Perplexity is WEB-GROUNDED. Responses
# include citations from live web search. This is what makes it valuable
# for Tier 3 cross-model verification -- it's not just a different model,
# it has access to external evidence.
#
# Models:
#   sonar              -- fast, web-grounded (~$1/M tokens)
#   sonar-pro          -- higher quality, web-grounded (~$3/M tokens)
#   sonar-deep-research -- multi-step research (~$5/M tokens)
#
# Usage:
#   from ironframe.mal.adapters.perplexity_v1_0 import PerplexityAdapter
#   adapter = PerplexityAdapter(api_key='pplx-...')
#   result = adapter.complete('What is the current inflation rate?')
# ============================================================================

from typing import Any, Dict, Generator, Optional


# Cost per million tokens (as of April 2026)
_PRICING = {
    "sonar": {"input": 1.00, "output": 1.00},
    "sonar-pro": {"input": 3.00, "output": 15.00},
    "sonar-deep-research": {"input": 2.00, "output": 8.00},
}


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate cost in USD from token counts."""
    pricing = _PRICING.get(model, {"input": 1.00, "output": 1.00})
    cost = (tokens_in * pricing["input"] / 1_000_000) + (tokens_out * pricing["output"] / 1_000_000)
    return round(cost, 8)


class PerplexityAdapter:
    """Adapter for the Perplexity Sonar API (OpenAI-compatible).

    Web-grounded: responses include citations from live web search.
    Uses the openai SDK with custom base_url.
    """

    PERPLEXITY_BASE_URL = "https://api.perplexity.ai"

    def __init__(self, api_key: str, default_model: str = "sonar"):
        self._api_key = api_key
        self._default_model = default_model
        self._client = None

    def _get_client(self):
        """Lazy-load the openai client pointed at Perplexity."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "The 'openai' package is required for the Perplexity adapter. "
                    "Install it with: pip install openai"
                )
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self.PERPLEXITY_BASE_URL,
            )
        return self._client

    def complete(
        self,
        prompt: str,
        system: str = "",
        model: str = "",
        max_tokens: int = 1024,
        temperature: float = 1.0,
    ) -> Dict[str, Any]:
        """Synchronous completion. Returns normalized response dict."""
        client = self._get_client()
        model = model or self._default_model

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        choice = response.choices[0] if response.choices else None
        text = choice.message.content if choice else ""

        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0

        return {
            "text": text,
            "model": model,
            "provider": "perplexity",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": _calc_cost(model, tokens_in, tokens_out),
            "stop_reason": choice.finish_reason if choice else "unknown",
        }

    def stream(
        self,
        prompt: str,
        system: str = "",
        model: str = "",
        max_tokens: int = 1024,
        temperature: float = 1.0,
    ) -> Generator[Dict[str, Any], None, None]:
        """Streaming completion. Yields chunk dicts, then a final summary.

        Note: Perplexity streaming doesn't return token counts per chunk,
        so we estimate from accumulated text.
        """
        client = self._get_client()
        model = model or self._default_model

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )

        full_text_parts = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                chunk_text = chunk.choices[0].delta.content
                full_text_parts.append(chunk_text)
                yield {"type": "chunk", "text": chunk_text, "tokens": 0}

        full_text = "".join(full_text_parts)
        # Estimate tokens (Perplexity doesn't always return usage in streaming)
        est_tokens_out = len(full_text) // 4  # rough estimate
        est_tokens_in = len(prompt) // 4

        yield {
            "type": "final",
            "text": full_text,
            "model": model,
            "provider": "perplexity",
            "tokens_in": est_tokens_in,
            "tokens_out": est_tokens_out,
            "cost_usd": _calc_cost(model, est_tokens_in, est_tokens_out),
            "stop_reason": "stop",
        }
