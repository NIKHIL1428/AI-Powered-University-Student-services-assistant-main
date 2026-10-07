"""Section 6 contract: response keys/types, every answer_type reachable, health/audit/sources endpoints."""
from fastapi.testclient import TestClient

from app.config import NOT_FOUND_MESSAGE
from app.guardrails.validator import ungrounded_numbers
from app.schemas.ask import AskResponse

REQUIRED = ["trace_id", "answer", "answer_type", "citations", "tools_invoked", "applied_rules",
            "conflicts_detected", "explanation", "as_of_date"]


def client():
    from app.main import app
    return TestClient(app)


def post(q, sid=None, as_of="2026-10-06"):
    h = {"X-Student-Id": sid} if sid else {}
    r = client().post("/ask", json={"question": q, "as_of_date": as_of}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_calculated_contract():
    b = post("Am I eligible for the end-sem exam in CS201?", "S8001")
    for k in REQUIRED:
        assert k in b
    AskResponse.model_validate(b)
    assert b["answer_type"] == "calculated" and b["as_of_date"] == "2026-10-06"
    t = {x["tool"]: x for x in b["tools_invoked"]}
    assert t["check_exam_eligibility"]["output"]["result"] == "ELIGIBLE"
    assert b["applied_rules"][0] == {"rule_id": "ATT-SYN-CIRC-01", "value": ">=80%", "source_doc_id": "SYN-CIRC-01"}
    c = b["citations"][0]
    assert set(c) == {"doc_id", "title", "section", "page", "version", "effective_from"}
    assert c["doc_id"] == "SYN-CIRC-01" and c["effective_from"] == "2026-08-01"


def test_all_answer_types_reachable():
    assert post("What is the minimum attendance required to appear for end-semester exams?")["answer_type"] \
        == "retrieved_fact"
    nf = post("What is the scholarship for studying in Antarctica?")
    assert nf["answer_type"] == "not_found" and nf["answer"] == NOT_FOUND_MESSAGE and nf["citations"] == []
    assert post("Am I eligible for the supplementary exam in Mathematics?", "S8001")["answer_type"] \
        == "clarification_needed"
    assert post("What are the marks of S8002?", "S8001")["answer_type"] == "refused"


def test_conflict_flagged_on_unresolvable_tie():
    """Two level-2 sources, same date, different values -> conflict_flagged, both cited."""
    from app.db import repo
    repo.upsert_source({"doc_id": "TIE-A", "title": "Tie A", "authority_level": 2, "doc_type": "circular",
                        "version": "1", "effective_from": "2031-01-01", "scope_programmes": "ALL",
                        "scope_batches": "ALL", "synthetic": "Y"})
    repo.upsert_source({"doc_id": "TIE-B", "title": "Tie B", "authority_level": 2, "doc_type": "circular",
                        "version": "1", "effective_from": "2031-01-01", "scope_programmes": "ALL",
                        "scope_batches": "ALL", "synthetic": "Y"})
    for d, v in (("TIE-A", "6.0"), ("TIE-B", "7.0")):
        repo.upsert_rule({"rule_id": f"PLC-CGPA-{d}", "parameter": "placement_min_cgpa", "operator": ">=",
                          "value": v, "effective_from": "2031-01-01", "source_doc_id": d, "source_section": "1",
                          "scope_programmes": "ALL", "scope_batches": "ALL", "extraction_method": "seed"})
    b = post("What is the minimum CGPA for placement?", as_of="2031-02-01")
    assert b["answer_type"] == "conflict_flagged"
    assert {c["doc_id"] for c in b["citations"]} == {"TIE-A", "TIE-B"}
    assert any(c["status"] == "unresolved" for c in b["conflicts_detected"])


def test_resolved_conflict_is_reported():
    b = post("What is the minimum attendance required to appear for end-semester exams?")
    assert ">=80%" in b["answer"]
    over = {c["overridden"]["doc_id"]: c["reason"] for c in b["conflicts_detected"] if c.get("overridden")}
    assert over["FIX-REG-2024"].startswith("step 2") and over["SYN-FAQ-01"].startswith("step 3")


def test_audit_endpoint():
    b = post("Am I eligible for placement?", "S8008")
    a = client().get(f"/audit/{b['trace_id']}").json()
    for k in ("trace_id", "timestamp", "student_id", "question_category", "sources_retrieved",
              "precedence_decision", "tools_invoked", "answer_type", "model", "llm_calls", "tokens", "latency_ms"):
        assert k in a
    assert a["tools_invoked"][0]["status"] == "ok" and "ms" in a["tools_invoked"][0]
    assert client().get("/audit/doesnotexist").status_code == 404


def test_health_and_sources():
    h = client().get("/health").json()
    assert h["api"] == "ok" and h["vector_store"]["chunks"] > 0 and h["sqlite"]["students"] >= 10
    assert h["llm"]["status"] == "mock"
    s = client().get("/sources").json()
    assert any(x["doc_id"] == "FIX-REG-2024" for x in s["sources"])
    assert all(r["source_doc_id"] and r["source_section"] for r in s["rules"])


def test_number_grounding_helper():
    assert ungrounded_numbers("minimum is 85%", "minimum is 75%") == ["85"]
    assert ungrounded_numbers("minimum is 75.0%", "minimum is 75%") == []
