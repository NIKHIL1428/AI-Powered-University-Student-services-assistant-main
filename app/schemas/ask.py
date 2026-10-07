"""POST /ask contract (Section 6.1). Last three response fields are additive."""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

AnswerType = Literal["retrieved_fact", "calculated", "not_found",
                     "clarification_needed", "refused", "conflict_flagged"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    as_of_date: date | None = None
    session_id: str | None = Field(default=None, max_length=64)


class Citation(BaseModel):
    doc_id: str
    title: str
    section: str
    page: int | None = None
    version: str
    effective_from: str


class ToolCall(BaseModel):
    tool: str
    input: dict[str, Any] = {}
    output: dict[str, Any] = {}


class AppliedRule(BaseModel):
    rule_id: str
    value: str
    source_doc_id: str


class AskResponse(BaseModel):
    trace_id: str
    answer: str
    answer_type: AnswerType
    citations: list[Citation] = []
    tools_invoked: list[ToolCall] = []
    applied_rules: list[AppliedRule] = []
    conflicts_detected: list[dict[str, Any]] = []
    explanation: str = ""
    as_of_date: str
    upcoming_changes: list[dict[str, Any]] = []
    assumptions: list[str] = []
    session_id: str | None = None
