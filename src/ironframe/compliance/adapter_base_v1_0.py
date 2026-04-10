# ============================================================================
# ironframe/compliance/adapter_base_v1_0.py - v1.0
# Last updated: 2026-04-08
# ============================================================================
# Regulation mapping adapter base class.
#
# Maps regulatory sections (HIPAA, FINRA, etc.) to Iron Frame requirements
# via C18's compliance_query() infrastructure. Provides coverage reporting
# per regulation section.
#
# Separate from base_v1_0.py (which handles input/output enforcement).
# This class handles: "does Iron Frame cover regulation X section Y?"
# ============================================================================

from typing import Any, Dict, List, Optional


class ComplianceAdapter:
    """Base class for regulation mapping adapters.

    Subclasses declare regulation sections and map them to IF-REQ entries
    via compliance_refs. Provides query() and full_report() for coverage
    assessment.
    """

    regulation_id: str = ""
    display_name: str = ""
    sections: Dict[str, str] = {}  # section_id -> description

    def get_section(self, section_id: str) -> Optional[str]:
        """Get description for a section. Returns None if unknown."""
        return self.sections.get(section_id)

    def list_sections(self) -> List[str]:
        """List all section IDs for this regulation."""
        return list(self.sections.keys())

    def query(self, engine, section_id: str) -> Dict[str, Any]:
        """Query coverage for a specific regulation section.

        Calls engine.compliance_query() and enriches with coverage status.
        """
        results = engine.compliance_query(regulation_id=section_id)

        # Determine coverage status
        has_requirement = len(results) > 0
        has_impl = any(
            len(r.get("implementation", [])) > 0 for r in results
        ) if results else False
        has_verification = any(
            len(r.get("verification", [])) > 0 for r in results
        ) if results else False

        if has_requirement and has_impl and has_verification:
            coverage_status = "covered"
        elif has_requirement:
            coverage_status = "partial"
        else:
            coverage_status = "not_covered"

        return {
            "regulation_id": self.regulation_id,
            "section_id": section_id,
            "section_description": self.sections.get(section_id, ""),
            "coverage_status": coverage_status,
            "requirements": results,
            "requirement_count": len(results),
        }

    def full_report(self, engine) -> Dict[str, Any]:
        """Run query() for every section. Returns full coverage report."""
        report = {}
        covered = 0
        partial = 0
        not_covered = 0

        for section_id in self.sections:
            result = self.query(engine, section_id)
            report[section_id] = result
            status = result["coverage_status"]
            if status == "covered":
                covered += 1
            elif status == "partial":
                partial += 1
            else:
                not_covered += 1

        report["summary"] = {
            "regulation_id": self.regulation_id,
            "display_name": self.display_name,
            "total_sections": len(self.sections),
            "covered": covered,
            "partial": partial,
            "not_covered": not_covered,
        }

        return report
