"""Component 17: Agent Trust & Containment -- zero-trust agent identity, autonomy tiers, containment."""

from ironframe.agent_trust.tiers_v1_0 import AutonomyTier, get_tier_permissions, is_action_allowed
from ironframe.agent_trust.identity_v1_0 import IdentityProvider, SessionToken
from ironframe.agent_trust.kill_switch_v1_0 import KillSwitch, KillSeverity, KillEvent
from ironframe.agent_trust.anomaly_v1_0 import AnomalyDetector, AnomalyAssessment, AgentBaseline
from ironframe.agent_trust.permissions_v1_0 import PermissionAuthority, PermissionDecision
from ironframe.agent_trust.provenance_v1_0 import OutputProvenance, create_provenance
from ironframe.agent_trust.engine_v1_0 import AgentTrustEngine
