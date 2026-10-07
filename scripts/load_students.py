"""Load Annex C CSVs into SQLite: python scripts/load_students.py --dir test_students/

- loads whatever of courses.csv, students.csv, attendance.csv, results.csv exist, in FK order
- validates every row first; invalid rows are skipped and reported (never crashes the load)
- INSERT OR REPLACE -> idempotent; judge IDs (S9xxx) and JDG* courses are accepted
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import validation as V  # noqa: E402
from app.db.connection import get_conn, init_db  # noqa: E402

ORDER = ["courses", "students", "attendance", "results"]
COLS = {
    "courses": ["course_code", "course_name", "programme", "semester", "credits"],
    "students": ["student_id", "full_name", "programme", "batch_year", "current_semester", "cgpa", "active_backlogs"],
    "attendance": ["student_id", "course_code", "classes_held", "classes_attended"],
    "results": ["student_id", "course_code", "exam_session", "exam_type", "internal_marks", "external_marks",
                "total_marks", "max_marks", "result"],
}


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [{(k or "").strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
                for r in csv.DictReader(f)]


def _pass_pct() -> float | None:
    from datetime import date
    from app.tools.rule_tools import resolve_rule
    try:
        out, _ = resolve_rule("min_total_marks_pct", date.today())
        return float(out["rule"]["value"]) if out["status"] == "ok" else None
    except Exception:
        return None


def load_dir(folder: Path) -> dict:
    init_db()
    report: dict = {"dir": str(folder)}
    with get_conn() as c:
        students = {r[0] for r in c.execute("SELECT student_id FROM students")}
        courses = {r[0] for r in c.execute("SELECT course_code FROM courses")}
    pass_pct = _pass_pct()
    for table in ORDER:
        path = folder / f"{table}.csv"
        if not path.exists():
            continue
        loaded, skipped = 0, []
        rows = _read(path)
        with get_conn() as c:
            for n, r in enumerate(rows, start=2):
                if table == "students":
                    row, errs = V.validate_student(r)
                elif table == "courses":
                    row, errs = V.validate_course(r)
                elif table == "attendance":
                    row, errs = V.validate_attendance(r, students, courses)
                else:
                    row, errs = V.validate_result(r, students, courses, pass_pct)
                if errs:
                    skipped.append({"line": n, "errors": errs})
                    continue
                cols = COLS[table]
                c.execute(f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                          [row.get(k) for k in cols])
                loaded += 1
                if table == "students":
                    students.add(row["student_id"])
                elif table == "courses":
                    courses.add(row["course_code"])
        report[table] = {"rows": len(rows), "loaded": loaded, "skipped": len(skipped), "violations": skipped[:50]}
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="folder with students.csv / courses.csv / attendance.csv / results.csv")
    a = ap.parse_args()
    print(json.dumps(load_dir(Path(a.dir)), indent=2))
