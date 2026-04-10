"""Compliance Adapter Layer - pluggable protocol enforcement.

The concrete regulatory adapters (HIPAA, FINRA, SOC2, SEC, GDPR) are
source-available under the PolyForm Noncommercial License in the pure repo.
Base classes and audit requirement constants remain Apache 2.0 and must be
imported by their full module path (they share a class name across files).
"""

# In dev these live directly in compliance/. In the pure repo the sync
# script relocates them to compliance/adapters/ and generates shim modules
# at compliance/<name>_v1_0.py so these import paths still work.
from ironframe.compliance.hipaa_v1_0 import HIPAAAdapter
from ironframe.compliance.finra_v1_0 import FINRAAdapter
from ironframe.compliance.soc2_v1_0 import SOC2Adapter
from ironframe.compliance.sec_v1_0 import SECAdapter
from ironframe.compliance.gdpr_v1_0 import GDPRAdapter
