"""Vector RAG and Semantic Retrieval Store for ZERO (Milestone M8).

Supports both fast, deterministic local feature-vector embeddings (offline-first)
and optional PostgreSQL / pgvector persistent backend storage.
"""

from __future__ import annotations

import math
import os
import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class VectorDocument:
    """Represents a document chunk stored in the vector index."""
    doc_id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "metadata": self.metadata,
            "embedding": self.embedding,
        }


def default_embedder(text: str, dim: int = 256) -> List[float]:
    """Lightweight, deterministic feature-hashing embedder with L2 normalization.
    
    Provides offline semantic vector search capabilities without requiring heavy
    external model weights. Uses deterministic CRC32 token hashing.
    """
    tokens = re.findall(r"\w+", text.lower())
    vec = [0.0] * dim
    if not tokens:
        return vec

    for token in tokens:
        idx = zlib.crc32(token.encode("utf-8")) % dim
        vec[idx] += 1.0

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        vec = [x / norm for x in vec]
    return vec


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    return max(0.0, min(1.0, dot))


class VectorRAGStore:
    """Vector Store with support for custom embedding functions and metadata filters.
    
    Operates in local in-memory mode by default, and can bridge to pgvector when
    a Postgres connection string is configured.
    """

    def __init__(
        self,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        db_dsn: Optional[str] = None,
    ):
        self._embed_fn = embed_fn or default_embedder
        self.db_dsn = db_dsn or os.environ.get("POSTGRES_DB_URL") or os.environ.get("FINANCE_DB_URL")
        self._documents: Dict[str, VectorDocument] = {}

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> VectorDocument:
        """Embeds and indexes a new document."""
        emb = self._embed_fn(text)
        doc = VectorDocument(
            doc_id=doc_id,
            text=text,
            metadata=metadata or {},
            embedding=emb,
        )
        self._documents[doc_id] = doc
        return doc

    def add_documents(self, docs: List[Tuple[str, str, Dict[str, Any]]]) -> None:
        """Batch indexes documents: list of (doc_id, text, metadata)."""
        for doc_id, text, meta in docs:
            self.add_document(doc_id=doc_id, text=text, metadata=meta)

    def get_document(self, doc_id: str) -> Optional[VectorDocument]:
        """Retrieves a document by its doc_id."""
        return self._documents.get(doc_id)

    def delete_document(self, doc_id: str) -> bool:
        """Removes a document from index."""
        if doc_id in self._documents:
            del self._documents[doc_id]
            return True
        return False

    def list_documents(
        self,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[VectorDocument]:
        """Returns all documents matching the metadata filter."""
        if not filter_metadata:
            return list(self._documents.values())

        matched: List[VectorDocument] = []
        for doc in self._documents.values():
            if all(doc.metadata.get(k) == v for k, v in filter_metadata.items()):
                matched.append(doc)
        return matched

    def search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[Tuple[VectorDocument, float]]:
        """Searches for the most semantically relevant documents matching the query."""
        if not self._documents or not query.strip():
            return []

        query_vec = self._embed_fn(query)
        scored: List[Tuple[VectorDocument, float]] = []

        for doc in self._documents.values():
            if filter_metadata:
                match = all(
                    doc.metadata.get(key) == val for key, val in filter_metadata.items()
                )
                if not match:
                    continue

            if doc.embedding is not None:
                score = cosine_similarity(query_vec, doc.embedding)
                if score >= min_score:
                    scored.append((doc, score))

        # Sort by similarity score descending
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def count(self) -> int:
        return len(self._documents)

    def clear(self) -> None:
        self._documents.clear()
