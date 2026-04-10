"""Tests for Component 3: State Machine / Session Manager (IF-REQ-017)."""
from ironframe.state.phase_v1_0 import PhaseGate, PhaseDeclaration


def test_session_creates_with_state(tmp_path):
    from ironframe.state.session_v1_0 import IronFrameSession
    session = IronFrameSession(base_dir=str(tmp_path), checkpoint_path=str(tmp_path / "cp.json"))
    session.set_category("OPS")
    assert session.category == "OPS"


def test_session_persists_and_retrieves(tmp_path):
    from ironframe.state.session_v1_0 import IronFrameSession
    session = IronFrameSession(base_dir=str(tmp_path), checkpoint_path=str(tmp_path / "cp.json"))
    session.set_category("REVENUE")
    session.set_hooks_profile("trading")
    # Re-read from disk
    session2 = IronFrameSession(base_dir=str(tmp_path), checkpoint_path=str(tmp_path / "cp.json"))
    assert session2.category == "REVENUE"
    assert session2.hooks_profile == "trading"


def test_phase_transitions_follow_order():
    gate = PhaseGate("test-skill", phases=[
        PhaseDeclaration(name="orient", required_before=["explore", "test"]),
        PhaseDeclaration(name="explore", required_before=["test"]),
        PhaseDeclaration(name="test", required_before=[]),
    ])
    result = gate.check("explore", phases_done=["orient"])
    assert result.allowed is True


def test_invalid_phase_transition_rejected():
    gate = PhaseGate("test-skill", phases=[
        PhaseDeclaration(name="orient", required_before=["explore", "test"]),
        PhaseDeclaration(name="explore", required_before=["test"]),
        PhaseDeclaration(name="test", required_before=[]),
    ])
    result = gate.check("test", phases_done=[])
    assert result.allowed is False
    assert "orient" in result.missing


def test_session_state_survives_simulated_restart(tmp_path):
    from ironframe.state.session_v1_0 import IronFrameSession
    session = IronFrameSession(base_dir=str(tmp_path), checkpoint_path=str(tmp_path / "cp.json"))
    session.set_category("NOVELTY")
    session.activate_skill("test-skill", phases=["orient", "explore"])
    session.mark_phase_done("orient")
    # Simulate restart: read snapshot, create new session, verify
    snap = session.snapshot()
    assert snap["session_state"]["category"] == "NOVELTY"
    assert "orient" in snap["skill_state"]["phases_done"]
    session2 = IronFrameSession(base_dir=str(tmp_path), checkpoint_path=str(tmp_path / "cp.json"))
    assert session2.category == "NOVELTY"
    assert session2.is_phase_done("orient")
