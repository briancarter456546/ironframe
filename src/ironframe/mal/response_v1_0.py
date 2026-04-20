# ============================================================================
# ironframe/mal/response_v1_0.py - v1.0
# Last updated: 2026-04-19
# ============================================================================
# IronFrameResponse -- the return type of IronFrameClient.complete().
#
# Inherits from dict for full backward compatibility: existing code using
# isinstance(r, dict), json.dumps(r), **r unpacking, r['text'], r.get('model')
# continues to work unchanged. Adds attribute access (r.content, r.cost,
# r.model, r.confidence) so the README quickstart pattern is correct:
#
#     response = client.complete(prompt="...", preference="smart")
#     print(response.content)
#     print(f"Cost: ${response.cost:.4f}")
#
# Attribute aliases (README-facing on the left, canonical schema key on the
# right):
#   .content  -> text
#   .cost     -> cost_usd
#   .confidence returns None unless a separate SAE verify() has populated it.
# ============================================================================

from __future__ import annotations

from typing import Any, Optional


class IronFrameResponse(dict):
    """Response object from IronFrameClient.complete().

    Subclasses dict so every pre-0.1.1 consumer (dict access, json.dumps,
    **unpacking, isinstance checks) keeps working. Attribute properties
    added for ergonomic README-style access.
    """

    # --- Canonical schema fields (match mal.complete.output_v1.0.json) ---

    @property
    def text(self) -> str:
        return self.get("text", "") or ""

    @property
    def model(self) -> str:
        return self.get("model", "") or ""

    @property
    def model_id(self) -> str:
        """Alias for .model to match naming in some consumer code paths."""
        return self.get("model", "") or ""

    @property
    def provider(self) -> str:
        return self.get("provider", "") or ""

    @property
    def tokens_in(self) -> int:
        return int(self.get("tokens_in", 0) or 0)

    @property
    def tokens_out(self) -> int:
        return int(self.get("tokens_out", 0) or 0)

    @property
    def cost_usd(self) -> float:
        return float(self.get("cost_usd", 0.0) or 0.0)

    @property
    def stop_reason(self) -> Optional[str]:
        return self.get("stop_reason")

    @property
    def preference(self) -> Optional[str]:
        return self.get("preference")

    @property
    def session_id(self) -> Optional[str]:
        return self.get("session_id")

    # --- README-facing aliases ---

    @property
    def content(self) -> str:
        """Alias for .text. Matches README quickstart."""
        return self.text

    @property
    def cost(self) -> float:
        """Alias for .cost_usd. Matches README quickstart."""
        return self.cost_usd

    @property
    def confidence(self) -> Optional[float]:
        """Confidence score for this response.

        None by default. MAL does not compute confidence -- that is the
        Self-Audit Engine's responsibility. To score a response, run it
        through TierRouter.verify() or sae.judge_v1_0.Judge.evaluate().
        """
        return self.get("confidence")

    # --- Helpers ---

    @property
    def raw(self) -> dict:
        """Return a plain-dict copy (without IronFrameResponse wrapper)."""
        return dict(self)

    def to_dict(self) -> dict:
        """Return a plain-dict copy. Alias for .raw for symmetry with to_json."""
        return dict(self)

    def __repr__(self) -> str:
        text_preview = self.text[:60] + ("..." if len(self.text) > 60 else "")
        return (
            f"IronFrameResponse(model={self.model!r}, "
            f"cost_usd={self.cost_usd}, "
            f"tokens_out={self.tokens_out}, "
            f"text={text_preview!r})"
        )
