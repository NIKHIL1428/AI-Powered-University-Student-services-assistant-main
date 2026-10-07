"""Query-time retrieval. No date filter here: upcoming docs must be visible to the precedence engine."""
from datetime import date

from app.config import get_settings
from app.precedence.engine import parse_supersedes
from app.precedence.models import SourceCandidate
from app.vectorstore import chroma_manager as vector_store
from app.embeddings.bge_model import embed_query


def retrieve(question: str, k: int | None = None, embed: str | None = None, strategy: str | None = None) -> list[dict]:
    s = get_settings()
    embed = embed or s.embed_model
    return vector_store.query(embed_query(question, embed), k or s.top_k, embed, strategy)


def _int_date(v) -> date | None:
    if not v:
        return None
    v = str(int(v))
    return date(int(v[:4]), int(v[4:6]), int(v[6:8]))


def to_candidate(chunk: dict) -> SourceCandidate:
    m = chunk["meta"]
    return SourceCandidate(
        key=chunk["chunk_id"], doc_id=m["doc_id"], section=str(m.get("section", "")),
        authority_level=int(m.get("authority_level", 4)),
        effective_from=_int_date(m.get("effective_from")), effective_to=_int_date(m.get("effective_to")),
        supersedes=parse_supersedes(m.get("supersedes")),
        scope_programmes=m.get("scope_programmes", "ALL"), scope_batches=m.get("scope_batches", "ALL"),
        score=chunk["score"], payload=chunk)
