"""Rule extraction at ingest time (live ingestion core).

Priority: 1) explicit `rules` in the ingest metadata, 2) regex per parameter over the doc's chunks.
Every extracted rule inherits dates + scope from the document and points at the clause it came from.
Rules are never deleted for other docs — the precedence engine decides which one applies on as_of_date.
"""
import re

from app.db import repo
from app.ingestion.chunker import Chunk
from app.schemas.source import SourceMetadata
from app.tools.catalog import PARAMETERS

PREFIX = {"min_attendance_pct": "ATT", "min_total_marks_pct": "PASS", "supplementary_allowed_results": "SUPP",
          "placement_min_cgpa": "PLC-CGPA", "placement_max_backlogs": "PLC-BKLG",
          "attendance_relaxation_dean_pct": "ATT-RELAX-DEAN", "attendance_relaxation_committee_pct": "ATT-RELAX-COMM",
          "min_attendance_after_relaxation_pct": "ATT-FLOOR", "max_attendance_relaxations": "ATT-RELAX-MAX"}

PCT = r"(\d{2}(?:\.\d{1,2})?)\s*(?:%|per\s*cent|percent)"
REGEXES: dict[str, list[re.Pattern]] = {
    "min_attendance_pct": [
        re.compile(r"attendance[^.\n]{0,140}?(?:minimum|at\s+least|not\s+less\s+than|atleast|min\.?)\s+(?:of\s+)?" + PCT, re.I),
        re.compile(r"(?:minimum|at\s+least|not\s+less\s+than)\s+(?:of\s+)?" + PCT + r"[^.\n]{0,80}?attendance", re.I),
        re.compile(r"attendance[^.\n]{0,60}?(?:is|be|of|:)\s*" + PCT, re.I),
    ],
    "min_total_marks_pct": [
        re.compile(r"(?:to\s+pass|pass(?:ing)?\s+(?:mark|marks|criteria|criterion|a\s+course))[^.\n]{0,120}?"
                   r"(?:minimum|at\s+least|not\s+less\s+than)?\s*(?:of\s+)?" + PCT, re.I),
        re.compile(r"minimum\s+(?:of\s+)?" + PCT + r"\s+(?:of\s+the\s+)?(?:total\s+|aggregate\s+)?marks[^.\n]{0,60}pass", re.I),
    ],
    "placement_min_cgpa": [
        re.compile(r"(?:cgpa|cumulative grade point average)[^.\n]{0,60}?(?:minimum|at\s+least|not\s+less\s+than|of|>=|≥)"
                   r"\s*(?:of\s+)?(\d{1,2}(?:\.\d{1,2})?)", re.I),
        re.compile(r"(?:minimum|at\s+least)\s+(?:a\s+)?(?:cgpa|cumulative grade point average)\s+(?:of\s+)?(\d{1,2}(?:\.\d{1,2})?)", re.I),
    ],
    "placement_max_backlogs": [
        re.compile(r"(?:not\s+more\s+than|maximum\s+(?:of\s+)?|up\s*to|at\s+most)\s+(\d{1,2})\s+(?:active\s+)?backlogs?", re.I),
        re.compile(r"\b(no|zero|nil)\s+(?:active\s+)?backlogs?", re.I),
    ],
}
CONTEXT = {"placement_min_cgpa": "placement", "placement_max_backlogs": "placement",
           "supplementary_allowed_results": "supplementary"}


def _valid(parameter: str, value: str) -> bool:
    rng = PARAMETERS[parameter]["range"]
    if rng is None:
        return bool(value)
    try:
        return rng[0] <= float(value) <= rng[1]
    except ValueError:
        return False


def _regex_value(parameter: str, text: str) -> str | None:
    text = " ".join(text.split())          # OCR/PDF line breaks inside a sentence
    if parameter == "supplementary_allowed_results":
        t = text.lower()
        if "supplementary" not in t or not re.search(r"\b(eligible|appear|allowed|may)\b", t):
            return None
        vals = [v for v, kw in (("FAIL", r"\bfail(ed|s|ing)?\b"), ("ABSENT", r"\babsent\b")) if re.search(kw, t)]
        return ";".join(vals) or None
    for rx in REGEXES[parameter]:
        if m := rx.search(text):
            v = m.group(1)
            if v.lower() in {"no", "zero", "nil"}:
                v = "0"
            return v
    return None


def _rule_row(meta: SourceMetadata, parameter: str, value: str, section: str, method: str,
              description: str | None = None, rule_id: str | None = None, operator: str | None = None) -> dict:
    return {"rule_id": rule_id or f"{PREFIX[parameter]}-{meta.doc_id}", "parameter": parameter,
            "description": description or f"{PARAMETERS[parameter]['desc']} (extracted from {meta.doc_id} §{section})",
            "operator": operator or PARAMETERS[parameter]["operator"], "value": value,
            "scope_programmes": meta.scope_programmes, "scope_batches": meta.scope_batches,
            "effective_from": meta.effective_from.isoformat(),
            "effective_to": meta.effective_to.isoformat() if meta.effective_to else "",
            "source_doc_id": meta.doc_id, "source_section": section, "extraction_method": method}


def extract_rules(meta: SourceMetadata, chunks: list[Chunk]) -> tuple[list[dict], list[str]]:
    """Returns (rules, warnings). Does not write; caller persists."""
    rules, warnings = [], []
    existing = {(r["source_doc_id"], r["parameter"]) for r in repo.all_rules()
                if r["extraction_method"] in ("seed", "metadata") and r["source_doc_id"] == meta.doc_id}
    covered = set()
    for spec in meta.rules:
        if spec.parameter not in PARAMETERS:
            warnings.append(f"rule parameter '{spec.parameter}' not in vocabulary; skipped")
            continue
        if not _valid(spec.parameter, spec.value) and spec.operator != "in":
            warnings.append(f"rule {spec.parameter}={spec.value} out of sane range; skipped")
            continue
        rules.append(_rule_row(meta, spec.parameter, spec.value, spec.section, "metadata",
                               spec.description, spec.rule_id, spec.operator))
        covered.add(spec.parameter)

    for parameter in [*REGEXES, "supplementary_allowed_results"]:   # regex extraction only where we have patterns
        if parameter in covered or (meta.doc_id, parameter) in existing:
            continue
        for ch in chunks:
            ctx = CONTEXT.get(parameter)
            if ctx and ctx not in ch.text.lower():
                continue
            if not any(k in ch.text.lower() for k in PARAMETERS[parameter]["keywords"]):
                continue
            v = _regex_value(parameter, ch.text)
            if v and _valid(parameter, v):
                rules.append(_rule_row(meta, parameter, v, ch.section, "regex"))
                break
    return rules, warnings
