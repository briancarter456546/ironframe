"""Component 9: Context Budget Manager -- zone-based budgets, stable prefix, trust preservation."""

from ironframe.context.zones_v1_0 import (
    ContextZone, ZoneContent, ContentChunk, ZONE_SEQUENCE,
    PROTECTED_ZONES, MANAGED_ZONES, COMPRESSION_PRECEDENCE,
)
from ironframe.context.budget_v1_0 import ContextBudgetAllocator, BudgetEscalation
from ironframe.context.compression_v1_0 import CompressionPipeline
from ironframe.context.rot_detector_v1_0 import assess_rot, RotAssessment
from ironframe.context.manager_v1_0 import ContextBudgetManager, ContextPackage, ContextRotEscalation
