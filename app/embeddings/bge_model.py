"""Sentence-transformers embeddings; bge-small (default) or MiniLM (eval comparison)."""
from functools import lru_cache

MODELS = {
    "bge": {"name": "BAAI/bge-small-en-v1.5",
            "query_prefix": "Represent this sentence for searching relevant passages: "},
    "minilm": {"name": "sentence-transformers/all-MiniLM-L6-v2", "query_prefix": ""},
}


@lru_cache(maxsize=2)
def _model(key: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODELS[key]["name"], device="cpu")


def embed_docs(texts: list[str], key: str) -> list[list[float]]:
    return _model(key).encode(texts, normalize_embeddings=True, batch_size=32).tolist()


def embed_query(text: str, key: str) -> list[float]:
    return _model(key).encode([MODELS[key]["query_prefix"] + text], normalize_embeddings=True)[0].tolist()
