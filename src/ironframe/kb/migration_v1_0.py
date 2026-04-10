# ============================================================================
# ironframe/kb/migration_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Migration Bridge: knowledge_base.db -> ironframe KB
#
# REVIEW GATE: First produces a type mapping (old type -> new entity_type)
# as dry-run output for Brian to review BEFORE any data moves.
# No writes until mapping approved.
#
# knowledge_base.db stays READ-ONLY during migration. Not deleted.
# Existing content becomes Authoritative Domain class entities.
# ============================================================================

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ironframe.kb.storage_v1_0 import KBStore


# ============================================================================
# TYPE MAPPING: old KB type -> new Iron Frame entity_type
#
# This mapping is the FIRST output of migration. Brian reviews it before
# any data moves. Surprises here are better found before 873 nodes are written.
# ============================================================================

_DEFAULT_TYPE_MAP = {
    # Trading/domain types
    "finding": "Insight",
    "correction": "DomainStandard",
    "system": "Component",
    "strategy": "DomainStandard",
    "rule": "ComplianceRule",
    "principle": "DomainStandard",
    "hypothesis": "Insight",
    "observation": "Insight",
    "metric": "DomainStandard",
    "signal": "DomainStandard",
    "regime": "DomainStandard",
    "benchmark": "DomainStandard",
    "warning": "Insight",

    # Infrastructure types
    "tool": "Tool",
    "skill": "Skill",
    "hook": "Hook",
    "config": "Component",
    "service": "Component",
    "dashboard": "Component",

    # Documentation types
    "reference": "SourceDocument",
    "note": "Insight",
    "article": "SourceDocument",
    "research": "SourceDocument",

    # Entity types (from Brian's migration review)
    "entity_tool": "Tool",
    "entity_system": "Component",
    "bug": "DriftEvent",
    "entity_person": "Insight",
    "entity_concept": "Insight",
    "entity_macro_concept": "Insight",
    "entity_org": "Insight",
    "entity_project": "Insight",
    "entity_asset": "DomainStandard",
    "entity_asset_class": "DomainStandard",
    "assumption": "Insight",
    "topic": "Insight",
    "joke_attempt": "Insight",
    "method_preference": "DomainStandard",
}

# Fallback for unmapped types
_FALLBACK_ENTITY_TYPE = "Insight"


def get_type_mapping() -> Dict[str, str]:
    """Return the current type mapping. Editable before migration runs."""
    return dict(_DEFAULT_TYPE_MAP)


def analyze_source(old_db_path: str = "knowledge_base.db") -> Dict[str, Any]:
    """Analyze the source KB WITHOUT writing anything.

    This is the REVIEW GATE: produces a mapping report for Brian to
    inspect before any data moves.
    """
    path = Path(old_db_path)
    if not path.exists():
        return {"error": f"Source DB not found: {old_db_path}"}

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row

    # Count nodes by type
    type_counts = {}
    rows = conn.execute("SELECT type, COUNT(*) as cnt FROM nodes GROUP BY type").fetchall()
    for row in rows:
        type_counts[row["type"]] = row["cnt"]

    # Count edges by relation
    rel_counts = {}
    rows = conn.execute("SELECT relation, COUNT(*) as cnt FROM edges GROUP BY relation").fetchall()
    for row in rows:
        rel_counts[row["relation"]] = row["cnt"]

    # Build mapping report
    type_map = get_type_mapping()
    mapping_report = []
    unmapped_types = []

    for old_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        new_type = type_map.get(old_type, _FALLBACK_ENTITY_TYPE)
        is_mapped = old_type in type_map
        mapping_report.append({
            "old_type": old_type,
            "new_entity_type": new_type,
            "count": count,
            "explicitly_mapped": is_mapped,
        })
        if not is_mapped:
            unmapped_types.append(old_type)

    # Totals
    total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    total_tags = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]

    conn.close()

    return {
        "source_db": old_db_path,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "total_tags": total_tags,
        "type_counts": type_counts,
        "relation_counts": rel_counts,
        "mapping_report": mapping_report,
        "unmapped_types": unmapped_types,
        "unmapped_count": sum(type_counts.get(t, 0) for t in unmapped_types),
        "review_required": len(unmapped_types) > 0,
        "message": (
            f"REVIEW GATE: {total_nodes} nodes, {total_edges} edges. "
            f"{len(unmapped_types)} unmapped types ({sum(type_counts.get(t, 0) for t in unmapped_types)} nodes). "
            f"Review mapping_report before running migrate()."
        ),
    }


