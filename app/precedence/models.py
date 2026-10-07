from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass
class SourceCandidate:
    key: str                         # rule_id or chunk_id
    doc_id: str
    section: str
    authority_level: int
    effective_from: date | None
    effective_to: date | None = None
    supersedes: list[str] = field(default_factory=list)   # ["ACAD-REG-2021#7.2", "CIRC-X"]
    scope_programmes: str = "ALL"
    scope_batches: str = "ALL"
    topic: str | None = None         # rules: parameter
    value: str | None = None
    score: float = 0.0
    payload: dict = field(default_factory=dict)            # original chunk / rule row


@dataclass
class Resolution:
    winners: list[SourceCandidate] = field(default_factory=list)
    overridden: list[tuple[SourceCandidate, str]] = field(default_factory=list)
    upcoming: list[SourceCandidate] = field(default_factory=list)
    informational: list[SourceCandidate] = field(default_factory=list)
    dropped: list[tuple[SourceCandidate, str]] = field(default_factory=list)
    status: Literal["resolved", "conflict", "none"] = "none"
    notes: list[str] = field(default_factory=list)

    @property
    def decision_text(self) -> str:
        return "; ".join(self.notes) if self.notes else "no competing sources"
