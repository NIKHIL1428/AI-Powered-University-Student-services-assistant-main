"""Annex C row validation shared by the loader and validate_synthetic_data.py.

Each validator returns (clean_row | None, [violations]). Logical constraints:
attended <= held; marks within range; total = internal + external; result consistent with marks.
"""
import re

PROGRAMMES_HINT = None
RESULTS = {"PASS", "FAIL", "ABSENT", "DETAINED"}
EXAM_TYPES = {"REGULAR", "SUPPLEMENTARY"}


def _int(v, name, errs, required=True):
    if v is None or str(v).strip() == "":
        if required:
            errs.append(f"{name} missing")
        return None
    try:
        f = float(v)
        if f != int(f):
            errs.append(f"{name} not an integer: {v}")
        return int(f)
    except ValueError:
        errs.append(f"{name} not a number: {v}")
        return None


def validate_student(r: dict) -> tuple[dict | None, list[str]]:
    e = []
    sid = (r.get("student_id") or "").strip().upper()
    if not re.fullmatch(r"S\d{4}", sid):
        e.append(f"student_id '{sid}' must be S + 4 digits")
    name = (r.get("full_name") or "").strip()
    if not name:
        e.append("full_name missing")
    prog = (r.get("programme") or "").strip()
    if not prog:
        e.append("programme missing")
    batch = _int(r.get("batch_year"), "batch_year", e)
    if batch is not None and not 2000 <= batch <= 2035:
        e.append(f"batch_year {batch} out of range")
    sem = _int(r.get("current_semester"), "current_semester", e)
    if sem is not None and not 1 <= sem <= 10:
        e.append(f"current_semester {sem} not in 1-10")
    try:
        cgpa = round(float(r.get("cgpa")), 2)
        if not 0 <= cgpa <= 10:
            e.append(f"cgpa {cgpa} not in 0-10")
    except (TypeError, ValueError):
        cgpa = None
        e.append(f"cgpa '{r.get('cgpa')}' invalid")
    bk = _int(r.get("active_backlogs"), "active_backlogs", e)
    if bk is not None and bk < 0:
        e.append("active_backlogs < 0")
    row = {**r, "student_id": sid, "full_name": name, "programme": prog, "batch_year": batch,
           "current_semester": sem, "cgpa": cgpa, "active_backlogs": bk}
    return (None if e else row), e


def validate_course(r: dict) -> tuple[dict | None, list[str]]:
    e = []
    code = (r.get("course_code") or "").strip().upper()
    if not code:
        e.append("course_code missing")
    if not (r.get("course_name") or "").strip():
        e.append("course_name missing")
    if not (r.get("programme") or "").strip():
        e.append("programme missing")
    sem = _int(r.get("semester"), "semester", e, required=False)
    cr = _int(r.get("credits"), "credits", e, required=False)
    if cr is not None and not 0 <= cr <= 10:
        e.append(f"credits {cr} out of range")
    row = {**r, "course_code": code, "course_name": (r.get("course_name") or "").strip(),
           "programme": (r.get("programme") or "").strip(), "semester": sem, "credits": cr}
    return (None if e else row), e


def validate_attendance(r: dict, students: set, courses: set) -> tuple[dict | None, list[str]]:
    e = []
    sid = (r.get("student_id") or "").strip().upper()
    cc = (r.get("course_code") or "").strip().upper()
    if sid not in students:
        e.append(f"unknown student_id {sid}")
    if cc not in courses:
        e.append(f"unknown course_code {cc}")
    held = _int(r.get("classes_held"), "classes_held", e)
    att = _int(r.get("classes_attended"), "classes_attended", e)
    if held is not None and held <= 0:
        e.append("classes_held must be > 0")
    if held is not None and att is not None and not 0 <= att <= held:
        e.append(f"classes_attended {att} not in 0..{held}")
    return (None if e else {"student_id": sid, "course_code": cc, "classes_held": held, "classes_attended": att}), e


def validate_result(r: dict, students: set, courses: set, pass_pct: float | None = None) -> tuple[dict | None, list[str]]:
    e = []
    sid = (r.get("student_id") or "").strip().upper()
    cc = (r.get("course_code") or "").strip().upper()
    if sid not in students:
        e.append(f"unknown student_id {sid}")
    if cc not in courses:
        e.append(f"unknown course_code {cc}")
    et = (r.get("exam_type") or "").strip().upper()
    if et not in EXAM_TYPES:
        e.append(f"exam_type '{et}' not REGULAR/SUPPLEMENTARY")
    res = (r.get("result") or "").strip().upper()
    if res not in RESULTS:
        e.append(f"result '{res}' not in {sorted(RESULTS)}")
    session = (r.get("exam_session") or "").strip()
    if not session:
        e.append("exam_session missing")
    i = _int(r.get("internal_marks"), "internal_marks", e, required=False)
    x = _int(r.get("external_marks"), "external_marks", e, required=False)
    t = _int(r.get("total_marks"), "total_marks", e, required=False)
    m = _int(r.get("max_marks"), "max_marks", e, required=False)
    if m is not None and m <= 0:
        e.append("max_marks must be > 0")
    for name, v in (("internal_marks", i), ("external_marks", x), ("total_marks", t)):
        if v is not None and v < 0:
            e.append(f"{name} < 0")
    if t is not None and m is not None and t > m:
        e.append(f"total_marks {t} > max_marks {m}")
    if i is not None and x is not None and t is not None and i + x != t:
        e.append(f"total_marks {t} != internal {i} + external {x}")
    if pass_pct is not None and t is not None and m and res in ("PASS", "FAIL"):
        passed = t * 100 >= pass_pct * m
        if res == "PASS" and not passed:
            e.append(f"result PASS but {t}/{m} below pass mark {pass_pct}%")
        if res == "FAIL" and passed:
            e.append(f"result FAIL but {t}/{m} meets pass mark {pass_pct}%")
    row = {"student_id": sid, "course_code": cc, "exam_session": session, "exam_type": et,
           "internal_marks": i, "external_marks": x, "total_marks": t, "max_marks": m, "result": res}
    return (None if e else row), e
