"""Tests for RTM requirement coverage."""


def test_all_accepted_requirements_have_impl_artifacts(rtm_registry):
    for entry in rtm_registry._entries.values():
        if entry.status == "accepted":
            assert len(entry.implementation_artifacts) > 0, \
                f"{entry.requirement_id} has no implementation_artifacts"


def test_original_requirements_have_verification_artifacts(rtm_registry):
    """Original IF-REQ-001 through IF-REQ-010 (+ 004A-D) must have verification."""
    original_ids = {f"IF-REQ-{i:03d}" for i in range(1, 11)}
    original_ids.update({"IF-REQ-004A", "IF-REQ-004B", "IF-REQ-004C", "IF-REQ-004D"})
    for entry in rtm_registry._entries.values():
        if entry.status == "accepted" and entry.requirement_id in original_ids:
            assert len(entry.verification_artifacts) > 0, \
                f"{entry.requirement_id} has no verification_artifacts"


def test_new_requirements_have_impl_artifacts(rtm_registry):
    """IF-REQ-011 through IF-REQ-018 must have implementation artifacts."""
    new_ids = {f"IF-REQ-{i:03d}" for i in range(11, 19)}
    for entry in rtm_registry._entries.values():
        if entry.requirement_id in new_ids:
            assert len(entry.implementation_artifacts) > 0, \
                f"{entry.requirement_id} has no implementation_artifacts"


def test_if_req_004_sub_requirements(rtm_registry):
    for req_id in ["IF-REQ-004", "IF-REQ-004A", "IF-REQ-004B",
                    "IF-REQ-004C", "IF-REQ-004D"]:
        entry = rtm_registry.get(req_id)
        assert entry is not None, f"{req_id} not in RTM"
        assert entry.status == "accepted"


def test_c15_requirements_registered(rtm_registry):
    for req_id in ["IF-REQ-009", "IF-REQ-010"]:
        entry = rtm_registry.get(req_id)
        assert entry is not None, f"{req_id} not in RTM"
