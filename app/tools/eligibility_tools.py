"""Eligibility checks. Every threshold comes from rule_registry via resolve_rule — no constants here.

Comparisons use integer/Decimal arithmetic so 'exactly at threshold' is never lost to float error.
"""
import math
from datetime import date
from decimal import Decimal

from app.db import repo
from app.tools.rule_tools import resolve_rule
from app.tools.student_tools import attendance_pct


def _rule(parameter: str, as_of: date, student: dict) -> tuple[dict | None, dict]:
    out, _ = resolve_rule(parameter, as_of, student)
    return (out.get("rule") if out["status"] == "ok" else None), out


def _no_rule(parameter: str, out: dict) -> dict:
    return {"result": "UNKNOWN", "status": out["status"],
            "reason": f"no applicable rule for {parameter} on {out['as_of_date']}"
                      + (" (conflicting sources)" if out["status"] == "conflict" else ""),
            "rule_lookup": out}


def _latest(rows: list[dict], exam_type: str | None = None) -> dict | None:
    rows = [r for r in rows if not exam_type or r["exam_type"] == exam_type]
    return sorted(rows, key=lambda r: (r["exam_session"], r["exam_type"] == "SUPPLEMENTARY"))[-1] if rows else None


def check_exam_eligibility(student_id: str, course_code: str, as_of: date) -> dict:
    student = repo.get_student(student_id)
    rule, out = _rule("min_attendance_pct", as_of, student)
    if not rule:
        return _no_rule("min_attendance_pct", out)
    detained = [r for r in repo.get_results(student_id, course_code) if r["result"] == "DETAINED"]
    att = repo.get_attendance(student_id, course_code)
    if not att:
        return {"result": "UNKNOWN", "status": "no_record", "course_code": course_code, "rule_id": rule["rule_id"]}
    held, attended = att[0]["classes_held"], att[0]["classes_attended"]
    min_pct = Decimal(rule["value"])
    eligible = Decimal(attended) * 100 >= min_pct * held
    res = {"course_code": course_code, "classes_held": held, "classes_attended": attended,
           "attendance_pct": attendance_pct(attended, held), "required_pct": float(min_pct),
           "rule_id": rule["rule_id"], "source_doc_id": rule["source_doc_id"],
           "source_section": rule["source_section"]}
    if detained:
        return {**res, "result": "DETAINED",
                "reason": f"record shows DETAINED in {detained[-1]['exam_session']}"}
    if eligible:
        return {**res, "result": "ELIGIBLE", "classes_short": 0}
    # classes needed if every further class is attended: (a+x)*100 >= p*(h+x)
    need = (min_pct * held - Decimal(attended) * 100) / (100 - min_pct) if min_pct < 100 else None
    shortfall = math.ceil(min_pct * held / 100) - attended   # vs classes already held
    out = {**res, "result": "NOT_ELIGIBLE", "classes_short": int(shortfall),
           "additional_classes_needed_if_all_attended": int(math.ceil(need)) if need is not None else None}
    relax = relaxation_analysis(attended, held, min_pct, as_of, student)
    if relax:
        out["relaxation"] = relax
    return out


def relaxation_analysis(attended: int, held: int, min_pct: Decimal, as_of: date, student: dict) -> dict | None:
    """What-if: could a relaxation make the student eligible? Every number comes from rule_registry."""
    dean, _ = _rule("attendance_relaxation_dean_pct", as_of, student)
    comm, _ = _rule("attendance_relaxation_committee_pct", as_of, student)
    floor, _ = _rule("min_attendance_after_relaxation_pct", as_of, student)
    if not dean:
        return None
    a100 = Decimal(attended) * 100
    floor_pct = Decimal(floor["value"]) if floor else Decimal(0)
    dean_min = max(min_pct - Decimal(dean["value"]), floor_pct)
    comm_min = max(dean_min - Decimal(comm["value"]), floor_pct) if comm else dean_min
    if a100 >= dean_min * held:
        outcome, needed = "ELIGIBLE_IF_DEAN_RELAXES", [dean["rule_id"]]
    elif comm and a100 >= comm_min * held:
        outcome, needed = "ELIGIBLE_IF_DEAN_AND_COMMITTEE_RELAX", [dean["rule_id"], comm["rule_id"]]
    else:
        outcome, needed = "NOT_ELIGIBLE_EVEN_WITH_RELAXATION", [r["rule_id"] for r in (dean, comm, floor) if r]
    return {"outcome": outcome, "min_with_dean_relaxation_pct": float(dean_min),
            "min_with_committee_relaxation_pct": float(comm_min),
            "floor_after_relaxation_pct": float(floor_pct) if floor else None,
            "rule_ids": needed, "all_rule_ids": [r["rule_id"] for r in (dean, comm, floor) if r]}


