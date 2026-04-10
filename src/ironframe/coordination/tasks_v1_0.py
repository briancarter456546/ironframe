# ============================================================================
# ironframe/coordination/tasks_v1_0.py - v1.0
# Last updated: 2026-04-07
# ============================================================================
# Component 14c: Task Decomposition Graph
#
# Orchestrators decompose tasks into sub-tasks with explicit dependencies.
# Circular dependencies detected at decomposition time (topological sort).
# Orchestrator holds the graph; agents see only their assignments.
# ============================================================================

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


# Sub-task statuses
PENDING = "pending"
ASSIGNED = "assigned"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
FAILED = "failed"
BLOCKED = "blocked"


class CircularDependency(Exception):
    """Raised when task graph contains circular dependencies."""
    def __init__(self, cycle: List[str]):
        self.cycle = cycle
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle)}")


@dataclass
class SubTask:
    """A single sub-task in a decomposition graph."""
    task_id: str
    parent_task_id: str = ""
    owner_agent_id: str = ""
    description: str = ""
    task_type: str = ""
    dependencies: List[str] = field(default_factory=list)  # task_ids that must complete first
    status: str = PENDING
    completion_criterion: str = ""
    priority: int = 0              # from graph position (critical path = highest)
    assigned_at: str = ""
    completed_at: str = ""
    result: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.status == COMPLETED

    @property
    def is_blocked(self) -> bool:
        return self.status == BLOCKED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "owner_agent_id": self.owner_agent_id,
            "description": self.description[:80],
            "status": self.status,
            "priority": self.priority,
            "dependencies": self.dependencies,
        }


class TaskGraph:
    """Directed acyclic graph of sub-tasks with dependency management.

    Detects circular dependencies at add time. Computes critical path
    for resource priority (Brian's flag #2).
    """

    def __init__(self, root_task_id: str = ""):
        self._root = root_task_id or str(uuid.uuid4())[:8]
        self._tasks: Dict[str, SubTask] = {}

    @property
    def root_task_id(self) -> str:
        return self._root

    def add_task(self, task: SubTask) -> None:
        """Add a sub-task. Detects circular dependencies."""
        self._tasks[task.task_id] = task
        # Validate no cycles
        try:
            self._topological_sort()
        except CircularDependency:
            del self._tasks[task.task_id]
            raise

    def get_task(self, task_id: str) -> Optional[SubTask]:
        return self._tasks.get(task_id)

    def assign(self, task_id: str, agent_id: str) -> bool:
        """Assign a task to an agent."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.owner_agent_id = agent_id
        task.status = ASSIGNED
        task.assigned_at = datetime.now(timezone.utc).isoformat()
        return True

    def start(self, task_id: str) -> bool:
        """Mark a task as in progress."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = IN_PROGRESS
        return True

    def complete(self, task_id: str, result: Optional[Dict] = None) -> bool:
        """Mark a task as completed. Does NOT mean acknowledged by orchestrator."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = COMPLETED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.result = result or {}
        # Unblock dependents
        self._update_blocked()
        return True

    def fail(self, task_id: str, reason: str = "") -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = FAILED
        task.result = {"failure_reason": reason}
        return True

    def ready_tasks(self) -> List[SubTask]:
        """Tasks whose dependencies are all complete and are pending/assigned."""
        ready = []
        for task in self._tasks.values():
            if task.status not in (PENDING, ASSIGNED):
                continue
            deps_met = all(
                self._tasks.get(dep_id) and self._tasks[dep_id].is_complete
                for dep_id in task.dependencies
            )
            if deps_met:
                ready.append(task)
        return ready

    def get_for_agent(self, agent_id: str) -> List[SubTask]:
        """Get tasks assigned to a specific agent."""
        return [t for t in self._tasks.values() if t.owner_agent_id == agent_id]

    def is_all_complete(self) -> bool:
        return all(t.is_complete for t in self._tasks.values())

    def critical_path_priority(self, task_id: str) -> int:
        """Compute priority based on position in dependency graph.

        Tasks with more dependents (further from leaves) get higher priority.
        Used by resources_v1_0.py for lock priority (Brian's flag #2).
        """
        dependent_count = sum(
            1 for t in self._tasks.values() if task_id in t.dependencies
        )
        # Also count transitive dependents
        transitive = self._count_transitive_dependents(task_id)
        return dependent_count + transitive

    def compute_all_priorities(self) -> None:
        """Compute and assign priority to all tasks based on critical path."""
        for task in self._tasks.values():
            task.priority = self.critical_path_priority(task.task_id)

    def _count_transitive_dependents(self, task_id: str, visited: Optional[Set] = None) -> int:
        if visited is None:
            visited = set()
        count = 0
        for t in self._tasks.values():
            if task_id in t.dependencies and t.task_id not in visited:
                visited.add(t.task_id)
                count += 1
                count += self._count_transitive_dependents(t.task_id, visited)
        return count

    def _topological_sort(self) -> List[str]:
        """Topological sort to detect cycles."""
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        order: List[str] = []

        def visit(task_id: str) -> None:
            if task_id in in_stack:
                # Find the cycle
                raise CircularDependency([task_id])
            if task_id in visited:
                return
            in_stack.add(task_id)
            task = self._tasks.get(task_id)
            if task:
                for dep in task.dependencies:
                    if dep in self._tasks:
                        visit(dep)
            in_stack.discard(task_id)
            visited.add(task_id)
            order.append(task_id)

        for tid in self._tasks:
            visit(tid)
        return order

    def _update_blocked(self) -> None:
        """Update blocked status for tasks whose deps are now met."""
        for task in self._tasks.values():
            if task.status == BLOCKED:
                deps_met = all(
                    self._tasks.get(d) and self._tasks[d].is_complete
                    for d in task.dependencies
                )
                if deps_met:
                    task.status = PENDING

    def summary(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for t in self._tasks.values():
            by_status[t.status] = by_status.get(t.status, 0) + 1
        return {
            "total_tasks": len(self._tasks),
            "by_status": by_status,
            "all_complete": self.is_all_complete(),
        }
