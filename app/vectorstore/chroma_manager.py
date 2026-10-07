"""ChromaDB wrapper. One collection per (embedding model, chunk strategy).

CHROMA_MODE=local (default): PersistentClient on disk - what the guide mandates and what works offline.
CHROMA_MODE=cloud: chromadb.CloudClient with CHROMA_API_KEY / CHROMA_TENANT / CHROMA_DATABASE from .env.
"""
from functools import lru_cache

from app.config import get_settings


@lru_cache(maxsize=1)
def _client():
    import logging
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
    import chromadb
    from chromadb.config import Settings as CS
    s = get_settings()
    if s.chroma_mode == "cloud":
        if not (s.chroma_api_key and s.chroma_tenant and s.chroma_database):
            raise RuntimeError("CHROMA_MODE=cloud needs CHROMA_API_KEY, CHROMA_TENANT and CHROMA_DATABASE")
        return chromadb.CloudClient(api_key=s.chroma_api_key, tenant=s.chroma_tenant, database=s.chroma_database)
    p = s.path(s.chroma_path)
    p.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(p), settings=CS(anonymized_telemetry=False))


def mode() -> str:
    return get_settings().chroma_mode


def collection_name(embed: str | None = None, strategy: str | None = None) -> str:
    s = get_settings()
    embed, strategy = embed or s.embed_model, strategy or s.chunk_strategy
    return f"chunks_{embed}" + ("" if strategy == "clause" else f"_{strategy}")


def get_collection(embed: str | None = None, strategy: str | None = None):
    return _client().get_or_create_collection(collection_name(embed, strategy), metadata={"hnsw:space": "cosine"})


def delete_doc(doc_id: str, embed=None, strategy=None) -> None:
    get_collection(embed, strategy).delete(where={"doc_id": doc_id})


def upsert(ids, embeddings, documents, metadatas, embed=None, strategy=None) -> None:
    col = get_collection(embed, strategy)
    for i in range(0, len(ids), 256):
        col.upsert(ids=ids[i:i + 256], embeddings=embeddings[i:i + 256],
                   documents=documents[i:i + 256], metadatas=metadatas[i:i + 256])


def count(embed=None, strategy=None) -> int:
    return get_collection(embed, strategy).count()


def doc_chunk_count(doc_id: str, embed=None, strategy=None) -> int:
    return len(get_collection(embed, strategy).get(where={"doc_id": doc_id}, include=[])["ids"])


def get_section(doc_id: str, section: str, embed=None, strategy=None) -> list[dict]:
    """Chunks of one clause (exact, then by clause prefix) - used to cite the clause behind a rule."""
    col = get_collection(embed, strategy)
    r = col.get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
    rows = [{"chunk_id": i, "text": d, "meta": m, "score": 1.0}
            for i, d, m in zip(r["ids"], r["documents"], r["metadatas"])]
    exact = [c for c in rows if str(c["meta"].get("section")) == section]
    if exact:
        return exact
    return [c for c in rows if str(c["meta"].get("section", "")).startswith(section + ".")
            or section.startswith(str(c["meta"].get("section", "")) + ".")]


def query(embedding: list[float], k: int, embed=None, strategy=None) -> list[dict]:
    col = get_collection(embed, strategy)
    n = col.count()
    if n == 0:
        return []
    r = col.query(query_embeddings=[embedding], n_results=min(k, n),
                  include=["documents", "metadatas", "distances"])
    return [{"chunk_id": i, "text": d, "meta": m, "score": round(1 - dist, 4)}
            for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])]
