# ============================================================================
# ironframe/kb/storage_v1_0.py - v1.0
# Last updated: 2026-04-06
# ============================================================================
# Component 10a: SQLite Vector + Graph Store
#
# SQLite for both stores — portable, no external service. Deliberate v1.
#
# Vector store: kb_chunks with 384-dim embeddings (all-MiniLM-L6-v2)
# Graph store: kb_entities + kb_relationships (adjacency tables)
#
# Embedding interface: pluggable. HashEmbedder for testing, MiniLM when available.
#
# Cosine similarity (addition #1): Python-side with numpy.
# v2 migration trigger: KB > ~50K chunks.
# ============================================================================

import hashlib
import json
import sqlite3
import struct
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 default


# ============================================================================
# EMBEDDING PROVIDERS (pluggable)
# ============================================================================

class EmbeddingProvider(ABC):
    """Pluggable embedding interface. Replaceable without schema change
    as long as dimension stays 384."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        ...

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        ...


class HashEmbedder(EmbeddingProvider):
    """Deterministic hash-based pseudo-embeddings for testing.

    NOT suitable for semantic search — produces consistent but semantically
    meaningless vectors. Use for schema validation, migration testing, and
    unit tests where embedding quality doesn't matter.
    """

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed(self, text: str) -> List[float]:
        h = hashlib.sha512(text.encode("utf-8")).digest()
        # Expand hash to fill 384 floats
        values = []
        for i in range(self.dimension):
            byte_val = h[i % len(h)]
            values.append((byte_val / 255.0) * 2.0 - 1.0)  # normalize to [-1, 1]
        return values

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(t) for t in texts]


class MiniLMEmbedder(EmbeddingProvider):
    """all-MiniLM-L6-v2 via sentence-transformers. 384 dimensions.

    Falls back to HashEmbedder if sentence-transformers not installed.
    """

    def __init__(self):
        self._model = None
        self._fallback = None
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            self._fallback = HashEmbedder()

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed(self, text: str) -> List[float]:
        if self._model:
            return self._model.encode(text).tolist()
        return self._fallback.embed(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if self._model:
            return self._model.encode(texts).tolist()
        return self._fallback.embed_batch(texts)


# ============================================================================
# EMBEDDING SERIALIZATION
# ============================================================================

def _serialize_embedding(embedding: List[float]) -> bytes:
    """Pack float list into bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def _deserialize_embedding(blob: bytes) -> List[float]:
    """Unpack bytes back to float list."""
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


