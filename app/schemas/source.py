"""Annex B Source Register metadata (also the /ingest metadata contract)."""
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DocType = Literal["regulation", "circular", "notice", "faq", "handbook", "unofficial"]


class RuleSpec(BaseModel):
    """Optional explicit rule supplied with /ingest metadata (highest-confidence extraction)."""
    parameter: str
    operator: Literal[">=", "<=", ">", "<", "==", "in", "between"]
    value: str
    section: str
    description: str | None = None
    rule_id: str | None = None


class SourceMetadata(BaseModel):
    doc_id: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
    title: str = Field(min_length=1)
    issuer: str = ""
    authority_level: int = Field(ge=1, le=5)
    doc_type: DocType
    version: str = "1.0"
    effective_from: date
    effective_to: date | None = None
    supersedes: str = ""                 # "DOC#clause;DOC2"
    scope_programmes: str = "ALL"
    scope_batches: str = "ALL"
    provenance: str = ""
    retrieved_on: date | None = None
    synthetic: Literal["Y", "N"] = "N"
    rules: list[RuleSpec] = []

    @field_validator("effective_to", "retrieved_on", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        return None if v in ("", None) else v

    @field_validator("doc_type", mode="before")
    @classmethod
    def lower(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("scope_batches")
    @classmethod
    def check_batches(cls, v):
        v = v.strip() or "ALL"
        for part in v.split(";"):
            if not re.fullmatch(r"ALL|\d{4}|\d{4}\+|\d{4}-\d{4}", part.strip(), re.I):
                raise ValueError(f"bad scope_batches part '{part}' (use ALL, 2023, 2023+, 2021-2023)")
        return v

    def register_row(self) -> dict:
        d = self.model_dump(exclude={"rules"})
        for k in ("effective_from", "effective_to", "retrieved_on"):
            d[k] = d[k].isoformat() if d[k] else ""
        return d
