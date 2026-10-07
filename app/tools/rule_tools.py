"""resolve_rule: pick the applicable rule-registry row for a parameter via the precedence engine."""
from datetime import date

from app.db import repo
from app.precedence.engine import parse_supersedes, resolve
from app.precedence.models import Resolution, SourceCandidate


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def rule_candidates(parameter: str) -> list[SourceCandidate]:
    out = []
    for r in repo.rules_for_parameter(parameter):
        out.append(SourceCandidate(
            key=r["rule_id"], doc_id=r["source_doc_id"], section=r["source_section"] or "",
            authority_level=int(r["authority_level"] or 4),
            effective_from=_d(r["effective_from"]), effective_to=_d(r["effective_to"]),
            supersedes=parse_supersedes(r.get("doc_supersedes")),
            scope_programmes=r["scope_programmes"] or "ALL", scope_batches=r["scope_batches"] or "ALL",
            topic=parameter, value=r["value"], payload=r))
    return out


def format_value(rule: dict) -> str:
    op, v = rule["operator"], rule["value"]
    unit = "%" if rule["parameter"].endswith("_pct") else ""
    return f"{op}{v}{unit}" if op != "in" else f"in {v}"


def rule_view(c: SourceCandidate) -> dict:
    r = c.payload
    return {"rule_id": r["rule_id"], "parameter": r["parameter"], "operator": r["operator"],
            "value": r["value"], "display": format_value(r), "description": r.get("description"),
            "source_doc_id": r["source_doc_id"], "source_section": r["source_section"],
            "effective_from": r["effective_from"], "authority_level": c.authority_level}


def resolve_rule(parameter: str, as_of: date, student: dict | None = None) -> tuple[dict, Resolution]:
    """Returns (tool_output, resolution). tool_output['status'] in ok | conflict | none."""
    res = resolve(rule_candidates(parameter), as_of, student)
    out: dict = {"parameter": parameter, "as_of_date": as_of.isoformat(),
                 "precedence_decision": res.decision_text}
    if res.status == "none":
        out["status"] = "none"
    elif res.status == "conflict":
        out["status"] = "conflict"
        out["candidates"] = [rule_view(c) for c in res.winners]
    else:
        out["status"] = "ok"
        out["rule"] = rule_view(res.winners[0])
    out["overridden"] = [{**rule_view(c), "reason": why} for c, why in res.overridden]
    out["upcoming"] = [rule_view(c) for c in res.upcoming]
    return out, res
