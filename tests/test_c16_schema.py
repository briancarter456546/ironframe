"""Tests for Component 16: I/O Schema Validation."""
from ironframe.io_schema.registry_v1_0 import SchemaDefinition, FieldSpec
from ironframe.io_schema.validator_v1_0 import validate_payload
from ironframe.io_schema.coercion_v1_0 import CoercionPolicy
from ironframe.io_schema.errors_v1_0 import MISSING_REQUIRED, UNKNOWN_FIELD


def _make_test_schema():
    """Create a simple schema for testing."""
    return SchemaDefinition(
        schema_id="test.message",
        version="1.0",
        fields={
            "sender_id": FieldSpec(name="sender_id", field_type="string", required=True),
            "tier": FieldSpec(name="tier", field_type="int", required=True),
            "payload": FieldSpec(name="payload", field_type="dict", required=False),
        },
        required=["sender_id", "tier"],
    )


def test_valid_message_passes():
    schema = _make_test_schema()
    result = validate_payload(
        {"sender_id": "agent-A", "tier": 2, "payload": {"key": "val"}},
        schema,
        CoercionPolicy.strict(),
    )
    assert result.valid is True
    assert result.outcome == "passed"
    assert len(result.errors) == 0


def test_missing_required_field_fails():
    schema = _make_test_schema()
    result = validate_payload(
        {"tier": 2},
        schema,
        CoercionPolicy.strict(),
    )
    assert result.valid is False
    assert any(e.error_type == MISSING_REQUIRED for e in result.errors)


def test_extra_field_fails_strict():
    schema = _make_test_schema()
    result = validate_payload(
        {"sender_id": "agent-A", "tier": 2, "rogue_field": "bad"},
        schema,
        CoercionPolicy.strict(allow_unknown=False),
    )
    assert result.valid is False
    assert any(e.error_type == UNKNOWN_FIELD for e in result.errors)


def test_extra_field_allowed_when_configured():
    schema = _make_test_schema()
    result = validate_payload(
        {"sender_id": "agent-A", "tier": 2, "extra": "ok"},
        schema,
        CoercionPolicy.strict(allow_unknown=True),
    )
    assert result.valid is True


def test_wrong_type_fails():
    schema = _make_test_schema()
    result = validate_payload(
        {"sender_id": "agent-A", "tier": "not_an_int"},
        schema,
        CoercionPolicy.strict(),
    )
    assert result.valid is False
    assert any(e.field == "tier" for e in result.errors)