def migrate(
    old_db_path: str = "knowledge_base.db",
    store: Optional[KBStore] = None,
    type_map: Optional[Dict[str, str]] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Migrate knowledge_base.db into the Iron Frame KB store.

    dry_run=True (default): analyze only, no writes.
    dry_run=False: actually write to the new store.

    Old DB stays read-only. New entities get source_class='authoritative_domain'.
    """
    if dry_run:
        return analyze_source(old_db_path)

    path = Path(old_db_path)
    if not path.exists():
        return {"error": f"Source DB not found: {old_db_path}"}

    if store is None:
        store = KBStore()

    if type_map is None:
        type_map = get_type_mapping()

    old_conn = sqlite3.connect(str(path))
    old_conn.row_factory = sqlite3.Row

    # Migrate nodes -> kb_chunks + kb_entities
    nodes_migrated = 0
    nodes_skipped = 0
    old_id_to_new: Dict[int, str] = {}  # old node.id -> new entity_id

    rows = old_conn.execute("SELECT * FROM nodes").fetchall()
    for row in rows:
        old_id = row["id"]
        old_type = row["type"] or ""
        entity_type = type_map.get(old_type, _FALLBACK_ENTITY_TYPE)
        content = row["content"] or ""
        title = row["title"] or ""

        if not content.strip():
            nodes_skipped += 1
            continue

        # Write as chunk (for vector search)
        chunk_id = store.insert_chunk(
            content=content,
            source_class="authoritative_domain",
            entity_type=entity_type,
            source_document_id=f"legacy_kb_node_{old_id}",
            metadata={
                "legacy_id": old_id,
                "legacy_type": old_type,
                "title": title,
                "domain": row["domain"] or "",
                "confidence": row["confidence"],
                "source": row["source"] or "",
            },
            chunk_id=f"legacy_{old_id}",
        )

        # Write as entity (for graph traversal)
        entity_id = store.insert_entity(
            entity_type=entity_type,
            source_class="authoritative_domain",
            name=title,
            properties={
                "legacy_id": old_id,
                "legacy_type": old_type,
                "domain": row["domain"] or "",
                "confidence": row["confidence"],
                "content_preview": content[:200],
            },
            entity_id=f"legacy_{old_id}",
        )

        old_id_to_new[old_id] = entity_id
        nodes_migrated += 1

    # Migrate edges -> kb_relationships
    edges_migrated = 0
    edges_skipped = 0

    edge_rows = old_conn.execute("SELECT * FROM edges").fetchall()
    for edge in edge_rows:
        from_id = edge["source_id"]
        to_id = edge["target_id"]
        relation = edge["relation"] or "RELATED_TO"

        from_entity = old_id_to_new.get(from_id)
        to_entity = old_id_to_new.get(to_id)

        if not from_entity or not to_entity:
            edges_skipped += 1
            continue

        store.insert_relationship(
            from_entity_id=from_entity,
            rel_type=relation.upper().replace(" ", "_"),
            to_entity_id=to_entity,
            properties={
                "legacy_edge_id": edge["id"],
                "weight": edge["weight"],
                "context": edge["context"] or "",
            },
        )
        edges_migrated += 1

    old_conn.close()

    # Validation
    new_chunks = store.count_chunks()
    new_entities = store.count_entities()
    new_rels = store.count_relationships()

    return {
        "status": "completed",
        "nodes_migrated": nodes_migrated,
        "nodes_skipped": nodes_skipped,
        "edges_migrated": edges_migrated,
        "edges_skipped": edges_skipped,
        "new_store_chunks": new_chunks,
        "new_store_entities": new_entities,
        "new_store_relationships": new_rels,
        "source_preserved": True,  # old DB not modified
    }