def check_supplementary_eligibility(student_id: str, course_code: str, as_of: date) -> dict:
    student = repo.get_student(student_id)
    rule, out = _rule("supplementary_allowed_results", as_of, student)
    if not rule:
        return _no_rule("supplementary_allowed_results", out)
    allowed = {v.strip().upper() for v in rule["value"].replace(",", ";").split(";") if v.strip()}
    rows = repo.get_results(student_id, course_code)
    latest = _latest(rows)
    if not latest:
        return {"result": "UNKNOWN", "status": "no_record", "course_code": course_code, "rule_id": rule["rule_id"]}
    res = {"course_code": course_code, "latest_result": latest["result"], "exam_session": latest["exam_session"],
           "exam_type": latest["exam_type"], "total_marks": latest["total_marks"], "max_marks": latest["max_marks"],
           "allowed_results": sorted(allowed), "rule_id": rule["rule_id"],
           "source_doc_id": rule["source_doc_id"], "source_section": rule["source_section"]}
    pass_rule, _ = _rule("min_total_marks_pct", as_of, student)
    if pass_rule and latest["total_marks"] is not None and latest["max_marks"]:
        res["pass_mark_pct"] = float(pass_rule["value"])
        res["pass_rule_id"] = pass_rule["rule_id"]
        res["marks_pct"] = round(latest["total_marks"] * 100 / latest["max_marks"], 2)
    if latest["result"] in allowed:
        return {**res, "result": "ELIGIBLE", "reason": f"latest result {latest['result']} is in {sorted(allowed)}"}
    return {**res, "result": "NOT_ELIGIBLE",
            "reason": f"latest result {latest['result']} is not in {sorted(allowed)}"}


def check_placement_eligibility(student_id: str, as_of: date, assume_pass: list[str] | None = None) -> dict:
    student = repo.get_student(student_id)
    cgpa_rule, o1 = _rule("placement_min_cgpa", as_of, student)
    bk_rule, o2 = _rule("placement_max_backlogs", as_of, student)
    if not cgpa_rule and not bk_rule:
        return _no_rule("placement_min_cgpa", o1)
    backlogs = student["active_backlogs"]
    assumptions: list[str] = []
    for code in assume_pass or []:
        latest = _latest(repo.get_results(student_id, code))
        if latest and latest["result"] in {"FAIL", "ABSENT"} and backlogs > 0:
            backlogs -= 1
            assumptions.append(f"{code} assumed PASSED in supplementary -> active backlogs {backlogs + 1} -> {backlogs}")
        elif latest:
            assumptions.append(f"{code}: latest result is {latest['result']}, so assuming a pass changes nothing")
    if assume_pass:
        assumptions.append("CGPA assumed unchanged (grade points of the supplementary are not modelled)")
    failing, applied = [], []
    cgpa = Decimal(str(student["cgpa"]))
    if cgpa_rule:
        applied.append(cgpa_rule["rule_id"])
        if not cgpa >= Decimal(cgpa_rule["value"]):
            failing.append(f"CGPA {student['cgpa']} < required {cgpa_rule['value']}")
    else:
        assumptions.append("no applicable CGPA rule found; CGPA criterion not checked")
    if bk_rule:
        applied.append(bk_rule["rule_id"])
        if not backlogs <= int(Decimal(bk_rule["value"])):
            failing.append(f"active backlogs {backlogs} > allowed {bk_rule['value']}")
    else:
        assumptions.append("no applicable backlog rule found; backlog criterion not checked")
    return {"result": "NOT_ELIGIBLE" if failing else "ELIGIBLE", "cgpa": student["cgpa"],
            "active_backlogs": student["active_backlogs"], "active_backlogs_considered": backlogs,
            "required_min_cgpa": cgpa_rule["value"] if cgpa_rule else None,
            "allowed_max_backlogs": bk_rule["value"] if bk_rule else None,
            "failing_criteria": failing, "assumptions": assumptions,
            "rule_id": ";".join(applied), "rule_ids": applied,
            "source_doc_id": (cgpa_rule or bk_rule)["source_doc_id"],
            "source_section": (cgpa_rule or bk_rule)["source_section"]}
