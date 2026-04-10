# ============================================================================
# ironframe/tool_governance/versioning_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 12f: Version Governance
#
# Multiple versions can be registered simultaneously. Version pinning
# per skill or workflow. Deprecation warnings. Sunset blocking.
# Version mismatch = drift event for Component 18.
# ============================================================================

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional


@dataclass
class VersionEvent:
    """Record of a version lifecycle event."""
    tool_id: str
    version: str
    event_type: str     # "registered", "deprecated", "sunset", "pinned", "unpinned"
    timestamp: str = ""
    detail: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "version": self.version,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "detail": self.detail,
        }


@dataclass
class VersionPin:
    """A version pin: forces a specific version for a given context."""
    tool_id: str
    version: str
    pinned_by: str       # skill name, workflow, or session ID
    pinned_at: str = ""

    def __post_init__(self):
        if not self.pinned_at:
            self.pinned_at = datetime.now(timezone.utc).isoformat()


class VersionGovernor:
    """Manages tool version lifecycle: registration, deprecation, sunset, pinning.

    Thread-safe. Tracks version events for audit.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # tool_id -> {version -> status_dict}
        self._versions: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # tool_id -> VersionPin (active pin)
        self._pins: Dict[str, VersionPin] = {}
        # Event log
        self._events: List[VersionEvent] = []

    def register_version(self, tool_id: str, version: str) -> VersionEvent:
        """Register a new version of a tool."""
        with self._lock:
            if tool_id not in self._versions:
                self._versions[tool_id] = {}
            self._versions[tool_id][version] = {
                "status": "active",
                "deprecated": False,
                "sunset_date": "",
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
            event = VersionEvent(tool_id, version, "registered")
            self._events.append(event)
            return event

    def deprecate(self, tool_id: str, version: str, sunset_date: str = "") -> VersionEvent:
        """Mark a version as deprecated. Optionally set a sunset date."""
        with self._lock:
            versions = self._versions.get(tool_id, {})
            if version in versions:
                versions[version]["deprecated"] = True
                versions[version]["status"] = "deprecated"
                if sunset_date:
                    versions[version]["sunset_date"] = sunset_date
            event = VersionEvent(
                tool_id, version, "deprecated",
                detail=f"sunset_date={sunset_date}" if sunset_date else "",
            )
            self._events.append(event)
            return event

    def is_allowed(self, tool_id: str, version: str) -> bool:
        """Check if a version is allowed to be called.

        Returns False if past sunset date. Deprecated but not sunset = allowed with warning.
        """
        with self._lock:
            versions = self._versions.get(tool_id, {})
            ver_info = versions.get(version)
            if not ver_info:
                return True  # unknown version = allow (registry check is separate)

            sunset = ver_info.get("sunset_date", "")
            if sunset:
                try:
                    sunset_dt = date.fromisoformat(sunset)
                    if date.today() >= sunset_dt:
                        return False
                except (ValueError, TypeError):
                    pass
            return True

    def is_deprecated(self, tool_id: str, version: str) -> bool:
        """Check if a version is deprecated (still callable, but warned)."""
        versions = self._versions.get(tool_id, {})
        ver_info = versions.get(version, {})
        return ver_info.get("deprecated", False)

    def is_sunset(self, tool_id: str, version: str) -> bool:
        """Check if a version is past its sunset date (blocked)."""
        return not self.is_allowed(tool_id, version)

    def pin(self, tool_id: str, version: str, pinned_by: str) -> VersionPin:
        """Pin a tool to a specific version for a given context."""
        with self._lock:
            pin = VersionPin(tool_id, version, pinned_by)
            self._pins[tool_id] = pin
            self._events.append(VersionEvent(
                tool_id, version, "pinned", detail=f"by={pinned_by}",
            ))
            return pin

    def unpin(self, tool_id: str) -> bool:
        """Remove version pin for a tool. Returns True if pin existed."""
        with self._lock:
            if tool_id in self._pins:
                old = self._pins.pop(tool_id)
                self._events.append(VersionEvent(
                    tool_id, old.version, "unpinned",
                ))
                return True
            return False

    def get_pinned_version(self, tool_id: str) -> Optional[str]:
        """Get the pinned version for a tool, or None if not pinned."""
        pin = self._pins.get(tool_id)
        return pin.version if pin else None

    def resolve_version(self, tool_id: str, requested_version: str) -> str:
        """Resolve the effective version: pin overrides requested version."""
        pinned = self.get_pinned_version(tool_id)
        return pinned if pinned else requested_version

    def list_events(self, tool_id: str = "") -> List[VersionEvent]:
        """Get version events, optionally filtered by tool."""
        if tool_id:
            return [e for e in self._events if e.tool_id == tool_id]
        return list(self._events)

    def summary(self) -> Dict[str, Any]:
        return {
            "tools_versioned": len(self._versions),
            "active_pins": len(self._pins),
            "total_events": len(self._events),
        }
