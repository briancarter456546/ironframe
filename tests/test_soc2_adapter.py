"""Tests for SOC 2 compliance adapter."""
from ironframe.compliance.soc2_v1_0 import SOC2Adapter, seed_soc2_compliance_refs


def test_soc2_adapter_instantiates():
    adapter = SOC2Adapter()
    assert adapter.regulation_id == "SOC2"
    assert adapter.display_name


def test_list_sections_returns_9():
    adapter = SOC2Adapter()
    assert len(adapter.list_sections()) == 9


def test_get_section_known():
    adapter = SOC2Adapter()
    assert adapter.get_section("SOC2 CC6.3") == "Role-based access and least privilege"


def test_get_section_unknown():
    adapter = SOC2Adapter()
    assert adapter.get_section("SOC2 ZZ9.9") is None


def test_query_cc6_3_returns_req_002_and_007(conformance_engine):
    seed_soc2_compliance_refs(conformance_engine.rtm)
    adapter = SOC2Adapter()
    result = adapter.query(conformance_engine, "SOC2 CC6.3")
    req_ids = [r["requirement"]["requirement_id"] for r in result["requirements"]]
    assert "IF-REQ-002" in req_ids
    assert "IF-REQ-007" in req_ids


def test_full_report_has_9_sections(conformance_engine):
    seed_soc2_compliance_refs(conformance_engine.rtm)
    adapter = SOC2Adapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["total_sections"] == 9


def test_full_report_no_not_covered(conformance_engine):
    seed_soc2_compliance_refs(conformance_engine.rtm)
    adapter = SOC2Adapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["not_covered"] == 0
