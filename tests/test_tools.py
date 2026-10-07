"""Deterministic tools against fixture students. Thresholds always come from rule_registry."""
from datetime import date

from app.db import repo
from app.tools import eligibility_tools as ET
from app.tools import student_tools as ST

TODAY = date(2026, 10, 6)      # circular: 80% applies
JULY = date(2026, 7, 15)       # regulation: 75% applies


def test_exactly_at_threshold_eligible():
    r = ET.check_exam_eligibility("S8001", "CS201", TODAY)       # 32/40 = 80.0%
    assert r["result"] == "ELIGIBLE" and r["rule_id"] == "ATT-SYN-CIRC-01"


def test_one_class_below_not_eligible():
    r = ET.check_exam_eligibility("S8002", "CS201", TODAY)       # 31/40 = 77.5%
    assert r["result"] == "NOT_ELIGIBLE" and r["classes_short"] == 1


def test_30_of_40_vs_29_of_40_at_75():
    assert ET.check_exam_eligibility("S8003", "CS201", JULY)["result"] == "ELIGIBLE"     # 30/40 at 75%
    assert ET.check_exam_eligibility("S8003", "CS201", TODAY)["result"] == "NOT_ELIGIBLE"


def test_detained():
    assert ET.check_exam_eligibility("S8006", "CS202", TODAY)["result"] == "DETAINED"
    assert ET.check_supplementary_eligibility("S8006", "CS202", TODAY)["result"] == "NOT_ELIGIBLE"


def test_absent_and_fail_go_to_supplementary():
    assert ET.check_supplementary_eligibility("S8005", "MA201", TODAY)["result"] == "ELIGIBLE"
    r = ET.check_supplementary_eligibility("S8004", "CS201", TODAY)
    assert r["result"] == "ELIGIBLE" and r["marks_pct"] == 39.0 and r["pass_mark_pct"] == 40.0


def test_pass_not_eligible_for_supplementary():
    assert ET.check_supplementary_eligibility("S8001", "CS201", TODAY)["result"] == "NOT_ELIGIBLE"


def test_cgpa_exactly_at_cutoff():
    assert ET.check_placement_eligibility("S8008", TODAY)["result"] == "ELIGIBLE"      # 6.50
    assert ET.check_placement_eligibility("S8009", TODAY)["result"] == "NOT_ELIGIBLE"  # 6.49


def test_multiple_backlogs_and_what_if():
    r = ET.check_placement_eligibility("S8007", TODAY, ["CS201"])
    assert r["result"] == "NOT_ELIGIBLE" and r["active_backlogs_considered"] == 2
    r = ET.check_placement_eligibility("S8004", TODAY, ["CS201"])
    assert r["result"] == "ELIGIBLE" and any("assumed PASSED" in a for a in r["assumptions"])
    assert ET.check_placement_eligibility("S8004", TODAY)["result"] == "NOT_ELIGIBLE"


def test_attendance_pct_two_dp():
    assert ST.get_attendance("S8010", "IT201")["attendance_pct"] == 80.0
    assert ST.attendance_pct(2, 3) == 66.67


def test_ambiguous_course_needs_clarification():
    r = ST.find_course("S8001", "Mathematics")
    assert r["status"] == "ambiguous" and len(r["candidates"]) == 2
    assert ST.find_course("S8005", "Mathematics")["course_code"] == "MA201"   # only one with records
    assert ST.find_course("S8001", "cs201")["course_code"] == "CS201"
    assert ST.find_course("S8001", "Quantum Basket Weaving")["status"] == "not_found"


def test_registry_value_drives_result(monkeypatch):
    """Proves no constants: changing the registry value flips the decision."""
    real = repo.rules_for_parameter

    def patched(p):
        rows = real(p)
        return [{**r, "value": "77"} if r["rule_id"] == "ATT-SYN-CIRC-01" else r for r in rows]
    monkeypatch.setattr(repo, "rules_for_parameter", patched)
    assert ET.check_exam_eligibility("S8002", "CS201", TODAY)["result"] == "ELIGIBLE"   # 77.5 >= 77


def test_profile_has_no_name():
    assert "full_name" not in ST.get_student_profile("S8001")


def test_relaxation_what_if_uses_registry_rules():
    r = ET.check_exam_eligibility("S8002", "CS201", TODAY)          # 77.5% vs 80%, Dean may relax 10%
    assert r["result"] == "NOT_ELIGIBLE"
    assert r["relaxation"]["outcome"] == "ELIGIBLE_IF_DEAN_RELAXES"
    assert r["relaxation"]["rule_ids"] == ["ATT-RELAX-DEAN-01"]
    r = ET.check_exam_eligibility("S8006", "CS202", TODAY)          # DETAINED record wins over any relaxation
    assert r["result"] == "DETAINED"
