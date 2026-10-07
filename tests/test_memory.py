"""Session memory: follow-ups resolve from context; memory is bound to the header identity."""
import json
import uuid

from app.db import repo


def test_followup_inherits_intent(ask):
    sid = uuid.uuid4().hex
    first = ask("What is my attendance in Data Structures?", "S8010", session=sid)
    assert first["answer_type"] == "calculated" and "IT201" in first["answer"]
    second = ask("and in Computer Networks?", "S8010", session=sid)
    assert second["answer_type"] == "calculated" and "IT202" in second["answer"]
    rec = repo.get_audit(second["trace_id"])
    assert rec["memory_used"] is True and "follow-up" in rec["rewritten_question"]


def test_header_change_resets_memory(ask):
    sid = uuid.uuid4().hex
    ask("What is my attendance in Data Structures?", "S8010", session=sid)
    r = ask("and in Computer Networks?", "S8001", session=sid)
    rec = repo.get_audit(r["trace_id"])
    assert rec["memory_used"] is False
    assert any("different identity" in w for w in rec["warnings"])


def test_expired_session_is_stateless(ask):
    sid = uuid.uuid4().hex
    ask("What is my attendance in Data Structures?", "S8010", session=sid)
    from app.db.connection import get_conn
    with get_conn() as c:
        c.execute("UPDATE sessions SET updated_at = '2020-01-01T00:00:00Z' WHERE session_id = ?", (sid,))
    r = ask("and in Computer Networks?", "S8010", session=sid)
    assert repo.get_audit(r["trace_id"])["memory_used"] is False


def test_memory_stores_no_names(ask):
    sid = uuid.uuid4().hex
    ask("What is my attendance in Data Structures?", "S8010", session=sid)
    mem = repo.get_session(sid)["memory_json"]
    assert "Nisha" not in mem and json.loads(mem)["last_turns"]
