"""Query router: intent -> allowlisted plan -> RAG / STRUCTURED / HYBRID path."""
from datetime import date

from app.db import repo
from app.graph.nodes import route_for
from app.router.query_router import detect_parameter, keyword_classify


def test_route_for():
    assert route_for(["retrieve"]) == "rag"
    assert route_for(["find_course", "get_attendance"]) == "structured"
    assert route_for(["find_course", "check_exam_eligibility", "retrieve"]) == "hybrid"
    assert route_for(["retrieve", "resolve_rule"]) == "hybrid"


def _route(ask, q, sid=None):
    r = ask(q, sid)
    return repo.get_audit(r["trace_id"])["route"], r


def test_paths_end_to_end(ask):
    assert _route(ask, "How do I apply for the supplementary exam?")[0] == "rag"
    assert _route(ask, "What is my attendance in Data Structures?", "S8001")[0] == "structured"
    assert _route(ask, "Am I eligible for the end-sem exam in CS201?", "S8001")[0] == "hybrid"
    assert _route(ask, "What is the minimum attendance required to appear for end-semester exams?")[0] == "hybrid"


def test_refusal_short_circuits_before_routing(ask):
    route, r = _route(ask, "What is the attendance of S8002?", "S8001")
    assert route is None and r["answer_type"] == "refused" and r["tools_invoked"] == []


def test_keyword_intents():
    assert keyword_classify("How do I apply for the supplementary exam?").intent == "procedure"
    assert keyword_classify("Where should I submit my medical certificate?").intent == "procedure"
    assert keyword_classify("What is my attendance in DS?").intent == "personal_data"
    assert keyword_classify("Am I eligible for placement?").intent == "personal_eligibility"
    assert keyword_classify("I failed DS. If I pass the supplementary, will I be eligible for placement?").intent \
        == "multi_step"
    assert keyword_classify("What is the minimum attendance required?").intent == "policy_fact"


def test_parameter_detection_needs_a_threshold_question():
    assert detect_parameter("What is the minimum attendance required?") == "min_attendance_pct"
    assert detect_parameter("Can the Dean condone a shortage of attendance on medical grounds?") is None
    assert detect_parameter("Can the Dean relax the minimum attendance requirement?") == "attendance_relaxation_dean_pct"
    assert detect_parameter("How many times can attendance relaxation be granted?") == "max_attendance_relaxations"


def test_tool_allowlist_blocks_unplanned_tools(ask):
    r = ask("What is the minimum attendance required to appear for end-semester exams?")
    assert {t["tool"] for t in r["tools_invoked"]} <= {"resolve_rule"}
