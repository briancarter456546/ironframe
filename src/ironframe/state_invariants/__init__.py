"""IronFrame state-invariants library.

C3x — Cross-View State Consistency. Reusable primitives for any surface that
renders metrics derived from shared analysis state (window, universe, benchmark,
as-of, methodology, ...). Pure-library: no Minerva, no UI, no operator deps.

Slice 1 ships only the canonical-window definitions. Provenance dataclass and
cross-view invariant validator are deferred to Slice 2 (see task_db #985, #986).
"""
from .canonical_windows_v1_0 import (
    WindowSpec,
    CANONICAL_WINDOWS,
    get_canonical_window,
    list_canonical_windows,
    effective_n_days,
    render_window_badge,
    serialize_spec,
    deserialize_spec,
    KNOWN_TYPES,
)

__all__ = [
    'WindowSpec',
    'CANONICAL_WINDOWS',
    'get_canonical_window',
    'list_canonical_windows',
    'effective_n_days',
    'render_window_badge',
    'serialize_spec',
    'deserialize_spec',
    'KNOWN_TYPES',
]
