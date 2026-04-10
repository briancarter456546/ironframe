"""Tests for Component 10: Knowledge Base Grounding (IF-REQ-013)."""
import tempfile
import os

from ironframe.kb.storage_v1_0 import KBStore, HashEmbedder
from ironframe.kb.freshness_v1_0 import check_freshness


def _temp_store(tmpdir):
    """Create a KBStore with a temp DB file inside tmpdir."""
    path = os.path.join(tmpdir, "test_kb.db")
    return KBStore(db_path=path, embedder=HashEmbedder())


def test_kb_write_and_retrieval_roundtrip(tmp_path):
    store = _temp_store(str(tmp_path))
    cid = store.insert_chunk("test content", source_class="analytical", entity_type="finding")
    result = store.get_chunk(cid)
    assert result is not None
    assert result["content"] == "test content"
    assert result["source_class"] == "analytical"
    store.close()


def test_freshness_tracking_records_timestamp(tmp_path):
    store = _temp_store(str(tmp_path))
    cid = store.insert_chunk("fresh data", source_class="analytical")
    chunk = store.get_chunk(cid)
    assert chunk["last_verified_at"] is not None
    assert chunk["freshness_status"] == "fresh"
    store.close()


def test_retrieval_returns_most_recent(tmp_path):
    store = _temp_store(str(tmp_path))
    store.insert_chunk("old entry", source_class="analytical", chunk_id="old-1")
    store.insert_chunk("new entry", source_class="analytical", chunk_id="new-1")
    results = store.search_chunks_semantic("entry", top_k=5)
    assert len(results) == 2
    chunk_ids = [r["chunk_id"] for r in results]
    assert "new-1" in chunk_ids
    store.close()


def test_freshness_check_stale():
    fc = check_freshness(
        entity_id="test-1",
        source_class="analytical",
        last_verified_at="2020-01-01T00:00:00+00:00",
    )
    assert fc.is_stale is True
    assert fc.freshness_status in ("stale", "expired")


def test_freshness_check_fresh():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    fc = check_freshness(
        entity_id="test-2",
        source_class="analytical",
        last_verified_at=now,
    )
    assert fc.is_stale is False
    assert fc.freshness_status == "fresh"
