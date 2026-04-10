# ============================================================================
# ironframe/coordination/handoff_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 14d: Handoff & Result Protocol
#
# When a sub-task completes:
#   1. Agent writes a typed RESULT message with provenance
#   2. Orchestrator validates result schema before accepting
#   3. Result written to session state with agent identity
#   4. Orchestrator decides: pass downstream or escalate
#
# Self-completion without orchestrator acknowledgment = coordination anomaly.
# ============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ironframe.coordination.messages_v1_0 import AgentMessage, MessageType, create_message
from ironframe.coordination.tasks_v1_0 import TaskGraph, SubTask


@dataclass
class HandoffResult:
    """Result of a handoff attempt."""
    accepted: bool
    task_id: str
    agent_id: str
    reason: str = ""
    downstream_task_ids: List[str] = field(default_factory=list)


class HandoffProtocol:
    """Manages sub-task completion handoffs with orchestrator acknowledgment."""

    def __init__(self, task_graph: TaskGraph, audit_logger=None):
        self._graph = task_graph
        self._audit = audit_logger
        self._pending_results: Dict[str, AgentMessage] = {}  # task_id -> RESULT message

    def submit_result(self, result_message: AgentMessage) -> None:
        """Agent submits a RESULT message. Awaits orchestrator acknowledgment.

        Self-completion without this path = anomaly.
        """
        task_id = result_message.payload.get("task_id", "")
        if not task_id:
            return
        self._pending_results[task_id] = result_message

    def acknowledge(
        self,
        task_id: str,
        orchestrator_id: str,
        accept: bool = True,
        reason: str = "",
    ) -> HandoffResult:
        """Orchestrator acknowledges a result. Only then is the task truly complete.

        accept=True: task marked complete, dependents unblocked.
        accept=False: task remains in progress, agent may retry.
        """
        result_msg = self._pending_results.pop(task_id, None)
        task = self._graph.get_task(task_id)

        if not task:
            return HandoffResult(accepted=False, task_id=task_id,
                                 agent_id="", reason="Task not found")

        if not result_msg:
            return HandoffResult(accepted=False, task_id=task_id,
                                 agent_id=task.owner_agent_id,
                                 reason="No pending result to acknowledge")

        if accept:
            self._graph.complete(task_id, result_msg.payload.get("result", {}))
            # Find newly ready downstream tasks
            downstream = [t.task_id for t in self._graph.ready_tasks()
                          if task_id in t.dependencies]
            self._log_handoff("accepted", task_id, task.owner_agent_id, orchestrator_id)
            return HandoffResult(
                accepted=True, task_id=task_id,
                agent_id=task.owner_agent_id,
                downstream_task_ids=downstream,
            )
        else:
            # Rejected — task stays in progress for retry
            self._log_handoff("rejected", task_id, task.owner_agent_id,
                              orchestrator_id, reason)
            return HandoffResult(
                accepted=False, task_id=task_id,
                agent_id=task.owner_agent_id, reason=reason,
            )

    def pending_count(self) -> int:
        return len(self._pending_results)

    def pending_tasks(self) -> List[str]:
        return list(self._pending_results.keys())

    def _log_handoff(self, outcome: str, task_id: str, agent_id: str,
                     orchestrator_id: str, reason: str = "") -> None:
        if not self._audit:
            return
        try:
            self._audit.log_event(
                event_type=f"coordination.handoff.{outcome}",
                component="coordination.handoff",
                details={
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "orchestrator_id": orchestrator_id,
                    "reason": reason,
                },
            )
        except Exception:
            pass
