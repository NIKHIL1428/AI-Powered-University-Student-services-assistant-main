"""Convert the team's generated CSVs (data/csv) to the exact Annex C schema in data/synthetic.

Fixes found during review (all mechanical, logged, no values invented):
  students.program            -> programme
  results.exam_type ("2026 MAY") -> exam_session
  results.result_type (REGULAR/SUPPLEMENTARY) -> exam_type
  results.pass_marks (40 of a 100-mark paper) -> dropped; max_marks = 100 (pass threshold lives in rule_registry)
"""
import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def convert(src: Path, dst: Path, max_marks: int = 100) -> list[str]:
    dst.mkdir(parents=True, exist_ok=True)
    log = []
    for name in ("students", "courses", "attendance", "results"):
        rows = list(csv.DictReader((src / f"{name}.csv").open(encoding="utf-8-sig")))
        if name == "students" and rows and "program" in rows[0] and "programme" not in rows[0]:
            rows = [{("programme" if k == "program" else k): v for k, v in r.items()} for r in rows]
            log.append("students: renamed column program -> programme")
        if name == "results" and rows and "result_type" in rows[0]:
            rows = [{"student_id": r["student_id"], "course_code": r["course_code"], "exam_session": r["exam_type"],
                     "exam_type": r["result_type"], "internal_marks": r["internal_marks"],
                     "external_marks": r["external_marks"], "total_marks": r["total_marks"],
                     "max_marks": str(max_marks), "result": r["result"]} for r in rows]
            log.append(f"results: exam_type->exam_session, result_type->exam_type, pass_marks dropped, "
                       f"max_marks={max_marks}")
        with (dst / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        log.append(f"{name}: {len(rows)} rows written")
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT.parent / "data" / "csv"))
    ap.add_argument("--dst", default=str(ROOT / "data" / "synthetic"))
    a = ap.parse_args()
    print("\n".join(convert(Path(a.src), Path(a.dst))))
