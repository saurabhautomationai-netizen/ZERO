from __future__ import annotations

from zero_core.memory import (
    VectorDocument,
    VectorRAGStore,
    cosine_similarity,
    default_embedder,
)


def test_default_embedder_and_cosine():
    v1 = default_embedder("finance budget transactions spending")
    v2 = default_embedder("personal spending on subscriptions")
    v3 = default_embedder("completely unrelated astronomy galaxy star")

    assert len(v1) == 256
    sim_related = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert sim_related > sim_unrelated


def test_vector_rag_store_indexing_and_search():
    rag = VectorRAGStore()
    assert rag.count() == 0

    rag.add_document(
        doc_id="doc_finance",
        text="Finance agent handles subscriptions, budgeting, and bank statements.",
        metadata={"domain": "finance"},
    )
    rag.add_document(
        doc_id="doc_trading",
        text="Trading agent interfaces with MetaTrader 5 and analyzes signal states.",
        metadata={"domain": "trading"},
    )
    rag.add_document(
        doc_id="doc_coding",
        text="Python backend architect specializes in FastAPI and database schemas.",
        metadata={"domain": "engineering"},
    )

    assert rag.count() == 3

    # Query finance
    results = rag.search(query="How much did I spend on subscriptions?", k=2)
    assert len(results) >= 1
    top_doc, score = results[0]
    assert top_doc.doc_id == "doc_finance"
    assert top_doc.metadata["domain"] == "finance"
    assert score > 0.0

    # Query with metadata filter
    filtered = rag.search(
        query="expert in schemas",
        k=2,
        filter_metadata={"domain": "engineering"},
    )
    assert len(filtered) == 1
    assert filtered[0][0].doc_id == "doc_coding"


def test_vector_rag_store_empty_and_clear():
    rag = VectorRAGStore()
    assert rag.search("test query") == []

    rag.add_document("doc1", "sample text")
    assert rag.count() == 1
    rag.clear()
    assert rag.count() == 0
