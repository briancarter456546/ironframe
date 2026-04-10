"""Component 14: Agent Coordination Protocol -- structured multi-agent orchestration."""

from ironframe.coordination.roles_v1_0 import RoleRegistry, AgentRole, RoleViolation
from ironframe.coordination.messages_v1_0 import AgentMessage, MessageType, MessageLog, create_message
from ironframe.coordination.tasks_v1_0 import TaskGraph, SubTask, CircularDependency
from ironframe.coordination.handoff_v1_0 import HandoffProtocol, HandoffResult
from ironframe.coordination.loops_v1_0 import LoopDetector, LoopDetection
from ironframe.coordination.resources_v1_0 import ResourceCoordinator
from ironframe.coordination.protocol_v1_0 import CoordinationProtocol
