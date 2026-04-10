"""Tests for GDPR compliance adapter."""
from ironframe.compliance.gdpr_v1_0 import GDPRAdapter, seed_gdpr_compliance_refs


def test_gdpr_adapter_instantiates():
    adapter = GDPRAdapter()
    assert adapter.regulation_id == "GDPR"
    assert adapter.display_name


def test_list_sections_returns_9():
    adapter = GDPRAdapter()
    assert len(adapter.list_sections()) == 9


def test_query_art_32_returns_req_014(conformance_engine):
    seed_gdpr_compliance_refs(conformance_engine.rtm)
    adapter = GDPRAdapter()
    result = adapter.query(conformance_engine, "GDPR Art.32")
    req_ids = [r["requirement"]["requirement_id"] for r in result["requirements"]]
    assert "IF-REQ-014" in req_ids


def test_full_report_has_9_sections(conformance_engine):
    seed_gdpr_compliance_refs(conformance_engine.rtm)
    adapter = GDPRAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["total_sections"] == 9


def test_full_report_no_not_covered(conformance_engine):
    seed_gdpr_compliance_refs(conformance_engine.rtm)
    adapter = GDPRAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["not_covered"] == 0
