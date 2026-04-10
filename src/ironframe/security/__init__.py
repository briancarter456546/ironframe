"""Component 11: Security / Injection Defense -- trust tiering, injection detection, action gating."""

from ironframe.security.trust_v1_0 import TrustTier, TrustedContent, classify_trust_tier
from ironframe.security.detection_v1_0 import scan_content, ScanResult
from ironframe.security.gate_v1_0 import ActionGate, GateDecision, ProvenanceChain, build_provenance_chain
from ironframe.security.sanitize_v1_0 import sanitize, SanitizedOutput
from ironframe.security.threat_log_v1_0 import ThreatEventLogger
from ironframe.security.engine_v1_0 import SecurityEngine