# ============================================================================
# COSINE SIMILARITY (addition #1: Python-side with numpy)
# ============================================================================

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors. Python-side computation.

    v1: acceptable for ~873 nodes. v2 migration trigger: ~50K chunks.
    """
    try:
        import numpy as np
        a_np = np.array(a, dtype=np.float32)
        b_np = np.array(b, dtype=np.float32)
        dot = np.dot(a_np, b_np)
        norm_a = np.linalg.norm(a_np)
        norm_b = np.linalg.norm(b_np)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))
    except ImportError:
        # Fallback without numpy
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


def cosine_similarity_batch(query: List[float], candidates: List[Tuple[str, List[float]]]) -> List[Tuple[str, float]]:
    """Compute cosine similarity of query against all candidates.

    Returns list of (chunk_id, similarity) sorted by similarity desc.
    """
    results = []
    for chunk_id, embedding in candidates:
        sim = cosine_similarity(query, embedding)
        results.append((chunk_id, sim))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ============================================================================
# KB STORE
# ============================================================================

class KBStore:
    """SQLite-backed vector + graph store for Iron Frame KB.

    Single database file with three main tables:
    kb_chunks (vector store), kb_entities (graph nodes), kb_relationships (graph edges).
    """

    def __init__(self, db_path: str = "ironframe/kb/ironframe_kb.db",
                 embedder: Optional[EmbeddingProvider] = None):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._embedder = embedder or HashEmbedder()
        self._conn = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                chunk_id TEXT PRIMARY KEY,
                source_class TEXT NOT NULL,
                entity_type TEXT,
                content TEXT NOT NULL,
                embedding BLOB,
                source_document_id TEXT,
                created_at TEXT,
                last_verified_at TEXT,
                freshness_status TEXT DEFAULT 'fresh',
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS kb_entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                source_class TEXT NOT NULL,
                name TEXT,
                properties TEXT DEFAULT '{}',
                created_at TEXT,
                last_verified_at TEXT,
                status TEXT DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS kb_relationships (
                rel_id TEXT PRIMARY KEY,
                from_entity_id TEXT NOT NULL,
                rel_type TEXT NOT NULL,
                to_entity_id TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at TEXT,
                FOREIGN KEY (from_entity_id) REFERENCES kb_entities(entity_id),
                FOREIGN KEY (to_entity_id) REFERENCES kb_entities(entity_id)
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_source_class ON kb_chunks(source_class);
            CREATE INDEX IF NOT EXISTS idx_chunks_entity_type ON kb_chunks(entity_type);
            CREATE INDEX IF NOT EXISTS idx_chunks_status ON kb_chunks(status);
            CREATE INDEX IF NOT EXISTS idx_entities_type ON kb_entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_entities_source ON kb_entities(source_class);
            CREATE INDEX IF NOT EXISTS idx_rel_from ON kb_relationships(from_entity_id);
            CREATE INDEX IF NOT EXISTS idx_rel_to ON kb_relationships(to_entity_id);
            CREATE INDEX IF NOT EXISTS idx_rel_type ON kb_relationships(rel_type);
        """)
        conn.commit()

    @property
    def embedder(self) -> EmbeddingProvider:
        return self._embedder

    # --- Chunk operations (vector store) ---

    def insert_chunk(
        self,
        content: str,
        source_class: str,
        entity_type: str = "",
        source_document_id: str = "",
        metadata: Optional[Dict] = None,
        chunk_id: str = "",
        status: str = "active",
    ) -> str:
        """Insert a content chunk with embedding."""
        if not chunk_id:
            chunk_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc).isoformat()
        embedding = self._embedder.embed(content)
        emb_blob = _serialize_embedding(embedding)

        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO kb_chunks
               (chunk_id, source_class, entity_type, content, embedding,
                source_document_id, created_at, last_verified_at, freshness_status,
                status, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'fresh', ?, ?)""",
            (chunk_id, source_class, entity_type, content, emb_blob,
             source_document_id, now, now, status,
             json.dumps(metadata or {}, ensure_ascii=True)),
        )
        conn.commit()
        return chunk_id

    def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM kb_chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def search_chunks_semantic(self, query: str, top_k: int = 10,
                                source_classes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Semantic search: embed query, compute cosine similarity against all chunks.

        v1: loads all candidate embeddings into memory. Acceptable for ~873 nodes.
        """
        query_embedding = self._embedder.embed(query)
        conn = self._get_conn()

        # Build SQL filter
        where = "WHERE status = 'active'"
        params = []
        if source_classes:
            placeholders = ",".join("?" for _ in source_classes)
            where += f" AND source_class IN ({placeholders})"
            params.extend(source_classes)

        rows = conn.execute(
            f"SELECT chunk_id, content, source_class, entity_type, embedding, "
            f"freshness_status, last_verified_at, metadata FROM kb_chunks {where}",
            params,
        ).fetchall()

        # Load embeddings and compute similarity
        candidates = []
        row_map = {}
        for row in rows:
            row_dict = dict(row)
            emb = _deserialize_embedding(row_dict["embedding"])
            candidates.append((row_dict["chunk_id"], emb))
            row_map[row_dict["chunk_id"]] = row_dict

        ranked = cosine_similarity_batch(query_embedding, candidates)

        results = []
        for chunk_id, score in ranked[:top_k]:
            row_dict = row_map[chunk_id]
            row_dict["relevance_score"] = round(score, 4)
            row_dict.pop("embedding", None)  # don't return raw embedding
            results.append(row_dict)

        return results

    def count_chunks(self, source_class: str = "") -> int:
        conn = self._get_conn()
        if source_class:
            return conn.execute(
                "SELECT COUNT(*) FROM kb_chunks WHERE source_class = ?", (source_class,)
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]

    # --- Entity operations (graph store) ---

    def insert_entity(
        self,
        entity_type: str,
        source_class: str,
        name: str = "",
        properties: Optional[Dict] = None,
        entity_id: str = "",
    ) -> str:
        if not entity_id:
            entity_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO kb_entities
               (entity_id, entity_type, source_class, name, properties, created_at, last_verified_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entity_id, entity_type, source_class, name,
             json.dumps(properties or {}, ensure_ascii=True), now, now),
        )
        conn.commit()
        return entity_id

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM kb_entities WHERE entity_id = ?", (entity_id,)).fetchone()
        return dict(row) if row else None

    def insert_relationship(
        self,
        from_entity_id: str,
        rel_type: str,
        to_entity_id: str,
        properties: Optional[Dict] = None,
    ) -> str:
        rel_id = str(uuid.uuid4())[:12]
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO kb_relationships
               (rel_id, from_entity_id, rel_type, to_entity_id, properties, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rel_id, from_entity_id, rel_type, to_entity_id,
             json.dumps(properties or {}, ensure_ascii=True), now),
        )
        conn.commit()
        return rel_id

    def traverse(self, entity_id: str, rel_type: str = "", direction: str = "outgoing",
                 max_hops: int = 3) -> List[Dict[str, Any]]:
        """Graph traversal from an entity. Configurable max_hops (addition #2).

        direction: 'outgoing' (from->to), 'incoming' (to->from), 'both'
        """
        conn = self._get_conn()
        visited = set()
        results = []
        frontier = [(entity_id, 0, [])]  # (entity_id, depth, path)

        while frontier:
            current_id, depth, path = frontier.pop(0)
            if current_id in visited or depth > max_hops:
                continue
            visited.add(current_id)

            entity = self.get_entity(current_id)
            if entity and depth > 0:
                results.append({**entity, "depth": depth, "path": path})

            if depth >= max_hops:
                continue

            # Find neighbors
            where_clauses = []
            if direction in ("outgoing", "both"):
                where_clauses.append("from_entity_id = ?")
            if direction in ("incoming", "both"):
                where_clauses.append("to_entity_id = ?")

            for clause in where_clauses:
                query = f"SELECT * FROM kb_relationships WHERE {clause}"
                params = [current_id]
                if rel_type:
                    query += " AND rel_type = ?"
                    params.append(rel_type)

                rels = conn.execute(query, params).fetchall()
                for rel in rels:
                    rel_dict = dict(rel)
                    neighbor = (rel_dict["to_entity_id"] if clause.startswith("from")
                                else rel_dict["from_entity_id"])
                    if neighbor not in visited:
                        new_path = path + [{"rel_type": rel_dict["rel_type"],
                                            "from": rel_dict["from_entity_id"],
                                            "to": rel_dict["to_entity_id"]}]
                        frontier.append((neighbor, depth + 1, new_path))

        return results

    def count_entities(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM kb_entities").fetchone()[0]

    def count_relationships(self) -> int:
        return self._get_conn().execute("SELECT COUNT(*) FROM kb_relationships").fetchone()[0]

    def summary(self) -> Dict[str, Any]:
        return {
            "chunks": self.count_chunks(),
            "entities": self.count_entities(),
            "relationships": self.count_relationships(),
            "embedding_dim": self._embedder.dimension,
            "db_path": str(self._db_path),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
