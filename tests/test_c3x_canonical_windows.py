"""C3x cross-view state consistency — canonical windows tests."""

import pytest

from ironframe.state_invariants import (
    CANONICAL_WINDOWS,
    KNOWN_TYPES,
    WindowSpec,
    deserialize_spec,
    effective_n_days,
    get_canonical_window,
    list_canonical_windows,
    render_window_badge,
    serialize_spec,
)


# -- WINDOWS structure --------------------------------------------------------

def test_canonical_windows_is_tuple():
    assert isinstance(CANONICAL_WINDOWS, tuple)
    assert all(isinstance(s, WindowSpec) for s in CANONICAL_WINDOWS)


def test_labels_unique():
    labels = [s.label for s in CANONICAL_WINDOWS]
    assert len(labels) == len(set(labels)), 'duplicate labels: ' + repr(labels)


def test_params_unique():
    sigs = [(s.type, s.params) for s in CANONICAL_WINDOWS]
    assert len(sigs) == len(set(sigs)), 'duplicate (type, params): ' + repr(sigs)


def test_slice1_only_fixed_trading():
    """Slice 1 only ships fixed_trading; richer types are listed in KNOWN_TYPES
    but no specs yet. This test pins that until walk_forward / oos_holdout /
    regime_conditioned types are designed."""
    types = {s.type for s in CANONICAL_WINDOWS}
    assert types == {'fixed_trading'}, 'unexpected types in slice 1: ' + repr(types)


def test_known_types_includes_extension_surface():
    assert 'fixed_trading' in KNOWN_TYPES
    assert 'walk_forward' in KNOWN_TYPES
    assert 'oos_holdout' in KNOWN_TYPES
    assert 'regime_conditioned' in KNOWN_TYPES


# -- WindowSpec invariants ----------------------------------------------------

def test_windowspec_is_frozen():
    s = CANONICAL_WINDOWS[0]
    with pytest.raises(Exception):
        s.label = 'mutated'  # frozen dataclass


def test_windowspec_rejects_unknown_type():
    with pytest.raises(ValueError):
        WindowSpec(label='x', type='unknown_kind', params=())


def test_windowspec_rejects_empty_label():
    with pytest.raises(ValueError):
        WindowSpec(label='', type='fixed_trading', params=(('n_days', 252),))


def test_windowspec_rejects_dict_params():
    """Params must be tuple-of-tuples for hashability."""
    with pytest.raises(TypeError):
        WindowSpec(label='1y', type='fixed_trading', params={'n_days': 252})


def test_windowspec_is_hashable():
    s = CANONICAL_WINDOWS[0]
    {s}  # raises TypeError if not hashable


# -- Helpers ------------------------------------------------------------------

def test_get_canonical_window_known():
    s = get_canonical_window('5y')
    assert s is not None
    assert s.label == '5y'
    assert s.type == 'fixed_trading'
    assert s.params_dict() == {'n_days': 1260}


def test_get_canonical_window_unknown():
    assert get_canonical_window('99y') is None


def test_list_canonical_windows_matches_module():
    assert list_canonical_windows() is CANONICAL_WINDOWS


def test_effective_n_days_fixed_trading():
    cases = [('63d', 63), ('126d', 126), ('1y', 252), ('3y', 756),
             ('5y', 1260), ('7y', 1764), ('10y', 2520)]
    for label, expected in cases:
        spec = get_canonical_window(label)
        assert spec is not None, label
        assert effective_n_days(spec) == expected, label


def test_effective_n_days_unknown_kind_raises():
    """Future window kinds must opt into a kind-specific accessor."""
    spec = WindowSpec(label='wf-x', type='walk_forward',
                      params=(('train_days', 252), ('test_days', 252),
                              ('step_days', 252), ('num_steps', 3)))
    with pytest.raises(NotImplementedError):
        effective_n_days(spec)


def test_render_window_badge_fixed_trading():
    spec = get_canonical_window('5y')
    assert render_window_badge(spec) == '5y · 1260d'


def test_render_window_badge_uses_display_label_override():
    spec = WindowSpec(label='WF-3x1y', type='walk_forward',
                      params=(('num_steps', 3), ('step_days', 252),
                              ('test_days', 252), ('train_days', 252)),
                      display_label='WF 3x1y')
    assert render_window_badge(spec) == 'WF 3x1y'


def test_render_window_badge_falls_back_to_label_for_unknown_kind():
    spec = WindowSpec(label='regime-bull-3y', type='regime_conditioned',
                      params=(('regime', 'bull'), ('base_window_days', 756)))
    assert render_window_badge(spec) == 'regime-bull-3y'


# -- Serialization ------------------------------------------------------------

def test_serialize_roundtrip_all():
    for s in CANONICAL_WINDOWS:
        d = serialize_spec(s)
        s2 = deserialize_spec(d)
        assert s2 == s, repr(d)


def test_serialize_shape():
    d = serialize_spec(get_canonical_window('5y'))
    assert d['label'] == '5y'
    assert d['type'] == 'fixed_trading'
    assert d['params'] == {'n_days': 1260}
    assert 'description' in d
    assert 'display_label' in d


def test_deserialize_rejects_bad_input():
    with pytest.raises(TypeError):
        deserialize_spec('not a dict')
    with pytest.raises(ValueError):
        deserialize_spec({})


# -- Regression for the actual bug -------------------------------------------

def test_regression_5y_n_days_is_1260_not_1256_or_1826():
    """The original bug: backend used calendar 5y (1826 days -> 1256 trading
    days slice) while frontend used 1260 trading days. Pin the canonical to
    1260 trading days so backend + frontend can never drift again."""
    spec = get_canonical_window('5y')
    assert spec is not None
    assert spec.type == 'fixed_trading'
    assert spec.params_dict()['n_days'] == 1260
    assert effective_n_days(spec) == 1260
