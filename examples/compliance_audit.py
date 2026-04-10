"""
Compliance adapter introspection -- inspect a regulation mapping.

LICENSE NOTICE: This example imports HIPAAAdapter, which is licensed under
the PolyForm Noncommercial License. Free for research, education, nonprofits,
and personal projects. Commercial use requires a commercial license.
See src/ironframe/compliance/adapters/LICENSE_COMMERCIAL.

The compliance adapter pattern maps regulation sections (HIPAA Security Rule,
FINRA Rule 4511, SOC2 Trust Services Criteria, etc.) to Iron Frame requirements
via the Conformance (C18) engine. Each adapter exposes:

    adapter.regulation_id      -- e.g. "HIPAA"
    adapter.display_name       -- e.g. "Health Insurance Portability..."
    adapter.sections           -- dict of section_id -> description
    adapter.list_sections()    -- list of section IDs
    adapter.get_section(id)    -- description for a section
    adapter.query(engine, id)  -- coverage for a section (requires C18 engine)
    adapter.full_report(engine)-- coverage for all sections

This example introspects the adapter without wiring a full conformance engine.

Run:
    python examples/compliance_audit.py
"""

from ironframe.compliance.adapters.hipaa_v1_0 import HIPAAAdapter


def main() -> None:
    adapter = HIPAAAdapter()

    print("=== Iron Frame Compliance Adapter Introspection ===\n")
    print(f"Regulation:   {adapter.regulation_id}")
    print(f"Display name: {adapter.display_name}")
    print(f"Total sections mapped: {len(adapter.sections)}\n")

    sections = adapter.list_sections()
    print(f"First 10 sections:")
    for section_id in sections[:10]:
        desc = adapter.get_section(section_id) or ""
        print(f"  {section_id:20s}  {desc[:60]}")
    if len(sections) > 10:
        print(f"  ... and {len(sections) - 10} more")
    print()

    print("To generate a full coverage report, pass a conformance engine:")
    print()
    print("    from ironframe.conformance.engine_v1_0 import ConformanceEngine")
    print("    engine = ConformanceEngine()")
    print("    report = adapter.full_report(engine)")
    print("    print(report['summary'])  # covered / partial / not_covered counts")
    print()
    print("The same pattern works for FINRA, SOC2, SEC, and GDPR adapters.")


if __name__ == "__main__":
    main()
