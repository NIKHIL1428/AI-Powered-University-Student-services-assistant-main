"""Bootstrap: register every source in source_register.csv, seed curated rules, then ingest only
missing/changed documents (hash check) — so a restart never re-embeds or re-OCRs the corpus.

  python scripts/ingest_all.py [--force] [--extra bge:fixed,minilm:clause]
"""
import argparse
import csv
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import repo  # noqa: E402
from app.db.connection import init_db  # noqa: E402
from app.ingestion.pipeline import ingest_document  # noqa: E402
from app.schemas.source import SourceMetadata  # noqa: E402

log = logging.getLogger("uniassist.bootstrap")


def read_register() -> list[dict]:
    s = get_settings()
    p = s.path(s.register_csv)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8-sig") as f:
        return [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)
                if (r.get("doc_id") or "").strip() and not r["doc_id"].startswith("#")]


def ingest_all(force: bool = False, extra: list[tuple[str, str]] | None = None) -> list[dict]:
    from scripts.seed_rules import seed_rules
    s = get_settings()
    init_db()
    rows, metas, results = read_register(), [], []
    for r in rows:
        try:
            meta = SourceMetadata.model_validate(r)
        except ValidationError as e:
            results.append({"doc_id": r.get("doc_id"), "status": "invalid_metadata", "error": str(e)[:300]})
            continue
        metas.append((meta, r.get("file_name", "")))
        if not repo.get_source(meta.doc_id):        # register first so seeded rules can reference it
            repo.upsert_source({**meta.register_row(), "file_name": r.get("file_name", "")})
    seeded = seed_rules()
    for meta, fname in metas:
        path = s.path(s.docs_dir) / fname
        if not fname or not path.exists():
            results.append({"doc_id": meta.doc_id, "status": "missing_file", "file": str(path)})
            continue
        try:
            res = ingest_document(path, meta, force=force, update_csv=False, extra_collections=extra)
            results.append({k: res[k] for k in ("doc_id", "status", "chunks_indexed", "ocr_pages", "rules_extracted")}
                           | {"warnings": res.get("warnings", [])})
        except Exception as e:
            log.exception("ingest failed for %s", meta.doc_id)
            results.append({"doc_id": meta.doc_id, "status": "error", "error": str(e)})
    results.append({"rules_seed": {"seeded": len(seeded["seeded"]), "rejected": seeded["rejected"]}})
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--extra", default="", help="extra collections for eval, e.g. bge:fixed,minilm:clause")
    a = ap.parse_args()
    extra = [tuple(x.split(":")) for x in a.extra.split(",") if x]
    print(json.dumps(ingest_all(a.force, extra), indent=2))
