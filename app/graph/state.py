from datetime import date
from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    trace_id: str
    student_id: str | None
    student: dict | None
    question: str
    as_of_date: date
    session_id: str | None
    memory: dict
    memory_used: bool
    rewritten_question: str
    intent: str
    entities: dict[str, Any]          # course, data_needed, eligibility_check, assume_pass
    parameter: str | None
    plan: list[str]
    route: str                        # rag | structured | hybrid (query router decision)
    chunks: list[dict]                # raw retrieval (top_k)
    ordered_chunks: list[dict]        # after precedence, applicable, best first
    overridden_chunks: list[dict]
    upcoming: list[dict]
    rule_lookup: dict | None
    precedence_decision: str
    tool_log: list[dict]              # audit: tool, input, output, status, ms
    tool_outputs: dict[str, dict]
    course: dict | None
    refusal: str | None
    clarification: str | None
    response: dict
    llm_calls: int
    tokens: int
    timings: dict[str, int]
    warnings: list[str]
    t0: float
