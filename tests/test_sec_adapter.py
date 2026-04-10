"""Tests for SEC compliance adapter."""
from ironframe.compliance.sec_v1_0 import SECAdapter, seed_sec_compliance_refs


def test_sec_adapter_instantiates():
    adapter = SECAdapter()
    assert adapter.regulation_id == "SEC"
    assert adapter.display_name


def test_list_sections_returns_6():
    adapter = SECAdapter()
    assert len(adapter.list_sections()) == 6


def test_query_ai_guidance_returns_req_018(conformance_engine):
    seed_sec_compliance_refs(conformance_engine.rtm)
    adapter = SECAdapter()
    result = adapter.query(conformance_engine, "SEC AI Guidance")
    req_ids = [r["requirement"]["requirement_id"] for r in result["requirements"]]
    assert "IF-REQ-018" in req_ids


def test_full_report_has_6_sections(conformance_engine):
    seed_sec_compliance_refs(conformance_engine.rtm)
    adapter = SECAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["total_sections"] == 6


def test_full_report_no_not_covered(conformance_engine):
    seed_sec_compliance_refs(conformance_engine.rtm)
    adapter = SECAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["not_covered"] == 0
