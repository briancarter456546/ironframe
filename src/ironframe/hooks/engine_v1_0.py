# ============================================================================
# ironframe/hooks/engine_v1_0.py - v1.0
# Last updated: 2026-04-04
# ============================================================================
# Python-native hook engine for API/product workflows.
#
# For Claude Code sessions: bash hooks remain primary (existing pattern).
# This engine is the product equivalent -- no bash dependency, composable,
# deterministic execution order, works in any Python environment.
#
# Hook contract: receives event dict, returns HookResult.
# Hooks are composable -- multiple hooks chain on the same event.
# Order is deterministic (registration order). A blocking hook failure
# halts execution unless marked non_blocking.
#
# Usage:
#   from ironframe.hooks.engine_v1_0 import HookEngine, HookResult
#
#   engine = HookEngine()
#
#   def check_input(event):
#       if 'password' in event.get('input', '').lower():
#           return HookResult(allow=False, message='Input contains password')
#       return HookResult(allow=True)
#
#   engine.register('pre_execution', check_input, blocking=True)
#   result = engine.fire('pre_execution', {'input': 'my password is 123'})
#   print(result.allow)  # False
# ============================================================================

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class HookResult:
    """Result of a single hook execution."""
    allow: bool = True
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    hook_name: str = ""
    duration_ms: float = 0.0


@dataclass
class ChainResult:
    """Result of executing all hooks for an event."""
    allow: bool = True
    results: List[HookResult] = field(default_factory=list)
    blocked_by: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allow": self.allow,
            "hooks_fired": len(self.results),
            "blocked_by": self.blocked_by,
            "results": [
                {"hook": r.hook_name, "allow": r.allow, "message": r.message,
                 "duration_ms": round(r.duration_ms, 2)}
                for r in self.results
            ],
        }


@dataclass
class HookRegistration:
    """Internal record of a registered hook."""
    event: str
    handler: Callable[[Dict[str, Any]], HookResult]
    name: str = ""
    blocking: bool = True
    description: str = ""
    priority: int = 100     # lower = runs first


class HookEngine:
    """Python-native hook engine with composable, deterministic execution.

    Events are string identifiers. Common events:
      pre_skill, post_skill, pre_execution, post_execution,
      completion_gate, escalation, session_start, session_end

    Hooks fire in registration order (stable sort by priority).
    Blocking hooks halt the chain on failure. Non-blocking hooks
    log but don't prevent execution.
    """

    def __init__(self):
        self._hooks: Dict[str, List[HookRegistration]] = {}

    def register(
        self,
        event: str,
        handler: Callable[[Dict[str, Any]], HookResult],
        name: str = "",
        blocking: bool = True,
        description: str = "",
        priority: int = 100,
    ) -> None:
        """Register a hook for an event.

        handler: callable that takes event dict, returns HookResult.
        blocking: if True, a failed result halts the chain.
        priority: lower numbers fire first (default 100).
        """
        if not name:
            name = getattr(handler, "__name__", f"hook_{id(handler)}")

        reg = HookRegistration(
            event=event,
            handler=handler,
            name=name,
            blocking=blocking,
            description=description,
            priority=priority,
        )

        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(reg)
        # Keep sorted by priority (stable sort preserves registration order for ties)
        self._hooks[event].sort(key=lambda h: h.priority)

    def unregister(self, event: str, name: str) -> bool:
        """Remove a named hook from an event. Returns True if found."""
        if event not in self._hooks:
            return False
        before = len(self._hooks[event])
        self._hooks[event] = [h for h in self._hooks[event] if h.name != name]
        return len(self._hooks[event]) < before

    def fire(self, event: str, context: Dict[str, Any]) -> ChainResult:
        """Fire all hooks for an event in priority order.

        Returns ChainResult. If any blocking hook returns allow=False,
        the chain halts and ChainResult.allow=False.
        """
        hooks = self._hooks.get(event, [])
        results = []

        for hook in hooks:
            start = time.time()
            try:
                result = hook.handler(context)
                if not isinstance(result, HookResult):
                    result = HookResult(allow=True)
                result.hook_name = hook.name
            except Exception as exc:
                result = HookResult(
                    allow=False,
                    message=f"Hook error: {exc}",
                    hook_name=hook.name,
                )
            result.duration_ms = (time.time() - start) * 1000
            results.append(result)

            # Blocking hook failed -- halt chain
            if not result.allow and hook.blocking:
                return ChainResult(
                    allow=False,
                    results=results,
                    blocked_by=hook.name,
                )

        return ChainResult(allow=True, results=results)

    def list_hooks(self, event: Optional[str] = None) -> List[Dict[str, Any]]:
        """List registered hooks, optionally filtered by event."""
        result = []
        events = [event] if event else sorted(self._hooks.keys())
        for evt in events:
            for hook in self._hooks.get(evt, []):
                result.append({
                    "event": evt,
                    "name": hook.name,
                    "blocking": hook.blocking,
                    "priority": hook.priority,
                    "description": hook.description,
                })
        return result

    @property
    def events(self) -> List[str]:
        """List all events that have registered hooks."""
        return sorted(self._hooks.keys())

    def summary(self) -> Dict[str, int]:
        """Return count of hooks per event."""
        return {event: len(hooks) for event, hooks in sorted(self._hooks.items())}
