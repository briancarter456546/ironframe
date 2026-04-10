# ============================================================================
# ironframe/coordination/protocol_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 14 Orchestrator: CoordinationProtocol
#
# Ties 14a-14f together. Manages multi-agent task decomposition,
# structured messaging, handoffs, loop detection, and resource coordination.
# ============================================================================

from typing import Any, Dict, List, Optional

from ironframe.coordination.roles_v1_0 import RoleRegistry, AgentRole, RoleViolation
from ironframe.coordination.messages_v1_0 import (
    AgentMessage, MessageType, MessageLog, create_message,
)
from ironframe.coordination.tasks_v1_0 import TaskGraph, SubTask, CircularDependency
from ironframe.coordination.handoff_v1_0 import HandoffProtocol, HandoffResult
from ironframe.coordination.loops_v1_0 import LoopDetector, LoopDetection
from ironframe.coordination.resources_v1_0 import ResourceCoordinator
from ironframe.tool_governance.locks_v1_0 import ResourceLockManager
from ironframe.audit.logger_v1_0 import AuditLogger


# Module-level conformance engine reference (C14->C18 wiring)
_conformance_engine = None


def register_conformance_engine(engine) -> None:
    """Register C18 ConformanceEngine to observe C14 coordination events."""
    global _conformance_engine
    _conformance_engine = engine


