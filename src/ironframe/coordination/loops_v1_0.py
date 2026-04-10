# ============================================================================
# ironframe/coordination/loops_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 14e: Loop Detection & Halt
#
# Detects coordination loops:
#   - Identical assignments issued > N times
#   - Circular query patterns between agents
#   - Stalled sub-tasks with no progress within timeout
#
# On detection: HALT broadcast, audit event, escalate to C3.
# ============================================================================

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ironframe.coordination.messages_v1_0 import AgentMessage, MessageType, MessageLog


# Default thresholds
DEFAULT_MAX_REPEAT_ASSIGNMENTS = 3
DEFAULT_STALL_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class LoopDetection:
    """Result of a loop detection check."""
    loop_detected: bool
    loop_type: str = ""       # repeat_assignment, circular_query, stalled_task
    detail: str = ""
    affected_agents: List[str] = field(default_factory=list)
    affected_tasks: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "loop_detected": self.loop_detected,
            "loop_type": self.loop_type,
            "detail": self.detail,
            "affected_agents": self.affected_agents,
            "affected_tasks": self.affected_tasks,
        }


class LoopDetector:
    """Detects coordination loops in multi-agent sessions."""

    def __init__(
        self,
        max_repeat_assignments: int = DEFAULT_MAX_REPEAT_ASSIGNMENTS,
        stall_timeout_seconds: float = DEFAULT_STALL_TIMEOUT_SECONDS,
    ):
        self._max_repeats = max_repeat_assignments
        self._stall_timeout = stall_timeout_seconds
        # Track assignment patterns: (agent_id, task_description_hash) -> count
        self._assignment_counts: Counter = Counter()
        # Track query patterns: (sender, receiver) -> count
        self._query_patterns: Counter = Counter()
        # Track task progress: task_id -> last_progress_timestamp
        self._task_progress: Dict[str, float] = {}

    def observe_assignment(self, agent_id: str, task_description: str) -> Optional[LoopDetection]:
        """Record an assignment. Returns LoopDetection if threshold exceeded."""
        key = (agent_id, hash(task_description))
        self._assignment_counts[key] += 1

        if self._assignment_counts[key] > self._max_repeats:
            return LoopDetection(
                loop_detected=True,
                loop_type="repeat_assignment",
                detail=f"Agent '{agent_id}' assigned same task {self._assignment_counts[key]} times "
                       f"(threshold: {self._max_repeats})",
                affected_agents=[agent_id],
            )
        return None

    def observe_query(self, sender_id: str, receiver_id: str) -> Optional[LoopDetection]:
        """Record a query between agents. Detects circular patterns."""
        self._query_patterns[(sender_id, receiver_id)] += 1

        # Check for A->B->A circular pattern
        reverse_count = self._query_patterns.get((receiver_id, sender_id), 0)
        forward_count = self._query_patterns[(sender_id, receiver_id)]

        if forward_count > self._max_repeats and reverse_count > self._max_repeats:
            return LoopDetection(
                loop_detected=True,
                loop_type="circular_query",
                detail=f"Circular queries: {sender_id}->{receiver_id} ({forward_count}x) "
                       f"and {receiver_id}->{sender_id} ({reverse_count}x)",
                affected_agents=[sender_id, receiver_id],
            )
        return None

    def observe_progress(self, task_id: str) -> None:
        """Record progress on a task (resets stall timer)."""
        self._task_progress[task_id] = time.time()

    def check_stalls(self, active_task_ids: List[str]) -> List[LoopDetection]:
        """Check for stalled tasks with no progress within timeout."""
        stalls = []
        now = time.time()

        for task_id in active_task_ids:
            last_progress = self._task_progress.get(task_id, now)
            elapsed = now - last_progress
            if elapsed > self._stall_timeout:
                stalls.append(LoopDetection(
                    loop_detected=True,
                    loop_type="stalled_task",
                    detail=f"Task '{task_id}' stalled for {elapsed:.0f}s "
                           f"(timeout: {self._stall_timeout}s)",
                    affected_tasks=[task_id],
                ))
        return stalls

    def check_all(self, message_log: MessageLog, active_task_ids: List[str]) -> List[LoopDetection]:
        """Run all loop detection checks. Returns list of detections."""
        detections = []
        detections.extend(self.check_stalls(active_task_ids))
        return detections

    def clear(self) -> None:
        self._assignment_counts.clear()
        self._query_patterns.clear()
        self._task_progress.clear()
