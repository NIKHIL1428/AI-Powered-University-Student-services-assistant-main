"""R10 audit record (Annex D superset). Summaries only — no chain-of-thought, no student names."""
from app.config import get_settings
from app.db import repo
from app.guardrails.redact import redact


def build_record(state: dict, response: dict, latency_ms: int) -> dict:
    sid = state.get("student_id")
    return {
        "trace_id": state["trace_id"],
        "timestamp": repo.now_iso(),
        "student_id": sid,
        "question": redact(state.get("question", ""), sid),
        "question_category": state.get("intent"),
        "rewritten_question": redact(state.get("rewritten_question", ""), sid),
        "memory_used": bool(state.get("memory_used")),
        "as_of_date": str(state.get("as_of_date")),
        "route": state.get("route"),
        "plan": state.get("plan", []),
        "sources_retrieved": [{"doc_id": c["meta"]["doc_id"], "section": c["meta"].get("section"),
                               "page": c["meta"].get("page"), "score": c["score"]}
                              for c in state.get("chunks", [])],
        "precedence_decision": state.get("precedence_decision", ""),
        "conflicts": response.get("conflicts_detected", []),
        "upcoming_changes": response.get("upcoming_changes", []),
        "tools_invoked": state.get("tool_log", []),
        "rules_applied": response.get("applied_rules", []),
        "citations": response.get("citations", []),
        "answer_type": response["answer_type"],
        "answer": redact(response["answer"], sid),
        "model": get_settings().model_label,
        "llm_calls": state.get("llm_calls", 0),
        "tokens": state.get("tokens", 0),
        "latency_ms": latency_ms,
        "node_timings": state.get("timings", {}),
        "warnings": state.get("warnings", []),
    }


def log(record: dict) -> None:
    repo.write_audit(record)