class CoordinationProtocol:
    """Component 14 orchestrator.

    Provides the structured coordination interface that replaces
    freeform natural-language agent coordination.
    """

    def __init__(
        self,
        lock_manager: Optional[ResourceLockManager] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        self._audit = audit_logger
        self._roles = RoleRegistry()
        self._messages = MessageLog()
        self._graph = TaskGraph()
        self._handoff = HandoffProtocol(self._graph, audit_logger)
        self._loops = LoopDetector()
        self._resources = ResourceCoordinator(
            lock_manager or ResourceLockManager(),
            self._graph,
        )

    # --- Properties ---

    @property
    def roles(self) -> RoleRegistry:
        return self._roles

    @property
    def graph(self) -> TaskGraph:
        return self._graph

    @property
    def messages(self) -> MessageLog:
        return self._messages

    @property
    def handoff(self) -> HandoffProtocol:
        return self._handoff

    @property
    def resources(self) -> ResourceCoordinator:
        return self._resources

    # --- Agent registration ---

    def register_agent(self, role: AgentRole) -> None:
        """Register an agent with declared role and capabilities."""
        self._roles.register(role)
        self._log("coordination.agent_registered", {
            "agent_id": role.agent_id,
            "agent_type": role.agent_type,
            "autonomy_tier": role.autonomy_tier,
        })

    # --- Task management ---

    def decompose(self, tasks: List[SubTask]) -> None:
        """Add sub-tasks to the decomposition graph.

        Raises CircularDependency if cycles detected.
        """
        for task in tasks:
            self._graph.add_task(task)
        self._graph.compute_all_priorities()
        self._log("coordination.task_decomposed", {
            "task_count": len(tasks),
            "task_ids": [t.task_id for t in tasks],
        })

    def assign_task(
        self,
        task_id: str,
        agent_id: str,
        orchestrator_id: str,
    ) -> AgentMessage:
        """Assign a sub-task to an agent. Returns the ASSIGNMENT message.

        Checks role compatibility. Detects repeated assignments (loops).
        """
        task = self._graph.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found in graph")

        role = self._roles.get(agent_id)
        if not role:
            raise ValueError(f"Agent '{agent_id}' not registered")

        # Check role compatibility
        if task.task_type and not role.can_handle(task.task_type):
            raise RoleViolation(agent_id, task.task_type, role.agent_type)

        # Check for repeated assignment (loop detection)
        loop = self._loops.observe_assignment(agent_id, task.description)
        if loop:
            self._handle_loop(loop, orchestrator_id)
            raise ValueError(f"Loop detected: {loop.detail}")

        # Assign
        self._graph.assign(task_id, agent_id)

        # Create structured ASSIGNMENT message
        msg = create_message(
            sender_id=orchestrator_id,
            sender_trust_tier=self._get_tier(orchestrator_id),
            receiver_id=agent_id,
            message_type=MessageType.ASSIGNMENT.value,
            payload={"task_id": task_id, "description": task.description,
                     "dependencies": task.dependencies},
        )
        self._messages.record(msg)

        self._log("coordination.task_assigned", {
            "task_id": task_id, "agent_id": agent_id,
            "orchestrator_id": orchestrator_id,
        })

        return msg

    def submit_result(
        self,
        task_id: str,
        agent_id: str,
        result: Dict[str, Any],
    ) -> AgentMessage:
        """Agent submits a result for orchestrator acknowledgment."""
        msg = create_message(
            sender_id=agent_id,
            sender_trust_tier=self._get_tier(agent_id),
            receiver_id="orchestrator",
            message_type=MessageType.RESULT.value,
            payload={"task_id": task_id, "result": result},
        )
        self._messages.record(msg)
        self._handoff.submit_result(msg)
        return msg

    def acknowledge_result(
        self,
        task_id: str,
        orchestrator_id: str,
        accept: bool = True,
        reason: str = "",
    ) -> HandoffResult:
        """Orchestrator acknowledges a sub-task result."""
        return self._handoff.acknowledge(task_id, orchestrator_id, accept, reason)

    # --- Messaging ---

    def send_message(self, message: AgentMessage) -> None:
        """Send a structured message between agents."""
        self._messages.record(message)

        # Loop detection on queries
        if message.message_type == MessageType.QUERY.value:
            loop = self._loops.observe_query(message.sender_id, message.receiver_id)
            if loop:
                self._handle_loop(loop, message.sender_id)

        self._log("coordination.message_sent", {
            "type": message.message_type,
            "sender": message.sender_id,
            "receiver": message.receiver_id,
        })

    # --- Resource access ---

    def request_resource(self, agent_id: str, task_id: str,
                          resource_id: str, session_id: str = ""):
        """Request shared resource access with graph-based priority."""
        return self._resources.request_resource(agent_id, task_id, resource_id, session_id)

    def release_resource(self, resource_id: str, session_id: str = ""):
        """Release resource and grant to next in priority queue."""
        return self._resources.release_and_grant_next(resource_id, session_id)

    # --- Loop handling ---

    def check_loops(self) -> List[LoopDetection]:
        """Run all loop detection checks."""
        active = [t.task_id for t in self._graph._tasks.values()
                  if t.status in ("assigned", "in_progress")]
        return self._loops.check_all(self._messages, active)

    def _handle_loop(self, detection: LoopDetection, initiator_id: str) -> None:
        """Handle a detected coordination loop: HALT + audit + escalate."""
        halt_msg = create_message(
            sender_id=initiator_id,
            sender_trust_tier=self._get_tier(initiator_id),
            receiver_id="BROADCAST",
            message_type=MessageType.HALT.value,
            payload={"loop_type": detection.loop_type, "detail": detection.detail},
        )
        self._messages.record(halt_msg)

        self._log("coordination.loop_detected", detection.to_dict())

    # --- Helpers ---

    def _get_tier(self, agent_id: str) -> int:
        role = self._roles.get(agent_id)
        return role.autonomy_tier if role else 1

    def _log(self, event_type: str, details: Dict[str, Any]) -> None:
        if self._audit:
            try:
                self._audit.log_event(
                    event_type=event_type,
                    component="coordination.protocol",
                    details=details,
                )
            except Exception:
                pass

        # C14->C18 wiring: feed trace event to conformance engine
        if _conformance_engine is not None:
            try:
                trace_event = {
                    "event_type": event_type.split(".")[-1] if "." in event_type else event_type,
                    "component_id": "C14",
                    "audit_logged": self._audit is not None,
                }
                trace_event.update(details)
                _conformance_engine.observe_event(trace_event)
            except Exception:
                pass  # C18 observation must never break C14 operation

    def summary(self) -> Dict[str, Any]:
        return {
            "agents": self._roles.summary(),
            "tasks": self._graph.summary(),
            "messages": self._messages.count(),
            "pending_handoffs": self._handoff.pending_count(),
            "resource_queues": self._resources.summary(),
        }
