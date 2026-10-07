"""Validate Annex C CSVs (schema + logical + cross-table constraints) and report violations and edge-case coverage.

  python scripts/validate_synthetic_data.py --dir data/synthetic [--out docs/validation_output.txt]

Row-level checks are shared with the loader (app/db/validation.py). Thresholds for edge-case coverage are read from
the rule registry seed (never hard-coded).
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import validation as V  # noqa: E402

REQUIRED = {
    "students": ["student_id", "full_name", "programme", "batch_year", "current_semester", "cgpa", "active_backlogs"],
    "courses": ["course_code", "course_name", "programme", "semester", "credits"],
    "attendance": ["student_id", "course_code", "classes_held", "classes_attended"],
    "results": ["student_id", "course_code", "exam_session", "exam_type", "internal_marks", "external_marks",
                "total_marks", "max_marks", "result"],
}


def read(p: Path) -> tuple[list[str], list[dict]]:
    with p.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def seed_value(rules_csv: Path, parameter: str) -> float | None:
    if not rules_csv.exists():
        return None
    for r in csv.DictReader(rules_csv.open(encoding="utf-8-sig")):
        if r.get("parameter") == parameter and r.get("value", "").replace(".", "", 1).isdigit():
            return float(r["value"])
    return None


def main(folder: Path, rules_csv: Path) -> list[str]:
    out: list[str] = [f"Validation of {folder}"]
    errors = 0
    data = {}
    for t, cols in REQUIRED.items():
        p = folder / f"{t}.csv"
        if not p.exists():
            out.append(f"[{t}] MISSING FILE")
            errors += 1
            continue
        header, rows = read(p)
        missing = [c for c in cols if c not in header]
        out.append(f"[{t}] {len(rows)} rows; columns ok" if not missing else f"[{t}] MISSING COLUMNS {missing}")
        errors += bool(missing)
        data[t] = rows
    students = {r["student_id"] for r in data.get("students", [])}
    courses = {r["course_code"] for r in data.get("courses", [])}
    pass_pct = seed_value(rules_csv, "min_total_marks_pct")
    checks = {"students": lambda r: V.validate_student(r), "courses": lambda r: V.validate_course(r),
              "attendance": lambda r: V.validate_attendance(r, students, courses),
              "results": lambda r: V.validate_result(r, students, courses, pass_pct)}
    for t, fn in checks.items():
        bad = [(i + 2, e) for i, r in enumerate(data.get(t, [])) for _, e in [fn(r)] if e]
        errors += len(bad)
        out.append(f"[{t}] row violations: {len(bad)}")
        out += [f"    line {ln}: {'; '.join(e)}" for ln, e in bad[:20]]

    # cross-table consistency
    st = {r["student_id"]: r for r in data.get("students", [])}
    progs = {r["programme"] for r in data.get("students", [])}
    for c in data.get("courses", []):
        if c["programme"] not in progs:
            out.append(f"    WARN course {c['course_code']} programme '{c['programme']}' has no students")
    latest: dict[tuple, dict] = {}
    for r in sorted(data.get("results", []), key=lambda r: (r["exam_session"], r["exam_type"] == "SUPPLEMENTARY")):
        latest[(r["student_id"], r["course_code"])] = r
    open_backlogs = Counter(k[0] for k, r in latest.items() if r["result"] in ("FAIL", "ABSENT"))
    mismatch = [(sid, int(s["active_backlogs"]), open_backlogs.get(sid, 0)) for sid, s in st.items()
                if int(s["active_backlogs"]) < open_backlogs.get(sid, 0)]
    out.append(f"[cross] students with fewer active_backlogs than FAIL/ABSENT courses in results: {len(mismatch)}")
    out += [f"    {sid}: active_backlogs={a} but {b} open FAIL/ABSENT result(s)" for sid, a, b in mismatch]
    for (sid, cc), r in latest.items():
        regs = [x for x in data["results"] if x["student_id"] == sid and x["course_code"] == cc]
        if any(x["exam_type"] == "SUPPLEMENTARY" for x in regs) and \
                any(x["exam_type"] == "REGULAR" and x["result"] == "PASS" for x in regs):
            out.append(f"    WARN {sid} {cc}: SUPPLEMENTARY attempt after a REGULAR PASS")
    enrol = defaultdict(set)
    for a in data.get("attendance", []):
        enrol[a["student_id"]].add(a["course_code"])
    for c in data.get("courses", []):
        pass
    for a in data.get("attendance", []):
        s = st.get(a["student_id"])
        prog = next((c["programme"] for c in data["courses"] if c["course_code"] == a["course_code"]), None)
        if s and prog and prog != s["programme"]:
            out.append(f"    WARN {a['student_id']} ({s['programme']}) has attendance in {a['course_code']} ({prog})")

    # distributions + edge-case coverage
    out.append("[distribution] students per programme x batch: " + ", ".join(
        f"{k[0]} {k[1]}={v}" for k, v in sorted(Counter((s["programme"], s["batch_year"]) for s in st.values()).items())))
    out.append("[distribution] results: " + ", ".join(f"{k}={v}" for k, v in
                                                     Counter(r["result"] for r in data.get("results", [])).items()))
    att_min = seed_value(rules_csv, "min_attendance_pct")
    cg_min = seed_value(rules_csv, "placement_min_cgpa")
    cov = {}
    if att_min:
        at = [a for a in data.get("attendance", []) if int(a["classes_attended"]) * 100 == att_min * int(a["classes_held"])]
        below = [a for a in data.get("attendance", []) if int(a["classes_attended"]) + 1 == -(-att_min * int(a["classes_held"]) // 100)
                 and int(a["classes_attended"]) * 100 < att_min * int(a["classes_held"])]
        cov[f"attendance exactly {att_min:g}%"] = [f"{a['student_id']}/{a['course_code']}" for a in at]
        cov["attendance one class below"] = [f"{a['student_id']}/{a['course_code']}" for a in below]
    if pass_pct:
        cov["marks just below pass"] = [f"{r['student_id']}/{r['course_code']}" for r in data.get("results", [])
                                        if r["result"] == "FAIL" and r["max_marks"] and
                                        pass_pct * int(r["max_marks"]) / 100 - 2 <= int(r["total_marks"]) < pass_pct * int(r["max_marks"]) / 100]
    cov["ABSENT result"] = [f"{r['student_id']}/{r['course_code']}" for r in data.get("results", []) if r["result"] == "ABSENT"]
    cov["DETAINED result"] = [f"{r['student_id']}/{r['course_code']}" for r in data.get("results", []) if r["result"] == "DETAINED"]
    cov["multiple backlogs (>=2)"] = [sid for sid, s in st.items() if int(s["active_backlogs"]) >= 2]
    if cg_min:
        cov[f"CGPA exactly at placement cut-off {cg_min:g}"] = [sid for sid, s in st.items() if float(s["cgpa"]) == cg_min]
    out.append("[edge cases]")
    for k, v in cov.items():
        out.append(f"    {'OK ' if v else 'MISSING'} {k}: {', '.join(v[:8]) + (' ...' if len(v) > 8 else '') if v else '-'}")
    out.append(f"RESULT: {errors} hard violation(s)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/synthetic")
    ap.add_argument("--rules", default="data/rules_seed.csv")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    lines = main(ROOT / a.dir if not Path(a.dir).is_absolute() else Path(a.dir), ROOT / a.rules)
    text = "\n".join(lines)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
