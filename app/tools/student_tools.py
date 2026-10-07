"""Student-data lookups. `student_id` always comes from the auth context, never from the LLM."""
import re
from decimal import ROUND_HALF_UP, Decimal

from app.db import repo


def attendance_pct(attended: int, held: int) -> float:
    if held <= 0:
        return 0.0
    return float((Decimal(attended) * 100 / Decimal(held)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in {"and", "of", "the", "in", "for", "to"}]


def find_course(student_id: str, query: str) -> dict:
    """Resolve a course name/code within the student's own courses.

    Returns {"status": "ok", "course_code", "course_name"} or
            {"status": "ambiguous"|"not_found", "candidates": [...]}.
    """
    courses = repo.courses_for_student(student_id)
    q = (query or "").strip()
    if not q:
        return {"status": "not_found", "query": q, "candidates": []}
    by_code = [c for c in courses if c["course_code"].lower() == q.lower().replace(" ", "")]
    if by_code:
        c = by_code[0]
        return {"status": "ok", "course_code": c["course_code"], "course_name": c["course_name"]}
    qt = _tokens(q)
    exact = [c for c in courses if c["course_name"].lower() == q.lower()]
    matches = exact or [c for c in courses if qt and all(
        any(ct.startswith(t) or t.startswith(ct) for ct in _tokens(c["course_name"])) for t in qt)]
    if len(matches) > 1:
        # prefer courses the student actually has records for
        with_records = {r["course_code"] for r in repo.get_attendance(student_id)} | \
                       {r["course_code"] for r in repo.get_results(student_id)}
        narrowed = [c for c in matches if c["course_code"] in with_records]
        if len(narrowed) == 1:
            matches = narrowed
    if len(matches) == 1:
        c = matches[0]
        return {"status": "ok", "course_code": c["course_code"], "course_name": c["course_name"]}
    return {"status": "ambiguous" if matches else "not_found", "query": q,
            "candidates": [{"course_code": c["course_code"], "course_name": c["course_name"]} for c in matches]}


def get_student_profile(student_id: str) -> dict:
    s = repo.get_student(student_id)
    if not s:
        return {"status": "not_found"}
    return {"status": "ok", "student_id": s["student_id"], "programme": s["programme"],
            "batch_year": s["batch_year"], "current_semester": s["current_semester"],
            "cgpa": s["cgpa"], "active_backlogs": s["active_backlogs"]}


def get_attendance(student_id: str, course_code: str | None = None) -> dict:
    rows = repo.get_attendance(student_id, course_code)
    out = [{"course_code": r["course_code"], "course_name": r["course_name"],
            "classes_held": r["classes_held"], "classes_attended": r["classes_attended"],
            "attendance_pct": attendance_pct(r["classes_attended"], r["classes_held"])} for r in rows]
    if course_code:
        if not out:
            return {"status": "no_record", "course_code": course_code}
        return {"status": "ok", **out[0]}
    return {"status": "ok" if out else "no_record", "courses": out}


def get_results(student_id: str, course_code: str | None = None, exam_type: str | None = None) -> dict:
    rows = repo.get_results(student_id, course_code, exam_type)
    return {"status": "ok" if rows else "no_record", "course_code": course_code, "results": rows}
