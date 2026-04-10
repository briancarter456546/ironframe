"""Tests for HIPAA compliance adapter."""
from ironframe.compliance.hipaa_v1_0 import HIPAAAdapter, seed_hipaa_compliance_refs


def test_hipaa_adapter_instantiates():
    adapter = HIPAAAdapter()
    assert adapter.regulation_id == "HIPAA"
    assert adapter.display_name


def test_list_sections_returns_7():
    adapter = HIPAAAdapter()
    assert len(adapter.list_sections()) == 7


def test_get_section_known():
    adapter = HIPAAAdapter()
    desc = adapter.get_section("HIPAA \u00a7164.312")
    assert desc == "Technical safeguards"


def test_get_section_unknown():
    adapter = HIPAAAdapter()
    assert adapter.get_section("HIPAA \u00a7999.999") is None


def test_query_returns_coverage_for_164_312(conformance_engine):
    seed_hipaa_compliance_refs(conformance_engine.rtm)
    adapter = HIPAAAdapter()
    result = adapter.query(conformance_engine, "HIPAA \u00a7164.312")
    assert result["coverage_status"] in ("covered", "partial")
    assert result["requirement_count"] >= 2


def test_full_report_has_7_sections(conformance_engine):
    seed_hipaa_compliance_refs(conformance_engine.rtm)
    adapter = HIPAAAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["total_sections"] == 7


def test_full_report_no_not_covered(conformance_engine):
    seed_hipaa_compliance_refs(conformance_engine.rtm)
    adapter = HIPAAAdapter()
    report = adapter.full_report(conformance_engine)
    assert report["summary"]["not_covered"] == 0
