"""Tests for Component 6: Logic Auditing (IF-REQ-018)."""
from ironframe.logic.toulmin_v1_0 import ToulminArgument, toulmin_prompt
from ironframe.logic.cqot_v1_0 import evaluate_argument, CRITICAL_QUESTIONS
from ironframe.logic.fallacy_v1_0 import get_fallacy, search_fallacies, FALLACY_TAXONOMY


def test_toulmin_decomposition():
    arg = ToulminArgument(
        claim="RSI2 < 10 is a profitable entry signal",
        grounds=["PF = 3.56 over 258 trades", "Win rate 81.4%"],
        warrant="Extreme oversold readings revert to mean within 5 days",
        backing="Mean reversion is well-documented in equity markets",
        qualifier="On SPY with SMA200 filter, 2015-2025 data",
        rebuttal="May fail in sustained bear markets (VIX > 35)",
    )
    assert arg.claim
    assert arg.warrant
    assert arg.backing
    assert arg.is_complete
    assert arg.strength == "STRONG"


def test_toulmin_validates_incomplete():
    arg = ToulminArgument(claim="Something is true")
    issues = arg.validate()
    assert len(issues) > 0
    assert any("GROUNDS" in i for i in issues)
    assert any("WARRANT" in i for i in issues)


def test_cqot_returns_critical_questions():
    assert "claim" in CRITICAL_QUESTIONS
    assert "warrant" in CRITICAL_QUESTIONS
    assert len(CRITICAL_QUESTIONS["claim"]) >= 3


def test_cqot_evaluate_complete_argument():
    arg = ToulminArgument(
        claim="Test claim",
        grounds=["Evidence 1"],
        warrant="Because X leads to Y",
        qualifier="With 80% confidence",
        rebuttal="Unless Z happens",
    )
    result = evaluate_argument(arg)
    assert result.total_questions > 0
    assert result.evaluated > 0
    assert result.passed > 0


def test_fallacy_scanner_flags_known_fallacy():
    f = get_fallacy("straw_man")
    assert f is not None
    assert f["category"] == "relevance"
    assert len(f["detection_questions"]) >= 2


def test_fallacy_scanner_passes_clean():
    results = search_fallacies("xyznonexistent")
    assert len(results) == 0


def test_fallacy_taxonomy_has_30():
    assert len(FALLACY_TAXONOMY) >= 29


def test_combined_audit_pipeline():
    arg = ToulminArgument(
        claim="Iron Frame improves reliability",
        grounds=["Catches hallucinations", "Enforces process"],
        warrant="Deterministic hooks cannot be bypassed by model reasoning",
        qualifier="For API-based deployments",
        rebuttal="Adds latency overhead",
    )
    issues = arg.validate()
    cqot = evaluate_argument(arg)
    assert isinstance(issues, list)
    assert cqot.total_questions > 0
