# ============================================================================
# ironframe/context/compression_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 9c: Priority-Weighted Compression Pipeline
#
# 4 passes, MANAGED zones only. Protection zones EXCLUDED.
#
# Dual-zone overflow precedence (addition #2):
#   1. Compress CONVERSATION_HISTORY first
#   2. If still over: compress RETRIEVED_CONTEXT
#   3. If both at floor and still over: escalate
#   NEVER compress into protection zones.
#
# Trust metadata preserved through every pass (9d invariant).
#
# v1: exact dedup, keyword relevance, truncation-based summary, tail truncation.
# Embedding/LLM-based methods deferred.
# ============================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ironframe.context.zones_v1_0 import (
    ContentChunk, ZoneContent, ContextZone, PROTECTED_ZONES,
    MANAGED_ZONES, COMPRESSION_PRECEDENCE,
)
from ironframe.context.budget_v1_0 import ContextBudgetAllocator
from ironframe.context.trust_preservation_v1_0 import verify_preservation


@dataclass
class CompressionEvent:
    """Record of a compression action."""
    zone: str
    pass_name: str          # dedup, relevance, summarize, truncate
    chunks_before: int
    chunks_after: int
    tokens_before: int
    tokens_after: int
    tokens_saved: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone": self.zone,
            "pass": self.pass_name,
            "chunks_before": self.chunks_before,
            "chunks_after": self.chunks_after,
            "tokens_saved": self.tokens_saved,
        }


@dataclass
class CompressionResult:
    """Result of running the compression pipeline."""
    zones_compressed: List[str]
    events: List[CompressionEvent] = field(default_factory=list)
    total_tokens_saved: int = 0
    hard_truncations: int = 0
    trust_violations: List[str] = field(default_factory=list)
    escalated: bool = False


