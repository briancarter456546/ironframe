# ============================================================================
# ironframe/tool_governance/locks_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 12d: Resource Locks
#
# Lock acquisition/release for tools operating on shared resources.
# Correction #5: full ownership metadata (lock_id, session/call owner,
# timestamps, expiry, reentrant flag).
#
# In-memory for v1. Persistent/distributed locking deferred.
# ============================================================================

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class LockConflict(Exception):
    """Raised when a lock cannot be acquired due to conflict."""
    def __init__(self, resource_id: str, held_by: str):
        self.resource_id = resource_id
        self.held_by = held_by
        super().__init__(f"Lock conflict on '{resource_id}', held by '{held_by}'")


@dataclass
class LockInfo:
    """Full ownership metadata for a resource lock (correction #5)."""
    lock_id: str
    resource_id: str
    owner_session_id: str
    owner_call_id: str
    acquired_at: str
    expires_at: str
    reentrant: bool = False

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) >= exp
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "resource_id": self.resource_id,
            "owner_session_id": self.owner_session_id,
            "owner_call_id": self.owner_call_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "reentrant": self.reentrant,
        }


class ResourceLockManager:
    """Thread-safe in-memory resource lock manager.

    Supports ownership tracking, expiry, reentrant locks, and deadlock detection.
    """

    def __init__(self):
        self._locks: Dict[str, LockInfo] = {}  # resource_id -> LockInfo
        self._lock = threading.Lock()

    def acquire(
        self,
        resource_id: str,
        owner_session_id: str,
        owner_call_id: str = "",
        timeout_seconds: float = 30.0,
        reentrant: bool = False,
    ) -> LockInfo:
        """Acquire a lock on a resource.

        Raises LockConflict if already held by a different owner (unless expired).
        Reentrant locks allow the same session to re-acquire.
        """
        with self._lock:
            self._expire_stale_internal()

            existing = self._locks.get(resource_id)
            if existing:
                # Reentrant: same session can re-acquire
                if reentrant and existing.owner_session_id == owner_session_id:
                    return existing
                # Different owner: conflict
                raise LockConflict(resource_id, existing.owner_session_id)

            now = datetime.now(timezone.utc)
            from datetime import timedelta
            expires = now + timedelta(seconds=timeout_seconds)

            lock_info = LockInfo(
                lock_id=str(uuid.uuid4())[:12],
                resource_id=resource_id,
                owner_session_id=owner_session_id,
                owner_call_id=owner_call_id,
                acquired_at=now.isoformat(),
                expires_at=expires.isoformat(),
                reentrant=reentrant,
            )
            self._locks[resource_id] = lock_info
            return lock_info

    def release(self, lock_id: str) -> bool:
        """Release a specific lock by ID. Returns True if found and released."""
        with self._lock:
            for resource_id, lock_info in list(self._locks.items()):
                if lock_info.lock_id == lock_id:
                    del self._locks[resource_id]
                    return True
            return False

    def release_resource(self, resource_id: str) -> bool:
        """Release lock on a resource. Returns True if found."""
        with self._lock:
            if resource_id in self._locks:
                del self._locks[resource_id]
                return True
            return False

    def release_all(self, owner_session_id: str) -> int:
        """Release ALL locks held by a session. Returns count released.

        Critical for cleanup on failure — prevents orphaned locks.
        """
        with self._lock:
            to_release = [rid for rid, info in self._locks.items()
                          if info.owner_session_id == owner_session_id]
            for rid in to_release:
                del self._locks[rid]
            return len(to_release)

    def is_locked(self, resource_id: str) -> bool:
        with self._lock:
            self._expire_stale_internal()
            return resource_id in self._locks

    def get_lock(self, resource_id: str) -> Optional[LockInfo]:
        with self._lock:
            self._expire_stale_internal()
            return self._locks.get(resource_id)

    def detect_deadlocks(self) -> List[str]:
        """Detect potential deadlock situations.

        v1: simple check for expired locks still held (stale holders).
        Full cycle detection deferred to distributed locking.
        """
        with self._lock:
            stale = [rid for rid, info in self._locks.items() if info.is_expired()]
            return stale

    def expire_stale(self) -> int:
        """Reap locks past their timeout. Returns count expired."""
        with self._lock:
            return self._expire_stale_internal()

    def _expire_stale_internal(self) -> int:
        """Internal: expire stale locks (caller must hold self._lock)."""
        expired = [rid for rid, info in self._locks.items() if info.is_expired()]
        for rid in expired:
            del self._locks[rid]
        return len(expired)

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            self._expire_stale_internal()
            return {
                "active_locks": len(self._locks),
                "resources": list(self._locks.keys()),
                "by_session": _count_by(self._locks.values(), "owner_session_id"),
            }


def _count_by(locks, attr: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for lock in locks:
        key = getattr(lock, attr, "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts
