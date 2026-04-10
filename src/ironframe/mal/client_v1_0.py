# ============================================================================
# ironframe/mal/client_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# IronFrameClient - unified interface for all model calls.
#
# Every call auto-routes by capability preference, enforces budget caps,
# and logs to the immutable audit trail. Supports both sync and streaming.
#
# Usage:
#   from ironframe.mal import get_client
#   client = get_client()  # uses IronFrameConfig.from_env()
#   result = client.complete('What is 2+2?', preference='fast')
#   # result = {'text': '4', 'model': '...', 'cost_usd': 0.0001, ...}
#
#   for chunk in client.stream('Tell me a story', preference='smart'):
#       print(chunk['text'], end='')
# ============================================================================

import uuid
from typing import Any, Dict, Generator, Optional

from ironframe.config_v1_0 import IronFrameConfig
from ironframe.mal.budget_v1_0 import BudgetTracker
from ironframe.mal.router_v1_0 import ModelRouter
from ironframe.audit.logger_v1_0 import AuditLogger
from ironframe.audit.stream_logger_v1_0 import StreamAuditLogger


def _load_adapter(provider: str, api_key: str):
    """Lazy-load the appropriate provider adapter."""
    if provider == "anthropic":
        from ironframe.mal.adapters.anthropic_v1_0 import AnthropicAdapter
        return AnthropicAdapter(api_key=api_key)
    elif provider == "perplexity":
        from ironframe.mal.adapters.perplexity_v1_0 import PerplexityAdapter
        return PerplexityAdapter(api_key=api_key)
    elif provider == "openai":
        # OpenAI adapter not yet built -- use Perplexity adapter pattern as reference
        raise NotImplementedError(
            f"Adapter for 'openai' not yet implemented."
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


class IronFrameClient:
    """Unified interface for all Iron Frame model calls.

    Ties together: config, router, budget, adapters, and audit logging.
    One client per session (shares budget and audit state).
    """

    def __init__(
        self,
        config: Optional[IronFrameConfig] = None,
        session_id: str = "",
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._config = config or IronFrameConfig.from_env()
        self._session_id = session_id or str(uuid.uuid4())[:8]
        self._budget = BudgetTracker(**self._config.budget)
        self._router = ModelRouter(self._config, self._budget)
        self._audit = audit_logger or AuditLogger(
            output_dir=str(self._config.get_audit_dir())
        )
        self._adapter_cache: Dict[str, Any] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def budget(self) -> BudgetTracker:
        return self._budget

    @property
    def audit_logger(self) -> AuditLogger:
        return self._audit

    def _get_adapter(self, provider: str, api_key: str):
        """Get or create a cached adapter for a provider."""
        if provider not in self._adapter_cache:
            self._adapter_cache[provider] = _load_adapter(provider, api_key)
        return self._adapter_cache[provider]

    def complete(
        self,
        prompt: str,
        system: str = "",
        preference: str = "smart",
        max_tokens: int = 1024,
        temperature: float = 1.0,
    ) -> Dict[str, Any]:
        """Synchronous completion with auto-routing, budget, and audit.

        Write-before-release: the audit log is written before the result
        is returned to the caller.
        """
        # Route to concrete model
        route = self._router.resolve(preference, max_tokens)
        provider = route["provider"]
        model = route["model"]
        api_key = route["api_key"]

        # Get adapter and call
        adapter = self._get_adapter(provider, api_key)
        result = adapter.complete(
            prompt=prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        # Record actual cost
        self._router.record_cost(result.get("cost_usd", 0.0))

        # Audit log (write-before-release)
        self._audit.log_event(
            event_type="model_call",
            component="mal.client",
            session_id=self._session_id,
            input_text=prompt,
            output_summary=result.get("text", "")[:500],
            output_text=result.get("text", ""),
            model_id=result.get("model", model),
            provider=provider,
            tokens_in=result.get("tokens_in", 0),
            tokens_out=result.get("tokens_out", 0),
            cost_usd=result.get("cost_usd", 0.0),
        )

        # Add routing metadata to result
        result["preference"] = preference
        result["session_id"] = self._session_id
        return result

    def stream(
        self,
        prompt: str,
        system: str = "",
        preference: str = "smart",
        max_tokens: int = 1024,
        temperature: float = 1.0,
    ) -> Generator[Dict[str, Any], None, None]:
        """Streaming completion with auto-routing, budget, and audit.

        Uses open/close audit pattern:
        - stream_open logged before first chunk
        - chunks yielded to caller
        - stream_close logged after final chunk (or stream_error on failure)

        Yields chunk dicts: {type: 'chunk', text: '...'}
        Final yield: {type: 'final', text: '...', cost_usd: ..., ...}
        """
        # Route to concrete model
        route = self._router.resolve(preference, max_tokens)
        provider = route["provider"]
        model = route["model"]
        api_key = route["api_key"]

        # Set up stream audit logger
        stream_audit = StreamAuditLogger(
            self._audit,
            session_id=self._session_id,
            component="mal.client",
        )

        # Open audit entry
        stream_audit.open(
            model_id=model,
            provider=provider,
            input_text=prompt,
        )

        # Get adapter and stream
        adapter = self._get_adapter(provider, api_key)
        try:
            final_result = None
            for item in adapter.stream(
                prompt=prompt,
                system=system,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                if item.get("type") == "chunk":
                    stream_audit.accumulate(item.get("text", ""))
                    yield item
                elif item.get("type") == "final":
                    final_result = item

            # Close audit entry with final stats
            if final_result:
                cost = final_result.get("cost_usd", 0.0)
                self._router.record_cost(cost)
                stream_audit.close(
                    cost_usd=cost,
                    tokens_out_override=final_result.get("tokens_out"),
                )
                final_result["preference"] = preference
                final_result["session_id"] = self._session_id
                yield final_result
            else:
                stream_audit.close()

        except Exception as exc:
            stream_audit.close_with_error(str(exc), type(exc).__name__)
            raise
