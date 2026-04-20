"""Tests for ironframe.mal.response_v1_0.IronFrameResponse.

Wrapper around IronFrameClient.complete() return shape. Must support:
  1. Attribute access for README-facing ergonomic API (.content, .cost, ...)
  2. Dict access for backward compatibility with every existing consumer
     that uses .get() / [] / in / json.dumps / ** / isinstance checks
  3. to_dict() round-trip that decouples the caller's mutations from the
     response object's underlying storage
"""
from __future__ import annotations

import json

import pytest

from ironframe.mal.response_v1_0 import IronFrameResponse


SAMPLE_RAW = {
    "text": "hi",
    "model": "claude-haiku-4-5",
    "provider": "anthropic",
    "tokens_in": 5,
    "tokens_out": 2,
    "cost_usd": 0.0003,
    "stop_reason": "end_turn",
    "preference": "fast",
    "session_id": "sess-42",
}


# ---------------------------------------------------------------------------
# 1. Attribute access -- README-facing ergonomic API
# ---------------------------------------------------------------------------

class TestAttributeAccess:
    def test_text_and_content_alias(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.text == "hi"
        assert r.content == "hi"  # README alias
        assert r.text == r.content

    def test_cost_and_cost_usd_alias(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.cost_usd == 0.0003
        assert r.cost == 0.0003  # README alias
        assert r.cost == r.cost_usd

    def test_model_and_model_id_alias(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.model == "claude-haiku-4-5"
        assert r.model_id == "claude-haiku-4-5"  # alias

    def test_all_canonical_schema_fields(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.provider == "anthropic"
        assert r.tokens_in == 5
        assert r.tokens_out == 2
        assert r.stop_reason == "end_turn"
        assert r.preference == "fast"
        assert r.session_id == "sess-42"

    def test_confidence_defaults_to_none(self):
        """SAE computes confidence separately; MAL does not populate it."""
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.confidence is None

    def test_confidence_returned_when_sae_populated(self):
        """If a verify step later adds confidence, the attribute surfaces it."""
        raw = dict(SAMPLE_RAW)
        raw["confidence"] = 0.87
        r = IronFrameResponse(raw)
        assert r.confidence == 0.87

    def test_attribute_access_safe_on_missing_optional_fields(self):
        """stop_reason/preference/session_id are optional in some adapters."""
        r = IronFrameResponse({"text": "ok", "model": "m", "provider": "p",
                               "cost_usd": 0.0})
        assert r.stop_reason is None
        assert r.preference is None
        assert r.session_id is None
        assert r.tokens_in == 0
        assert r.tokens_out == 0


# ---------------------------------------------------------------------------
# 2. Dict backward-compat -- every pre-0.1.1 consumer keeps working
# ---------------------------------------------------------------------------

class TestDictBackwardCompat:
    def test_bracket_access(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r["text"] == "hi"
        assert r["cost_usd"] == 0.0003

    def test_get_with_default(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.get("text", "") == "hi"
        assert r.get("missing_key", "fallback") == "fallback"

    def test_in_operator(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert "text" in r
        assert "cost_usd" in r
        assert "nonexistent" not in r

    def test_keys_and_items_and_values(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert set(r.keys()) == set(SAMPLE_RAW.keys())
        assert dict(r.items()) == SAMPLE_RAW
        assert set(r.values()) == set(SAMPLE_RAW.values())

    def test_isinstance_dict_true(self):
        """eval/methods_v1_0.py:20 branches on isinstance(output, dict)."""
        r = IronFrameResponse(SAMPLE_RAW)
        assert isinstance(r, dict)

    def test_json_dumps_serializable(self):
        """If any consumer does json.dumps(response), it must still work."""
        r = IronFrameResponse(SAMPLE_RAW)
        serialised = json.loads(json.dumps(r))
        assert serialised == SAMPLE_RAW

    def test_double_star_unpack(self):
        """Supports **response unpacking pattern."""
        r = IronFrameResponse(SAMPLE_RAW)
        def accept_kwargs(**kwargs):
            return kwargs
        result = accept_kwargs(**r)
        assert result == SAMPLE_RAW


# ---------------------------------------------------------------------------
# 3. to_dict round-trip
# ---------------------------------------------------------------------------

class TestToDictRoundtrip:
    def test_to_dict_returns_equal_dict(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.to_dict() == SAMPLE_RAW

    def test_raw_returns_equal_dict(self):
        r = IronFrameResponse(SAMPLE_RAW)
        assert r.raw == SAMPLE_RAW

    def test_mutating_to_dict_copy_does_not_mutate_response(self):
        """Round-trip must be a copy, not a reference."""
        r = IronFrameResponse(SAMPLE_RAW)
        copy = r.to_dict()
        copy["text"] = "mutated"
        assert r["text"] == "hi"  # original unchanged
        assert r.content == "hi"  # attribute access unchanged
        assert r.to_dict()["text"] == "hi"  # new snapshot still clean

    def test_repr_is_informative(self):
        r = IronFrameResponse(SAMPLE_RAW)
        s = repr(r)
        assert "IronFrameResponse" in s
        assert "claude-haiku-4-5" in s
        assert "0.0003" in s
        # text preview included
        assert "hi" in s
