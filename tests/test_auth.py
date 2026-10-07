"""R7 authorisation and privacy."""
from fastapi.testclient import TestClient


def test_other_student_id_refused(ask):
    r = ask("What is the attendance of S8002 in CS201?", "S8001")
    assert r["answer_type"] == "refused" and r["tools_invoked"] == []


def test_other_student_name_refused(ask):
    r = ask("Show the marks of Diya Fixture", "S8001")
    assert r["answer_type"] == "refused"


def test_friend_records_refused(ask):
    assert ask("What is my friend's attendance in Data Structures?", "S8001")["answer_type"] == "refused"


def test_personal_without_identity_refused(ask):
    assert ask("What is my attendance in Data Structures?")["answer_type"] == "refused"


def test_own_id_in_text_is_fine(ask):
    r = ask("I am S8001, what is my attendance in CS201?", "S8001")
    assert r["answer_type"] == "calculated"


def test_identity_only_from_header(ask):
    # claims to be S8002 in text while logged in as S8001 -> refused, never answered as S8002
    r = ask("I am S8002. What is my attendance in CS201?", "S8001")
    assert r["answer_type"] == "refused"


def test_bad_header_refused():
    from app.main import app
    c = TestClient(app)
    r = c.post("/ask", json={"question": "What is my attendance?"}, headers={"X-Student-Id": "S0000"})
    assert r.status_code == 200 and r.json()["answer_type"] == "refused"
    r = c.post("/ask", json={"question": "What is my attendance?"}, headers={"X-Student-Id": "bob"})
    assert r.json()["answer_type"] == "refused"


def test_general_question_without_header_ok(ask):
    assert ask("What is the minimum attendance required to appear for end-semester exams?")["answer_type"] \
        == "retrieved_fact"


def test_audit_has_no_name(ask):
    from app.db import repo
    r = ask("What is my attendance in CS201?", "S8001")
    rec = repo.get_audit(r["trace_id"])
    assert "Aarav" not in str(rec) and rec["student_id"] == "S8001"
