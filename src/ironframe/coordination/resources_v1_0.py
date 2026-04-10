# ============================================================================
# ironframe/coordination/resources_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 14f: Shared Resource Coordination
#
# Brian's flag #2: two agents wanting same tool get serialized via C12's
# lock manager using task dependency graph priority, NOT "first wins."
#
# Priority order:
#   1. Critical path position (higher = more dependents waiting)
#   2. Assignment timestamp (earlier = higher priority on tie)
# ============================================================================

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ironframe.coordination.tasks_v1_0 import TaskGraph
from ironframe.tool_governance.locks_v1_0 import ResourceLockManager, LockConflict, LockInfo


@dataclass
class ResourceRequest:
    """A queued resource access request from an agent."""
    agent_id: str
    task_id: str
    resource_id: str
    priority: int              # from task graph critical path
    requested_at: str = ""
    status: str = "queued"     # queued, granted, denied

    def __post_init__(self):
        if not self.requested_at:
            self.requested_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "resource_id": self.resource_id,
            "priority": self.priority,
            "status": self.status,
        }


class ResourceCoordinator:
    """Coordinates shared resource access between agents.

    Uses C12's ResourceLockManager for actual locking.
    Priority determined by task dependency graph position.
    """

    def __init__(self, lock_manager: ResourceLockManager, task_graph: TaskGraph):
        self._locks = lock_manager
        self._graph = task_graph
        self._queues: Dict[str, List[ResourceRequest]] = {}  # resource_id -> sorted queue

    def request_resource(
        self,
        agent_id: str,
        task_id: str,
        resource_id: str,
        session_id: str = "",
    ) -> Tuple[bool, Optional[LockInfo], str]:
        """Request access to a shared resource.

        Returns (granted, lock_info, message).
        If not granted: request is queued by priority.
        """
        # Compute priority from task graph
        priority = self._graph.critical_path_priority(task_id)

        request = ResourceRequest(
            agent_id=agent_id,
            task_id=task_id,
            resource_id=resource_id,
            priority=priority,
        )

        # Try to acquire lock
        try:
            lock = self._locks.acquire(
                resource_id=resource_id,
                owner_session_id=session_id or agent_id,
                owner_call_id=f"{agent_id}:{task_id}",
            )
            request.status = "granted"
            return True, lock, "Resource acquired"

        except LockConflict:
            # Check if requestor has higher priority than current holder
            current_lock = self._locks.get_lock(resource_id)
            if current_lock:
                current_task_id = current_lock.owner_call_id.split(":")[-1] if ":" in current_lock.owner_call_id else ""
                current_priority = self._graph.critical_path_priority(current_task_id) if current_task_id else 0

                if priority > current_priority:
                    # Higher priority — queue but flag for preemption consideration
                    request.status = "queued"
                    self._enqueue(request)
                    return False, None, (
                        f"Resource locked by {current_lock.owner_call_id} "
                        f"(priority {current_priority}). Your priority: {priority}. Queued."
                    )

            # Lower or equal priority — queue
            request.status = "queued"
            self._enqueue(request)
            return False, None, f"Resource '{resource_id}' busy. Queued at priority {priority}."

    def release_and_grant_next(self, resource_id: str, session_id: str = "") -> Optional[ResourceRequest]:
        """Release a resource and grant to the highest-priority queued request.

        Returns the next request to be granted, if any.
        """
        self._locks.release_resource(resource_id)

        queue = self._queues.get(resource_id, [])
        if not queue:
            return None

        # Grant to highest priority (already sorted)
        next_request = queue.pop(0)
        next_request.status = "granted"

        if not queue:
            del self._queues[resource_id]

        return next_request

    def get_queue(self, resource_id: str) -> List[ResourceRequest]:
        """Get the current queue for a resource."""
        return list(self._queues.get(resource_id, []))

    def queue_length(self, resource_id: str) -> int:
        return len(self._queues.get(resource_id, []))

    def _enqueue(self, request: ResourceRequest) -> None:
        """Add request to queue, sorted by priority (highest first), then timestamp."""
        if request.resource_id not in self._queues:
            self._queues[request.resource_id] = []
        self._queues[request.resource_id].append(request)
        self._queues[request.resource_id].sort(
            key=lambda r: (-r.priority, r.requested_at)
        )

    def summary(self) -> Dict[str, Any]:
        return {
            "queued_resources": len(self._queues),
            "total_queued_requests": sum(len(q) for q in self._queues.values()),
        }
