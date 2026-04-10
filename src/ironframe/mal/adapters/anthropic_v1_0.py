# ============================================================================
# ironframe/mal/adapters/anthropic_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Anthropic Messages API adapter for Iron Frame MAL.
#
# Gets API key from IronFrameConfig, NOT from anthropic_key_helper.py.
# Zero imports from Brian's domain code.
#
# Normalizes Anthropic responses into Iron Frame's standard format:
#   {text, model, provider, tokens_in, tokens_out, cost_usd, stop_reason}
#
# Usage:
#   from ironframe.mal.adapters.anthropic_v1_0 import AnthropicAdapter
#   adapter = AnthropicAdapter(api_key='sk-...')
#   result = adapter.complete('Hello', model='claude-haiku-4-5-20251001')
#   # result = {'text': '...', 'tokens_in': 5, 'tokens_out': 12, ...}
# ============================================================================

from typing import Any, Dict, Generator, Optional


# Cost per million tokens (as of April 2026)
_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
}


def _calc_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Calculate cost in USD from token counts."""
    pricing = _PRICING.get(model, {"input": 3.00, "output": 15.00})
    cost = (tokens_in * pricing["input"] / 1_000_000) + (tokens_out * pricing["output"] / 1_000_000)
    return round(cost, 8)


class AnthropicAdapter:
    """Adapter for the Anthropic Messages API.

    Wraps the anthropic SDK into Iron Frame's normalized interface.
    Handles both sync completion and streaming.
    """

    def __init__(self, api_key: str, default_model: str = "claude-haiku-4-5-20251001"):
        self._api_key = api_key
        self._default_model = default_model
        self._client = None

    def _get_client(self):
        """Lazy-load the anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required for the Anthropic adapter. "
                    "Install it with: pip install anthropic"
                )
            self._client = anthropic.Anthropic(api_key=self._api_key)
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

        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        text = response.content[0].text if response.content else ""

        return {
            "text": text,
            "model": response.model,
            "provider": "anthropic",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": _calc_cost(model, tokens_in, tokens_out),
            "stop_reason": response.stop_reason,
        }

    def stream(
        self,
        prompt: str,
        system: str = "",
        model: str = "",
        max_tokens: int = 1024,
        temperature: float = 1.0,
    ) -> Generator[Dict[str, Any], None, None]:
        """Streaming completion. Yields chunk dicts, then a final summary dict.

        Chunk dict: {type: 'chunk', text: '...', tokens: N}
        Final dict: {type: 'final', text: '...', model: '...', tokens_in: N, ...}
        """
        client = self._get_client()
        model = model or self._default_model

        messages = [{"role": "user", "content": prompt}]
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        full_text_parts = []
        tokens_in = 0
        tokens_out = 0

        with client.messages.stream(**kwargs) as stream:
            for event in stream:
                if hasattr(event, "type"):
                    if event.type == "content_block_delta":
                        chunk_text = event.delta.text if hasattr(event.delta, "text") else ""
                        if chunk_text:
                            full_text_parts.append(chunk_text)
                            yield {"type": "chunk", "text": chunk_text, "tokens": 0}

            # Get final message for accurate token counts
            final_message = stream.get_final_message()
            tokens_in = final_message.usage.input_tokens
            tokens_out = final_message.usage.output_tokens

        full_text = "".join(full_text_parts)

        yield {
            "type": "final",
            "text": full_text,
            "model": model,
            "provider": "anthropic",
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": _calc_cost(model, tokens_in, tokens_out),
            "stop_reason": final_message.stop_reason if final_message else "unknown",
        }
