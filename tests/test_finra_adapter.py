"""Tests for FINRA compliance adapter."""
from ironframe.compliance.finra_v1_0 import FINRAAdapter, seed_finra_compliance_refs


def test_finra_adapter_instantiates():
    adapter = FINRAAdapter()
    assert adapter.regulation_id == "FINRA"
    assert adapter.display_name


def test_list_sections_returns_6():
    adapter = FINRAAdapter()
    assert len(adapter.list_sections()) == 6


def test_query_rule_4370_returns_if_req_011(conformance_engine):
    seed_finra_compliance_refs(conformance_engine.rtm)
    adapter = FINRAAdapter()
    result = adapter.query(conformance_engine, "FINRA Rule 4370")
    req_ids = [
        r["requirement"]["requirement_id"]
        for r in result["requirements"]
    ]
    assert "IF-REQ-011" in req_ids


def test_full_report_has_6_sections(conformance_engine):
    seed_finra_compliance_refs(conformance_engine.rtm)
    adapter = FINRAAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["total_sections"] == 6


def test_full_report_no_not_covered(conformance_engine):
    seed_finra_compliance_refs(conformance_engine.rtm)
    adapter = FINRAAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["not_covered"] == 0
