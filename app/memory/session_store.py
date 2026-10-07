"""Session memory for follow-ups. Memory is context, never evidence and never identity.

- bound to the X-Student-Id that created it; a different header resets it (no cross-student leak)
- deterministic summary (no extra LLM call), last 3 turns, answers truncated to 200 chars, no names
- TTL from settings (default 30 min)
"""
from datetime import datetime, timedelta, timezone
import json

from app.config import get_settings
from app.db import repo
from app.guardrails.redact import redact

EMPTY = {"summary": "", "last_turns": [], "entities": {}}


def load(session_id: str | None, student_id: str | None) -> tuple[dict, list[str]]:
    """Returns (memory, warnings)."""
    if not session_id:
        return dict(EMPTY), []
    row = repo.get_session(session_id)
    if not row:
        return dict(EMPTY), []
    if (row["student_id"] or None) != (student_id or None):
        return dict(EMPTY), ["session belonged to a different identity; memory ignored and reset"]
    updated = datetime.strptime(row["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - updated > timedelta(minutes=get_settings().session_ttl_min):
        return dict(EMPTY), ["session expired; memory reset"]
    return json.loads(row["memory_json"]), []


def update(session_id: str | None, student_id: str | None, memory: dict, question: str, response: dict,
           entities: dict) -> None:
    if not session_id:
        return
    turn = {"q": redact(question, student_id)[:200], "answer_type": response["answer_type"],
            "a": redact(response["answer"], student_id)[:200]}
    turns = (memory.get("last_turns") or [])[-2:] + [turn]
    ents = {**memory.get("entities", {}), **{k: v for k, v in entities.items() if v}}
    summary = "Earlier: " + "; ".join(
        f"{t['q'][:60]} -> {t['answer_type']}" for t in turns)
    repo.save_session(session_id, student_id, {"summary": summary, "last_turns": turns, "entities": ents})
