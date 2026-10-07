"""Seed curated rules (data/rules_seed.csv) into rule_registry.

Each rule must reference a doc_id present in the source register (else rejected) and a clause.
Empty effective dates / scope are inherited from the source document. Rows with value TODO are skipped.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import repo  # noqa: E402
from app.db.connection import init_db  # noqa: E402
from app.tools.catalog import PARAMETERS  # noqa: E402


def seed_rules(path: Path | None = None) -> dict:
    s = get_settings()
    path = path or s.path(s.rules_seed_csv)
    init_db()
    out = {"file": str(path), "seeded": [], "rejected": []}
    if not path.exists():
        out["rejected"].append("rules seed file not found")
        return out
    with path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k: (v or "").strip() for k, v in r.items() if k}
            rid = r.get("rule_id")
            if not rid or rid.startswith("#"):
                continue
            src = repo.get_source(r.get("source_doc_id", ""))
            why = None
            if not src:
                why = f"source_doc_id {r.get('source_doc_id')} not in source register"
            elif r.get("parameter") not in PARAMETERS:
                why = f"parameter {r.get('parameter')} not in vocabulary"
            elif not r.get("value") or r["value"].upper() == "TODO":
                why = "value not filled in (TODO)"
            elif not r.get("source_section"):
                why = "source_section missing"
            if why:
                out["rejected"].append({"rule_id": rid, "reason": why})
                continue
            repo.upsert_rule({
                **r, "operator": r.get("operator") or PARAMETERS[r["parameter"]]["operator"],
                "scope_programmes": r.get("scope_programmes") or src["scope_programmes"] or "ALL",
                "scope_batches": r.get("scope_batches") or src["scope_batches"] or "ALL",
                "effective_from": r.get("effective_from") or src["effective_from"],
                "effective_to": r.get("effective_to") or src["effective_to"] or "",
                "extraction_method": "seed"})
            out["seeded"].append(rid)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None)
    a = ap.parse_args()
    print(json.dumps(seed_rules(Path(a.file) if a.file else None), indent=2))
