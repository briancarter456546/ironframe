# ============================================================================
# ironframe/coordination/messages_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 14b: Structured Message Protocol
#
# All inter-agent messages use a typed schema (C16-validated).
# Freeform natural language is NOT valid for operational coordination.
#
# Trust propagation (Brian's flag #1): receiving agent's effective
# permissions = min(own_tier, sender_tier). No trust escalation.
# ============================================================================

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageType(str, Enum):
    ASSIGNMENT = "ASSIGNMENT"
    RESULT = "RESULT"
    QUERY = "QUERY"
    ESCALATION = "ESCALATION"
    HEARTBEAT = "HEARTBEAT"
    HALT = "HALT"
    RESOURCE_QUEUED = "RESOURCE_QUEUED"


@dataclass
class AgentMessage:
    """Structured inter-agent message. C16-schema-validated envelope.

    Trust propagation: effective_tier_for_receiver() returns
    min(receiver_tier, sender_tier). A T2 sender to a T3 receiver
    means T3 processes the message with T2 permissions.
    """
    message_id: str
    session_id: str
    sender_id: str
    sender_trust_tier: int          # from sender's C17 OutputProvenance
    receiver_id: str                # agent ID or "BROADCAST"
    message_type: str               # MessageType value
    payload: Dict[str, Any] = field(default_factory=dict)
    payload_schema: str = ""        # C16 schema ID for payload validation
    provenance: Dict[str, Any] = field(default_factory=dict)  # C17 OutputProvenance.to_dict()
    timestamp: str = ""

    def __post_init__(self):
        if not self.message_id:
            self.message_id = str(uuid.uuid4())[:12]
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def effective_tier_for_receiver(self, receiver_tier: int) -> int:
        """Receiver's effective permissions = min(own, sender).

        Brian's flag #1: NO trust escalation through messaging.
        A T2 message arriving at a T3 agent = T3 processes at T2 level.
        """
        return min(receiver_tier, self.sender_trust_tier)

    @property
    def is_broadcast(self) -> bool:
        return self.receiver_id == "BROADCAST"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "sender_id": self.sender_id,
            "sender_trust_tier": self.sender_trust_tier,
            "receiver_id": self.receiver_id,
            "message_type": self.message_type,
            "payload_schema": self.payload_schema,
            "timestamp": self.timestamp,
        }


def create_message(
    sender_id: str,
    sender_trust_tier: int,
    receiver_id: str,
    message_type: str,
    session_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
    provenance: Optional[Dict[str, Any]] = None,
) -> AgentMessage:
    """Factory for creating structured agent messages."""
    return AgentMessage(
        message_id=str(uuid.uuid4())[:12],
        session_id=session_id,
        sender_id=sender_id,
        sender_trust_tier=sender_trust_tier,
        receiver_id=receiver_id,
        message_type=message_type,
        payload=payload or {},
        provenance=provenance or {},
    )


class MessageLog:
    """Ordered log of all coordination messages in a session."""

    def __init__(self):
        self._messages: List[AgentMessage] = []

    def record(self, message: AgentMessage) -> None:
        self._messages.append(message)

    def get_for_agent(self, agent_id: str) -> List[AgentMessage]:
        """Get messages sent to or from an agent."""
        return [m for m in self._messages
                if m.sender_id == agent_id or m.receiver_id == agent_id
                or m.is_broadcast]

    def get_by_type(self, message_type: str) -> List[AgentMessage]:
        return [m for m in self._messages if m.message_type == message_type]

    def count(self) -> int:
        return len(self._messages)

    def count_by_sender(self, sender_id: str, message_type: str = "") -> int:
        """Count messages from a sender, optionally filtered by type."""
        msgs = [m for m in self._messages if m.sender_id == sender_id]
        if message_type:
            msgs = [m for m in msgs if m.message_type == message_type]
        return len(msgs)
