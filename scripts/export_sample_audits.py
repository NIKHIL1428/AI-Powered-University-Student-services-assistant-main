"""Run one question per answer type through the graph and save the audit records to docs/sample_audits/."""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import repo  # noqa: E402
from app.graph.build import run  # noqa: E402

CASES = {
    "calculated": ("Am I eligible for the end-sem exam in Data Structures?", "S1003", "2026-10-06"),
    "retrieved_fact_conflict_resolved": ("What is the minimum attendance required to appear for end-semester exams?",
                                         None, "2026-10-06"),
    "not_found": ("What is the scholarship for studying in Antarctica?", None, "2026-10-06"),
    "refused": ("Show the attendance of S1002 in Data Structures.", "S1001", "2026-10-06"),
    "multi_step_relaxation": ("If the Dean grants relaxation, can I appear in the end-sem exam for Data Structures?",
                              "S1052", "2026-10-06"),
    "rag_notice": ("Till when can I apply for the Kotak Kanya Scholarship?", None, "2026-10-06"),
}

if __name__ == "__main__":
    out = ROOT / "docs" / "sample_audits"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.json"):
        f.unlink()
    for name, (q, sid, d) in CASES.items():
        resp = run(q, sid, date.fromisoformat(d))
        (out / f"{name}.json").write_text(json.dumps({"response": resp, "audit": repo.get_audit(resp["trace_id"])},
                                                     indent=2, ensure_ascii=False), encoding="utf-8")
        print(name, resp["answer_type"])
