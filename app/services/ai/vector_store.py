"""
ChromaDB wrapper.

Stores per-organization 'brand voice' snippets, top-performing past posts,
and guidelines. When generating content we retrieve the most relevant items
and feed them to Mistral so output stays on-brand.

Uses Chroma's built-in embedding function by default. For higher quality you
can swap in Mistral embeddings (mistral-embed) via a custom embedding fn.
"""
from __future__ import annotations

import chromadb
from chromadb.config import Settings
from app.config import settings

_client = chromadb.PersistentClient(
    path=settings.CHROMA_PERSIST_DIR,
    settings=Settings(anonymized_telemetry=False)
)


def _collection(org_id: int):
    # one logical collection per org keeps tenant data isolated
    return _client.get_or_create_collection(name=f"org_{org_id}")


def add_brand_doc(org_id: int, doc_id: str, text: str, metadata: dict | None = None) -> None:
    _collection(org_id).upsert(
        ids=[doc_id],
        documents=[text],
        metadatas=[metadata or {}],
    )


def query_brand_context(org_id: int, query: str, k: int = 4) -> list[str]:
    col = _collection(org_id)
    if col.count() == 0:
        return []
    res = col.query(query_texts=[query], n_results=min(k, col.count()))
    docs = res.get("documents") or [[]]
    return docs[0]


def delete_brand_doc(org_id: int, doc_id: str) -> None:
    _collection(org_id).delete(ids=[doc_id])