class CompressionPipeline:
    """4-pass compression pipeline for managed zones.

    Dual-zone overflow precedence: CONVERSATION_HISTORY first,
    then RETRIEVED_CONTEXT. Never touches protection zones.
    """

    def __init__(self, current_task_keywords: Optional[List[str]] = None):
        self._task_keywords = set(
            w.lower() for w in (current_task_keywords or []) if len(w) > 3
        )

    def compress_to_budget(
        self,
        zones: Dict[str, ZoneContent],
        allocator: ContextBudgetAllocator,
    ) -> CompressionResult:
        """Compress managed zones to fit within budget.

        Follows COMPRESSION_PRECEDENCE: CONVERSATION_HISTORY first,
        then RETRIEVED_CONTEXT. Escalates if both at floor and still over.
        """
        result = CompressionResult(zones_compressed=[])

        for zone_enum in COMPRESSION_PRECEDENCE:
            zone_key = zone_enum.value
            zone = zones.get(zone_key)
            if not zone or not zone.chunks:
                continue

            budget = allocator.get_budget(zone_key)
            if not budget.over_budget:
                continue

            # Run 4-pass pipeline on this zone
            original_chunks = list(zone.chunks)
            target_tokens = budget.max_tokens

            # Pass 1: Deduplication
            zone.chunks = self._pass_dedup(zone.chunks)
            result.events.append(self._event(zone_key, "dedup", original_chunks, zone.chunks))

            if zone.token_count <= target_tokens:
                zone.compressed = True
                result.zones_compressed.append(zone_key)
                allocator.update_usage(zone_key, zone.token_count)
                continue

            # Pass 2: Relevance filtering
            pre_relevance = list(zone.chunks)
            zone.chunks = self._pass_relevance(zone.chunks, zone_key)
            result.events.append(self._event(zone_key, "relevance", pre_relevance, zone.chunks))

            if zone.token_count <= target_tokens:
                zone.compressed = True
                result.zones_compressed.append(zone_key)
                allocator.update_usage(zone_key, zone.token_count)
                continue

            # Pass 3: Tiered summarization (v1: keep first N tokens worth of chunks)
            pre_summary = list(zone.chunks)
            zone.chunks = self._pass_summarize(zone.chunks, target_tokens, zone_key)
            result.events.append(self._event(zone_key, "summarize", pre_summary, zone.chunks))

            if zone.token_count <= target_tokens:
                zone.compressed = True
                result.zones_compressed.append(zone_key)
                allocator.update_usage(zone_key, zone.token_count)
                continue

            # Pass 4: Hard truncation (last resort — ALWAYS logged)
            pre_truncate = list(zone.chunks)
            floor_tokens = budget.floor_tokens
            zone.chunks = self._pass_truncate(zone.chunks, max(target_tokens, floor_tokens))
            evt = self._event(zone_key, "truncate", pre_truncate, zone.chunks)
            result.events.append(evt)
            result.hard_truncations += 1
            zone.compressed = True
            result.zones_compressed.append(zone_key)
            allocator.update_usage(zone_key, zone.token_count)

            # Verify trust preservation after all passes
            violations = verify_preservation(original_chunks, zone.chunks)
            result.trust_violations.extend(violations)

        # Check if total is still over budget after compressing all managed zones
        total_used = sum(z.token_count for z in zones.values())
        if total_used > allocator.total_tokens:
            # Both managed zones at floor — escalate
            result.escalated = True

        result.total_tokens_saved = sum(e.tokens_saved for e in result.events)
        return result

    def _pass_dedup(self, chunks: List[ContentChunk]) -> List[ContentChunk]:
        """Pass 1: Remove exact and near-duplicate chunks.

        v1: exact text match + substring containment.
        Keep the version with higher trust tier on collision.
        """
        seen_texts = {}  # normalized text -> chunk
        result = []

        for chunk in chunks:
            normalized = chunk.text.strip().lower()
            if not normalized:
                continue

            # Check exact match
            if normalized in seen_texts:
                existing = seen_texts[normalized]
                # Keep higher trust tier
                if chunk.trust_tier > existing.trust_tier:
                    result.remove(existing)
                    result.append(chunk)
                    seen_texts[normalized] = chunk
                continue

            # Check substring containment (longer contains shorter)
            is_contained = False
            for seen_text, seen_chunk in list(seen_texts.items()):
                if normalized in seen_text:
                    is_contained = True
                    break
                if seen_text in normalized:
                    # Current chunk is longer, replace the shorter
                    result.remove(seen_chunk)
                    del seen_texts[seen_text]
                    break

            if not is_contained:
                result.append(chunk)
                seen_texts[normalized] = chunk

        return result

    def _pass_relevance(self, chunks: List[ContentChunk], zone_key: str) -> List[ContentChunk]:
        """Pass 2: Filter by relevance to current task.

        v1: keyword overlap scoring. Embedding-based deferred.
        Threshold is stricter for RETRIEVED_CONTEXT than CONVERSATION_HISTORY.
        """
        if not self._task_keywords:
            return chunks  # no task context = can't filter

        threshold = 0.1 if zone_key == ContextZone.RETRIEVED_CONTEXT.value else 0.05

        scored = []
        for chunk in chunks:
            words = set(chunk.text.lower().split())
            overlap = len(words & self._task_keywords)
            score = overlap / len(self._task_keywords) if self._task_keywords else 0
            chunk.relevance_score = score
            scored.append((score, chunk))

        return [chunk for score, chunk in scored if score >= threshold]

    def _pass_summarize(self, chunks: List[ContentChunk], target_tokens: int,
                        zone_key: str) -> List[ContentChunk]:
        """Pass 3: Tiered summarization.

        v1: keep chunks from the front (most recent for history, most relevant
        for retrieved) until target is reached. LLM-based rolling summary deferred.
        """
        if zone_key == ContextZone.CONVERSATION_HISTORY.value:
            # For history: keep most recent (tail), drop oldest (head)
            chunks = list(reversed(chunks))

        result = []
        running_total = 0
        for chunk in chunks:
            if running_total + chunk.token_count <= target_tokens:
                result.append(chunk)
                running_total += chunk.token_count
                chunk.compressed = True
                if "summarize" not in chunk.compression_passes:
                    chunk.compression_passes.append("summarize")

        if zone_key == ContextZone.CONVERSATION_HISTORY.value:
            result = list(reversed(result))

        return result

    def _pass_truncate(self, chunks: List[ContentChunk], target_tokens: int) -> List[ContentChunk]:
        """Pass 4: Hard truncation. Last resort. ALWAYS logged.

        Removes from the lowest-relevance end until target is met.
        """
        # Sort by relevance (lowest first for removal)
        sorted_chunks = sorted(chunks, key=lambda c: c.relevance_score)

        # Remove lowest-relevance until under target
        keep = list(chunks)
        for chunk in sorted_chunks:
            current = sum(c.token_count for c in keep)
            if current <= target_tokens:
                break
            if chunk in keep:
                keep.remove(chunk)

        for chunk in keep:
            chunk.compressed = True
            if "truncate" not in chunk.compression_passes:
                chunk.compression_passes.append("truncate")

        return keep

    def _event(self, zone: str, pass_name: str,
               before: List[ContentChunk], after: List[ContentChunk]) -> CompressionEvent:
        tokens_before = sum(c.token_count for c in before)
        tokens_after = sum(c.token_count for c in after)
        return CompressionEvent(
            zone=zone,
            pass_name=pass_name,
            chunks_before=len(before),
            chunks_after=len(after),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tokens_saved=tokens_before - tokens_after,
        )
