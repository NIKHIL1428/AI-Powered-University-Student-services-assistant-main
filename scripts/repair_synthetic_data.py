"""Deterministic, logged repairs to the LLM-generated data (data/synthetic, Annex C schema).

Every change here is listed in docs/DATA_CARD.md ("What the LLM got wrong" / "Edge cases").
  R1  S1006 CS302: a SUPPLEMENTARY attempt after a REGULAR PASS is inconsistent. The student was ABSENT in CS301,
      so the supplementary attempt is moved to CS301 (marks unchanged: 18+21=39 -> FAIL).
  E1  Edge case missing: DETAINED. Added S1051 with CS301 attendance 22/40 (55%, below the 60% floor of
      clause 11.6 even after relaxation) and a DETAINED result.
  E2  Edge case: attendance exactly at the 60% floor (24/40) -> eligible only with Dean + committee relaxation. S1052.
Idempotent: running twice does not duplicate rows.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "synthetic"


def _rw(name):
    rows = list(csv.DictReader((D / f"{name}.csv").open(encoding="utf-8")))
    return rows, list(rows[0].keys())


def _save(name, rows, cols):
    with (D / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main() -> list[str]:
    log = []
    res, rc = _rw("results")
    for r in res:
        if r["student_id"] == "S1006" and r["course_code"] == "CS302" and r["exam_type"] == "SUPPLEMENTARY":
            r["course_code"] = "CS301"
            log.append("R1 S1006 supplementary attempt moved CS302 -> CS301")
    st, sc = _rw("students")
    att, ac = _rw("attendance")
    new_students = [
        {"student_id": "S1051", "full_name": "Student Fern", "programme": "B.Tech CSE", "batch_year": "2024",
         "current_semester": "5", "cgpa": "6.95", "active_backlogs": "1"},
        {"student_id": "S1052", "full_name": "Student Grove", "programme": "B.Tech CSE", "batch_year": "2024",
         "current_semester": "5", "cgpa": "7.40", "active_backlogs": "0"},
    ]
    new_att = [{"student_id": "S1051", "course_code": "CS301", "classes_held": "40", "classes_attended": "22"},
               {"student_id": "S1051", "course_code": "CS302", "classes_held": "40", "classes_attended": "33"},
               {"student_id": "S1052", "course_code": "CS301", "classes_held": "40", "classes_attended": "24"},
               {"student_id": "S1052", "course_code": "CS302", "classes_held": "40", "classes_attended": "34"}]
    new_res = [{"student_id": "S1051", "course_code": "CS301", "exam_session": "2026 MAY", "exam_type": "REGULAR",
                "internal_marks": "12", "external_marks": "0", "total_marks": "12", "max_marks": "100",
                "result": "DETAINED"},
               {"student_id": "S1051", "course_code": "CS302", "exam_session": "2026 MAY", "exam_type": "REGULAR",
                "internal_marks": "27", "external_marks": "45", "total_marks": "72", "max_marks": "100",
                "result": "PASS"}]
    have = {s["student_id"] for s in st}
    for s in new_students:
        if s["student_id"] not in have:
            st.append(s)
            log.append(f"E add student {s['student_id']}")
    key = lambda r: (r["student_id"], r["course_code"])
    have_a = {key(a) for a in att}
    att += [a for a in new_att if key(a) not in have_a]
    have_r = {(r["student_id"], r["course_code"], r["exam_session"], r["exam_type"]) for r in res}
    res += [r for r in new_res if (r["student_id"], r["course_code"], r["exam_session"], r["exam_type"]) not in have_r]
    _save("students", st, sc)
    _save("attendance", att, ac)
    _save("results", res, rc)
    log.append(f"students={len(st)} attendance={len(att)} results={len(res)}")
    return log


if __name__ == "__main__":
    print("\n".join(main()))
