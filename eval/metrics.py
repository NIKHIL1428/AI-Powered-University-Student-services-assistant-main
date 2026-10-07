"""Scoring functions. Method: exact match on answer_type, enums and numbers; substring rubric for text answers
(keywords chosen by the team before running, disclosed in EVAL_REPORT.md). No LLM-as-judge."""
import statistics


def _src_match(cited: str, expected: str) -> bool:
    cd, _, cs = cited.partition("#")
    ed, _, es = expected.partition("#")
    return cd == ed and (not es or cs == es or cs.startswith(es + ".") or es.startswith(cs + "."))


def tool_outputs(resp: dict) -> dict:
    return {t["tool"]: t["output"] for t in resp.get("tools_invoked", [])}


def score(q: dict, resp: dict) -> dict:
    s: dict = {"id": q["id"], "category": q["category"], "answer_type": resp["answer_type"]}
    allowed = q.get("expected_answer_type_any") or [q["expected_answer_type"]]
    type_ok = resp["answer_type"] in allowed
    ans = resp["answer"]
    contains_ok = all(k.lower() in ans.lower() for k in q.get("answer_contains", []))
    not_contains_ok = all(k.lower() not in ans.lower() for k in q.get("answer_not_contains", []))

    tools_ok = None
    if q.get("expected_values"):
        outs = tool_outputs(resp)
        tools_ok = all(tool in outs and all(outs[tool].get(k) == v for k, v in exp.items())
                       for tool, exp in q["expected_values"].items())
        s["tool_result_correct"] = tools_ok

    extra_ok = True
    if q.get("expected_upcoming"):
        ups = {u["doc_id"] for u in resp.get("upcoming_changes", [])}
        extra_ok &= all(d in ups for d in q["expected_upcoming"])
    if q.get("expected_overridden"):
        over = {c["overridden"]["doc_id"] for c in resp.get("conflicts_detected", []) if c.get("overridden")}
        extra_ok &= all(d in over for d in q["expected_overridden"])
    if q.get("expect_assumptions"):
        extra_ok &= bool(resp.get("assumptions"))
    if q.get("expected_relaxation"):
        rx = tool_outputs(resp).get("check_exam_eligibility", {}).get("relaxation") or {}
        extra_ok &= rx.get("outcome") == q["expected_relaxation"]
    if q.get("expected_rule_id"):
        extra_ok &= q["expected_rule_id"] in {r["rule_id"] for r in resp.get("applied_rules", [])}

    s["answer_correct"] = bool(type_ok and contains_ok and not_contains_ok and (tools_ok is not False) and extra_ok)

    if q.get("expected_sources"):
        cited = [f"{c['doc_id']}#{c['section']}" for c in resp.get("citations", [])]
        s["citation_correct"] = bool(cited) and any(_src_match(c, e) for c in cited for e in q["expected_sources"])
        s["citations"] = cited

    unanswerable = q["expected_answer_type"] == "not_found" if "expected_answer_type" in q else False
    s["abstention_correct"] = (resp["answer_type"] == "not_found") == unanswerable
    s["unanswerable"] = unanswerable
    return s


def hit_at_k(expected: list[str], chunks: list[dict]) -> bool:
    """Hit if a top-k chunk is the expected clause: same doc and (same section, or - for fixed-size chunks that
    carry no section - the chunk text contains that clause's number as a heading)."""
    import re
    for c in chunks:
        got = f"{c['meta']['doc_id']}#{c['meta'].get('section', '')}"
        for e in expected:
            if _src_match(got, e):
                return True
            doc, _, sec = e.partition("#")
            if c["meta"]["doc_id"] == doc and sec and re.search(rf"(^|\s){re.escape(sec)}[.):]?\s", c["text"]):
                return True
    return False


def pct(xs: list[bool]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def summarize(rows: list[dict]) -> dict:
    lat = [r["latency_ms"] for r in rows]
    return {
        "n": len(rows),
        "answer_correctness": pct([r["answer_correct"] for r in rows]),
        "citation_accuracy": pct([r.get("citation_correct") for r in rows if "citation_correct" in r]),
        "abstention_accuracy": pct([r["abstention_correct"] for r in rows]),
        "tool_result_correctness": pct([r.get("tool_result_correct") for r in rows if "tool_result_correct" in r]),
        "latency_p50_ms": percentile(lat, 0.5), "latency_p95_ms": percentile(lat, 0.95),
        "llm_calls_avg": round(statistics.mean(r["llm_calls"] for r in rows), 2),
        "tokens_avg": round(statistics.mean(r["tokens"] for r in rows), 1),
    }
