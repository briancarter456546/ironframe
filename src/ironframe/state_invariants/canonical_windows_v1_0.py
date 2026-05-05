# ============================================================================
# canonical_windows_v1_0.py - v1.0
# Last updated: 2026-05-05
# ============================================================================
# C3x slice 1: canonical analysis-window definitions for the IronFrame
# ecosystem. Single source of truth so backend, frontend, and any future
# consumer (backtest engine, monitoring) reference the same labels + params.
#
# WindowSpec is intentionally generalized so future window kinds (walk-forward,
# OOS holdout, regime-conditioned) can be added without breaking consumers.
# Slice 1 only populates `fixed_trading` specs.
# ============================================================================
"""Canonical window specifications for the IronFrame ecosystem.

Pure-library, no I/O, no external deps. Safe to import from any consumer.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# Recognized window types. Slice 1 only populates `fixed_trading`. Other types
# are listed as the extension surface; they will be designed when the first
# consumer needs them (see task_db #992 / #993 / #994).
KNOWN_TYPES: Tuple[str, ...] = (
    'fixed_trading',     # last N trading days from `as_of`
    'fixed_calendar',    # last N calendar days from `as_of`
    'walk_forward',      # train/test blocks (params: train_days, test_days, step_days, num_steps)
    'oos_holdout',       # in-sample / out-of-sample split (params: split_date or pct)
    'regime_conditioned',  # window depends on a regime label or predicate
)


@dataclass(frozen=True)
class WindowSpec:
    """Immutable description of an analysis window.

    Slice 1 only stamps `fixed_trading` specs from this lib. Future kinds add
    new `type` strings + their own `params` schema; consumers extend with
    `effective_n_days()` / `render_window_badge()` overrides as needed.
    """
    label: str            # short stable identifier, e.g. "5y", "WF-3x1y", "OOS-2019"
    type: str             # one of KNOWN_TYPES
    params: tuple         # tuple of (key, value) pairs (frozen + hashable; reconstruct dict via dict())
    description: str = '' # optional human note
    display_label: str = ''  # optional override for UI

    def __post_init__(self):
        if self.type not in KNOWN_TYPES:
            raise ValueError('unknown window type: ' + repr(self.type))
        if not self.label:
            raise ValueError('label required')
        # params must be a tuple-of-tuples for hashability
        if not isinstance(self.params, tuple):
            raise TypeError('WindowSpec.params must be a tuple of (key, value) pairs')
        for kv in self.params:
            if not (isinstance(kv, tuple) and len(kv) == 2 and isinstance(kv[0], str)):
                raise TypeError('each WindowSpec.params entry must be (str, value)')

    def params_dict(self) -> Dict[str, object]:
        """Return params as a dict for ergonomic access."""
        return dict(self.params)


def _spec(label: str, wtype: str, **params) -> WindowSpec:
    """Helper: build a WindowSpec from kwargs (sorted for determinism)."""
    p = tuple(sorted(params.items()))
    return WindowSpec(label=label, type=wtype, params=p)


# Canonical analysis windows. The ONLY place WINDOWS is defined; backend +
# frontend must read from this (frontend via API echo of `canonical_windows`).
CANONICAL_WINDOWS: Tuple[WindowSpec, ...] = (
    _spec('63d',  'fixed_trading', n_days=63),
    _spec('126d', 'fixed_trading', n_days=126),
    _spec('1y',   'fixed_trading', n_days=252),
    _spec('3y',   'fixed_trading', n_days=756),
    _spec('5y',   'fixed_trading', n_days=1260),
    _spec('7y',   'fixed_trading', n_days=1764),
    _spec('10y',  'fixed_trading', n_days=2520),
)


def list_canonical_windows() -> Tuple[WindowSpec, ...]:
    """Return the full canonical window tuple. Immutable."""
    return CANONICAL_WINDOWS


def get_canonical_window(label: str) -> Optional[WindowSpec]:
    """Look up a WindowSpec by its label. Returns None if not present."""
    for s in CANONICAL_WINDOWS:
        if s.label == label:
            return s
    return None


def effective_n_days(spec: WindowSpec) -> Optional[int]:
    """Return the trading-day count for windows that have one.

    Defined for `fixed_trading` (params['n_days']) and `fixed_calendar` (the
    n_days param converted from calendar days; identity until we add the
    calendar slicer). For walk_forward / oos_holdout / regime_conditioned
    this raises NotImplementedError -- callers must opt into a kind-specific
    accessor when those types are designed.
    """
    p = spec.params_dict()
    if spec.type == 'fixed_trading':
        n = p.get('n_days')
        return int(n) if isinstance(n, int) else None
    if spec.type == 'fixed_calendar':
        n = p.get('n_days')
        return int(n) if isinstance(n, int) else None
    raise NotImplementedError(
        'effective_n_days not defined for window type {!r}; '
        'design the accessor when the first consumer of this type lands'.format(spec.type))


def render_window_badge(spec: WindowSpec) -> str:
    """Compose a short human-readable badge for UI stamps.

    fixed_trading       -> "5y · 1260d"
    fixed_calendar      -> "5y · 1826cd"
    walk_forward        -> "WF 3x1y" (uses display_label if provided)
    oos_holdout         -> "OOS 2019" (uses display_label if provided)
    regime_conditioned  -> "regime-bull-3y" (uses display_label if provided)
    """
    if spec.display_label:
        return spec.display_label
    p = spec.params_dict()
    if spec.type == 'fixed_trading':
        n = p.get('n_days')
        return '{} · {}d'.format(spec.label, n) if isinstance(n, int) else spec.label
    if spec.type == 'fixed_calendar':
        n = p.get('n_days')
        return '{} · {}cd'.format(spec.label, n) if isinstance(n, int) else spec.label
    # Future kinds: fall back to the label until the consumer-specific renderer
    # is wired up (when the type is designed).
    return spec.label


def serialize_spec(spec: WindowSpec) -> Dict[str, object]:
    """JSON-safe dict representation of a WindowSpec."""
    return {
        'label': spec.label,
        'type': spec.type,
        'params': spec.params_dict(),
        'description': spec.description,
        'display_label': spec.display_label,
    }


def deserialize_spec(d: Dict[str, object]) -> WindowSpec:
    """Reconstruct a WindowSpec from a JSON dict."""
    if not isinstance(d, dict):
        raise TypeError('deserialize_spec: expected dict')
    label = d.get('label')
    wtype = d.get('type')
    params_d = d.get('params', {})
    if not isinstance(label, str) or not isinstance(wtype, str) or not isinstance(params_d, dict):
        raise ValueError('deserialize_spec: malformed payload')
    p = tuple(sorted(params_d.items()))
    return WindowSpec(
        label=label,
        type=wtype,
        params=p,
        description=str(d.get('description', '')),
        display_label=str(d.get('display_label', '')),
    )
