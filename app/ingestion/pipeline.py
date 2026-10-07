"""ingest_document: file + Annex B metadata -> OCR/text -> clean -> chunks -> Chroma -> rules -> source register."""
import csv
import logging
import threading
from pathlib import Path

from app.config import get_settings
from app.db import repo
from app.guardrails.injection import is_suspicious
from app.guardrails.pii import redact_pages
from app.ingestion.chunker import chunk_clauses, chunk_fixed
from app.ingestion.text_cleaner import clean_text, strip_repeating_lines
from app.ingestion.document_loader import extract_pages, file_hash
from app.ingestion.rule_extractor import extract_rules
from app.vectorstore import chroma_manager as vector_store
from app.embeddings.bge_model import embed_docs
from app.schemas.source import SourceMetadata

log = logging.getLogger("uniassist.ingest")
_lock = threading.Lock()   # one ingest at a time (Chroma + SQLite writes)

REGISTER_FIELDS = ["doc_id", "title", "issuer", "authority_level", "doc_type", "version", "effective_from",
                   "effective_to", "supersedes", "scope_programmes", "scope_batches", "provenance",
                   "retrieved_on", "synthetic", "file_name"]


def _date_int(d) -> int:
    return int(d.strftime("%Y%m%d")) if d else 0


def _chunk_meta(meta: SourceMetadata, ch, conf: float | None) -> dict:
    return {"doc_id": meta.doc_id, "title": meta.title, "issuer": meta.issuer,
            "authority_level": meta.authority_level, "doc_type": meta.doc_type, "version": meta.version,
            "effective_from": _date_int(meta.effective_from), "effective_to": _date_int(meta.effective_to),
            "supersedes": meta.supersedes or "", "scope_programmes": meta.scope_programmes,
            "scope_batches": meta.scope_batches, "section": ch.section, "heading": ch.heading,
            "page": ch.page, "synthetic": meta.synthetic, "ocr_confidence": float(conf if conf is not None else 100.0),
            "suspicious": is_suspicious(ch.text)}


def build_chunks(meta: SourceMetadata, pages, strategy: str):
    texts = strip_repeating_lines([clean_text(p.text) for p in pages])
    pairs = [(p.page, t) for p, t in zip(pages, texts)]
    return chunk_clauses(meta.doc_id, pairs) if strategy == "clause" else chunk_fixed(meta.doc_id, pairs)


def index_chunks(meta: SourceMetadata, chunks, conf_by_page: dict, embed: str, strategy: str) -> None:
    vector_store.delete_doc(meta.doc_id, embed, strategy)
    if not chunks:
        return
    ctx = [f"{meta.title} | section {c.section} {c.heading}\n{c.text}" for c in chunks]
    vector_store.upsert([c.chunk_id for c in chunks], embed_docs(ctx, embed), [c.text for c in chunks],
                        [_chunk_meta(meta, c, conf_by_page.get(c.page)) for c in chunks], embed, strategy)


def append_register_csv(meta: SourceMetadata, file_name: str) -> None:
    s = get_settings()
    path = s.path(s.register_csv)
    rows = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("doc_id") != meta.doc_id]
    rows.append({**meta.register_row(), "file_name": file_name})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REGISTER_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def ingest_document(path: Path, meta: SourceMetadata, data: bytes | None = None, force: bool = False,
                    update_csv: bool = True, extra_collections: list[tuple[str, str]] | None = None) -> dict:
    s = get_settings()
    data = data if data is not None else path.read_bytes()
    h = file_hash(data)
    with _lock:
        prev = repo.get_source(meta.doc_id)
        if (not force and prev and prev.get("file_hash") == h
                and vector_store.doc_chunk_count(meta.doc_id) > 0):
            return {"doc_id": meta.doc_id, "chunks_indexed": prev["chunks_indexed"], "status": "unchanged",
                    "ocr_pages": prev["ocr_pages"], "rules_extracted": 0, "warnings": []}

        warnings: list[str] = []
        pages = extract_pages(path, data, warnings)
        # personal-data gate: student lists (names / roll numbers) never reach chunks, embeddings or the LLM
        redacted, pii = redact_pages([p.text for p in pages])
        for p, t in zip(pages, redacted):
            p.text = t
        if pii["flagged"]:
            warnings.append(f"personal data redacted: {pii['rolls_before']} roll number(s), "
                            f"{pii['lines_removed']} list line(s) removed")
        conf_by_page = {p.page: p.confidence for p in pages if p.ocr}
        chunks = build_chunks(meta, pages, s.chunk_strategy)
        index_chunks(meta, chunks, conf_by_page, s.embed_model, s.chunk_strategy)
        for embed, strategy in extra_collections or []:
            index_chunks(meta, build_chunks(meta, pages, strategy), conf_by_page, embed, strategy)

        suspicious = [c.chunk_id for c in chunks if is_suspicious(c.text)]
        if suspicious:
            warnings.append(f"{len(suspicious)} chunk(s) contain instruction-like text; flagged as suspicious "
                            f"and masked at answer time")
        rules, rw = extract_rules(meta, [c for c in chunks if c.chunk_id not in set(suspicious)])
        warnings += rw
        for r in rules:
            repo.upsert_rule(r)

        repo.upsert_source({**meta.register_row(), "file_name": path.name, "file_hash": h, "pages": len(pages),
                            "ocr_pages": sum(p.ocr for p in pages), "chunks_indexed": len(chunks),
                            "ingested_at": repo.now_iso()})
        if update_csv:
            append_register_csv(meta, path.name)
        if not chunks:
            warnings.append("no text extracted (scanned document without OCR available?)")
        log.info("ingested %s: %d chunks, %d rules", meta.doc_id, len(chunks), len(rules))
        return {"doc_id": meta.doc_id, "chunks_indexed": len(chunks),
                "status": "updated" if prev and prev.get("file_hash") else "ingested",
                "ocr_pages": sum(p.ocr for p in pages), "rules_extracted": len(rules),
                "rules": [{"rule_id": r["rule_id"], "parameter": r["parameter"], "value": r["value"],
                           "source_section": r["source_section"], "method": r["extraction_method"]} for r in rules],
                "warnings": warnings}
