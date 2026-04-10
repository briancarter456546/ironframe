"""Tests for Component 17: Agent Trust & Identity."""
import pytest

from ironframe.agent_trust.tiers_v1_0 import (
    AutonomyTier, get_tier_permissions, is_action_allowed, tier_name,
)
from ironframe.agent_trust.identity_v1_0 import (
    IdentityProvider, TokenVerificationFailed,
)
from ironframe.coordination.messages_v1_0 import create_message, MessageType


def test_tier_assignment_returns_correct_permissions():
    perms = get_tier_permissions(AutonomyTier.OBSERVE)
    assert perms["read_kb"] is True
    assert perms["write_kb"] is False
    assert perms["tool_calls"] is False

    perms3 = get_tier_permissions(AutonomyTier.STANDARD)
    assert perms3["tool_calls"] is True
    assert perms3["external_tools"] is True
    assert perms3["canonical_write"] is False


def test_min_sender_receiver_logic():
    msg = create_message(
        sender_id="low",
        sender_trust_tier=1,
        receiver_id="high",
        message_type=MessageType.ASSIGNMENT.value,
    )
    assert msg.effective_tier_for_receiver(4) == 1
    assert msg.effective_tier_for_receiver(1) == 1


def test_trust_cannot_escalate_via_message():
    msg = create_message(
        sender_id="t2-agent",
        sender_trust_tier=2,
        receiver_id="t1-agent",
        message_type=MessageType.QUERY.value,
    )
    effective = msg.effective_tier_for_receiver(1)
    assert effective <= 1
    assert effective <= msg.sender_trust_tier


def test_unknown_tier_defaults_to_observe():
    perms = get_tier_permissions(999)
    assert perms == get_tier_permissions(AutonomyTier.OBSERVE)


def test_tier_name():
    assert tier_name(1) == "OBSERVE"
    assert tier_name(4) == "ELEVATED"
    assert "UNKNOWN" in tier_name(99)


def test_action_allowed_checks():
    assert is_action_allowed(AutonomyTier.OBSERVE, "read_kb") is True
    assert is_action_allowed(AutonomyTier.OBSERVE, "write_kb") is False
    assert is_action_allowed(AutonomyTier.LIMITED, "tool_call") is True
    assert is_action_allowed(AutonomyTier.LIMITED, "external_tool") is False
    assert is_action_allowed(AutonomyTier.ELEVATED, "canonical_write") is True


def test_identity_provider_issue_and_verify():
    provider = IdentityProvider(secret="test-secret-key")
    token = provider.issue_token(
        agent_type="worker",
        role="analyst",
        autonomy_tier=AutonomyTier.LIMITED,
    )
    assert token.autonomy_tier == 2
    assert token.verify("test-secret-key") is True
    verified = provider.verify_token(token)
    assert verified.session_id == token.session_id


def test_identity_provider_rejects_tampered_token():
    provider = IdentityProvider(secret="test-secret-key")
    token = provider.issue_token(
        agent_type="worker",
        role="analyst",
        autonomy_tier=AutonomyTier.LIMITED,
    )
    token.autonomy_tier = AutonomyTier.ELEVATED  # tamper
    assert token.verify("test-secret-key") is False


def test_elevated_requires_approver():
    provider = IdentityProvider(secret="test-secret-key")
    token = provider.issue_token(
        agent_type="worker",
        role="analyst",
        autonomy_tier=AutonomyTier.LIMITED,
    )
    with pytest.raises(TokenVerificationFailed):
        provider.elevate_tier(token.session_id, AutonomyTier.ELEVATED, approver="")
