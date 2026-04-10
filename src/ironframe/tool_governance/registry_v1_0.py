# ============================================================================
# ironframe/tool_governance/registry_v1_0.py - v1.0
# Last updated: 2026-04-05
# ============================================================================
# Component 12a: Tool Registry
#
# Structured catalog of every tool available to the system. No tool can be
# called that is not registered. Unregistered calls are blocked as anomalies.
#
# Corrections applied:
#   #2: Auth model expanded (allowed_roles, minimum_autonomy_tier)
#   #3: governed/blocking_validation explicit, not inferred from risk
#   #8: Risk/schema mismatch behavior defined
#
# Constitution: Law 3 (agents untrusted), dependency rule (12 is the only
# layer allowed to inject live credentials).
# ============================================================================

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ToolRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ToolDefinition:
    """Complete definition of a governed tool."""

    # Identity
    tool_id: str
    name: str
    version: str = "1.0"
    description: str = ""
    risk: str = ToolRisk.MEDIUM.value

    # Schema links (two layers per correction #1)
    schema_request_id: str = ""    # "tool.{tool_id}.request" -> per-tool payload schema
    schema_response_id: str = ""   # "tool.{tool_id}.response" -> per-tool result schema

    # Auth model (correction #2)
    auth_required: bool = False
    auth_credential_key: str = ""  # env var name (never the value)
    allowed_callers: List[str] = field(default_factory=list)   # explicit allowlist override
    allowed_roles: List[str] = field(default_factory=list)     # role-based (for C17)
    minimum_autonomy_tier: int = 0  # 0 = any tier (for C17)

    # Governance (correction #3: explicit, not risk-inferred)
    governed: bool = True
    blocking_validation: bool = True

    # Rate limits (correction #6: explicit windows)
    rate_limit_rpm: int = 0              # requests per minute (0 = unlimited)
    rate_limit_cost_cap_usd: float = 0.0 # per-day cost cap (0 = uncapped)
    rate_limit_concurrency: int = 0      # max concurrent calls (0 = unlimited)

    # Contract flags
    idempotent: bool = False
    has_side_effects: bool = True
    rollback_supported: bool = False
    max_latency_ms: int = 30000          # default 30s SLA

    # Versioning
    deprecated: bool = False
    sunset_date: str = ""                # ISO date or "" = not sunset

    # Traceability
    rtm_requirements: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.schema_request_id:
            self.schema_request_id = f"tool.{self.tool_id}.request"
        if not self.schema_response_id:
            self.schema_response_id = f"tool.{self.tool_id}.response"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "version": self.version,
            "risk": self.risk,
            "governed": self.governed,
            "blocking_validation": self.blocking_validation,
            "auth_required": self.auth_required,
            "deprecated": self.deprecated,
            "schema_request_id": self.schema_request_id,
            "schema_response_id": self.schema_response_id,
        }


class ToolRegistry:
    """Catalog of all registered tools. Thread-safe.

    No tool can be called that is not registered.
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._lock = threading.Lock()

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool. Overwrites if same tool_id exists."""
        with self._lock:
            self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        """Get a tool by ID."""
        return self._tools.get(tool_id)

    def is_registered(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def unregister(self, tool_id: str) -> bool:
        """Remove a tool. Returns True if it existed."""
        with self._lock:
            if tool_id in self._tools:
                del self._tools[tool_id]
                return True
            return False

    def list_tools(self, risk: str = "", governed_only: bool = False) -> List[str]:
        """List tool IDs, optionally filtered."""
        results = []
        for tid, tool in sorted(self._tools.items()):
            if risk and tool.risk != risk:
                continue
            if governed_only and not tool.governed:
                continue
            results.append(tid)
        return results

    def summary(self) -> Dict[str, Any]:
        by_risk: Dict[str, int] = {}
        for tool in self._tools.values():
            by_risk[tool.risk] = by_risk.get(tool.risk, 0) + 1
        return {
            "total": len(self._tools),
            "by_risk": by_risk,
            "governed": sum(1 for t in self._tools.values() if t.governed),
            "deprecated": sum(1 for t in self._tools.values() if t.deprecated),
        }
