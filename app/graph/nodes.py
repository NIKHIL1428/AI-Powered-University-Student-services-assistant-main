"""LangGraph nodes. Only `classify` and `compose` may call the LLM; everything else is deterministic code."""
import functools
import time
from datetime import date

from app.audit import logger as audit
from app.config import NOT_FOUND_MESSAGE, get_settings
from app.db import repo
from app.router import query_router as H
from app.guardrails import auth
from app.guardrails.injection import sanitize
from app.guardrails.validator import content_terms, missing_terms, ungrounded_numbers
from app.llm import qwen as llm
from app.llm.qwen import LLMUsage
from app.llm.json_guard import call_json
from app.llm.prompts import (CLASSIFY_SYSTEM, COMPOSE_SYSTEM, EXPLAIN_SYSTEM, ClassifyOut, ComposeOut,
                             ExplainOut)
from app.memory import session_store
from app.precedence.engine import resolve
from app.precedence.scope import scope_label
from app.vectorstore import chroma_manager as vector_store
from app.retrieval.retriever import retrieve as vector_retrieve
from app.retrieval.retriever import to_candidate
from app.tools import eligibility_tools as ET
from app.tools import student_tools as ST
from app.tools.catalog import INTENT_ALLOWLIST, PARAMETERS, PERSONAL_INTENTS, TOOL_PARAMETERS
from app.tools.rule_tools import format_value, resolve_rule

MAX_DOCS_TO_LLM = 5
RELEVANCE_MARGIN = 0.10   # chunks this close to the best score compete on precedence


def timed(fn):
    @functools.wraps(fn)
    def wrap(state):
        t = time.perf_counter()
        out = fn(state) or {}
        timings = dict(state.get("timings", {}))
        timings[fn.__name__] = int((time.perf_counter() - t) * 1000)
        out["timings"] = timings
        return out
    return wrap


def _usage_update(state, usage: LLMUsage) -> dict:
    out = {"llm_calls": state.get("llm_calls", 0) + usage.calls, "tokens": state.get("tokens", 0) + usage.tokens}
    if usage.errors:
        out["warnings"] = state.get("warnings", []) + [f"llm: {e}" for e in usage.errors[:3]]
    return out


# ------------------------------------------------------------------ 1 auth_guard
@timed
def auth_guard(state):
    sid = state.get("student_id")
    if state.get("refusal"):
        return {}
    other = auth.other_student_reference(state["question"], sid)
    if other:
        return {"refusal": f"I can only share records of the logged-in student; {other}.", "intent": "refused"}
    return {"student": repo.get_student(sid) if sid else None}


# ------------------------------------------------------------------ 2 contextualize
@timed
def contextualize(state):
    memory, warnings = session_store.load(state.get("session_id"), state.get("student_id"))
    q = state["question"]
    rewritten, used = q, False
    if memory.get("last_turns") and H.is_followup(q):
        last = memory["last_turns"][-1]["q"]
        rewritten = f"{q} (follow-up to previous question: \"{last}\")"
        used = True
    return {"memory": memory, "memory_used": used, "rewritten_question": rewritten,
            "warnings": state.get("warnings", []) + warnings}


# ------------------------------------------------------------------ 3 classify
def _classify(state):
    q, usage = state["question"], LLMUsage()
    kw = H.keyword_classify(q)
    out: ClassifyOut | None = None
    if llm.enabled() and get_settings().classify_mode == "llm":
        summary = state.get("memory", {}).get("summary", "")
        user = (f"<conversation_summary>{summary}</conversation_summary>\n" if summary else "") + f"Question: {q}"
        out = call_json(CLASSIFY_SYSTEM, user, ClassifyOut, usage)
    if out is None:
        out = kw
    # deterministic sanity merge
    parameter = out.parameter if out.parameter in PARAMETERS else kw.parameter
    if not H.THRESHOLD.search(q):
        parameter = None          # e.g. "can the Dean condone attendance?" is not asking for the threshold
    check = out.eligibility_check if out.eligibility_check != "none" else kw.eligibility_check
    intent = out.intent
    if intent in ("policy_fact", "procedure", "out_of_scope") and kw.intent in PERSONAL_INTENTS and state.get("student_id"):
        intent = kw.intent        # "my attendance" is never a policy question
    if intent in PERSONAL_INTENTS and not H.PERSONAL.search(q):
        intent = kw.intent        # no first-person reference -> not a question about the student's own records
    if intent in PERSONAL_INTENTS and not state.get("student_id") and not H.OWN_RECORDS.search(q):
        # hypothetical "if I am placed in a Dream company, can I apply again?" is a policy question,
        # not a request for records - answer it from documents instead of refusing
        intent = kw.intent if kw.intent not in PERSONAL_INTENTS else "policy_fact"
    entities = {"course": out.course, "data_needed": out.data_needed or kw.data_needed,
                "eligibility_check": check, "assume_pass": out.assume_pass or kw.assume_pass}

    student = state.get("student")
    if student and not entities["course"]:
        entities["course"] = H.course_mention(q, repo.courses_for_student(student["student_id"]))

    # follow-up: inherit intent / course from memory (only what the new question leaves open)
    mem_ents = state.get("memory", {}).get("entities", {})
    if state.get("memory_used"):
        if not entities["course"] and mem_ents.get("course"):
            entities["course"] = mem_ents["course"]
        if mem_ents.get("intent") and (intent in ("policy_fact", "out_of_scope") or H.is_followup(q)) \
                and not H.DATA.search(q) and not H.ELIG.search(q):
            intent = mem_ents["intent"]
            entities["eligibility_check"] = entities["eligibility_check"] if check != "none" else mem_ents.get("check", "none")
            entities["data_needed"] = entities["data_needed"] or mem_ents.get("data_needed", [])
            parameter = parameter or mem_ents.get("parameter")

    upd = {"intent": intent, "entities": entities, "parameter": parameter, **_usage_update(state, usage)}
    if intent in PERSONAL_INTENTS and not state.get("student_id"):
        upd["refusal"] = ("This is a personal question. Please identify yourself (X-Student-Id header / "
                          "select your student ID) - I cannot look up records without it.")
    return upd


# ------------------------------------------------------------------ 4 plan
def _plan(state):
    intent, e = state["intent"], state["entities"]
    check, course = e.get("eligibility_check", "none"), e.get("course")
    steps: list[str] = []
    clarification = None
    if intent in ("policy_fact",):
        steps = ["retrieve"] + (["resolve_rule"] if state.get("parameter") else [])
    elif intent in ("procedure", "out_of_scope"):
        steps = ["retrieve"]
    elif intent == "personal_data":
        needed = e.get("data_needed") or (["attendance"] if course else ["profile"])
        steps = (["find_course"] if course else []) + \
                [{"attendance": "get_attendance", "results": "get_results", "profile": "get_student_profile"}[d]
                 for d in needed]
    elif intent == "personal_eligibility":
        if check == "none":
            check = "exam" if course else "none"
        if check == "placement":
            steps = ["get_student_profile", "check_placement_eligibility", "retrieve"]
        elif check in ("exam", "supplementary"):
            if not course:
                clarification = _course_question(state, f"{'end-semester exam' if check == 'exam' else 'supplementary exam'} eligibility")
            steps = ["find_course", f"check_{check}_eligibility", "retrieve"]
        else:
            clarification = ("Which eligibility do you mean - end-semester exam (attendance), "
                             "supplementary exam, or placement?")
    elif intent == "multi_step" and check == "exam":
        # what-if on attendance (e.g. "if the Dean grants relaxation, can I appear?")
        if not course:
            clarification = _course_question(state, "end-semester exam eligibility")
        steps = ["find_course", "get_attendance", "check_exam_eligibility", "retrieve"]
    elif intent == "multi_step":
        steps = (["find_course", "get_results", "check_supplementary_eligibility"] if course else
                 ["get_student_profile"]) + ["check_placement_eligibility", "retrieve"]
    allowed = INTENT_ALLOWLIST.get(intent, ["retrieve"])
    steps = [s for s in steps if s in allowed]           # allowlist: nothing outside it can ever run
    return {"plan": steps, "clarification": clarification,
            "entities": {**e, "eligibility_check": check}}


def _course_question(state, what: str) -> str:
    courses = repo.courses_for_student(state["student_id"])
    opts = ", ".join(f"{c['course_code']} ({c['course_name']})" for c in courses[:12])
    return f"Which course do you mean for {what}? Your courses: {opts}."


# ------------------------------------------------------------------ 5 retrieve
def _retrieve(state):
    if "retrieve" not in state.get("plan", []):
        return {"chunks": []}
    q = state.get("rewritten_question") or state["question"]
    params = set()
    if state.get("parameter"):
        params.add(state["parameter"])
    for step in state["plan"]:
        params.update(TOOL_PARAMETERS.get(step, []))
    if params and state["intent"] != "policy_fact":
        q = q + " | " + "; ".join(PARAMETERS[p]["desc"] for p in params)
    return {"chunks": vector_retrieve(q)}


# ------------------------------------------------------------------ 6 resolve_precedence
def _resolve_precedence(state):
    as_of, student = state["as_of_date"], state.get("student")
    res = resolve([to_candidate(c) for c in state.get("chunks", [])], as_of, student)
    notes = [n for n in res.notes if not n.startswith("step 1: ") or "upcoming" in n]
    ordered = [c.payload for c in res.winners]
    # level-5 content may be shown as informational only, after everything else
    ordered += [{**c.payload, "informational": True} for c in res.informational]
    threshold = get_settings().not_found_threshold
    upcoming = [{"doc_id": c.doc_id, "title": c.payload["meta"].get("title"), "section": c.section,
                 "effective_from": str(c.effective_from), "note": "not yet effective on as_of_date"}
                for c in res.upcoming if c.score >= threshold]
    out = {"ordered_chunks": ordered, "upcoming": upcoming,
           "overridden_chunks": [{"doc_id": c.doc_id, "section": c.section, "reason": why}
                                 for c, why in res.overridden]}
    decision = list(dict.fromkeys(notes))
    if state.get("rule_lookup"):                      # rule-registry precedence (from the resolve_rule tool)
        decision = [state["rule_lookup"]["precedence_decision"]] + decision
    out["precedence_decision"] = "; ".join(d for d in decision if d) or "no competing sources"
    return out


# ------------------------------------------------------------------ 7 run_tools
def _run_tools(state):
    sid, as_of, e = state.get("student_id"), state["as_of_date"], state["entities"]
    log, outputs = list(state.get("tool_log", [])), {}
    course, clarification = None, state.get("clarification")

    def call(name, inp, fn):
        t = time.perf_counter()
        try:
            out, status = fn(), "ok"
        except Exception as ex:          # a tool failure is reported, never invented around
            out, status = {"error": f"{type(ex).__name__}: {ex}"}, "error"
        log.append({"tool": name, "input": inp, "output": out, "status": status,
                    "ms": int((time.perf_counter() - t) * 1000)})
        outputs[name] = out
        return out

    rule_lookup = None
    if "resolve_rule" in state.get("plan", []) and state.get("parameter"):
        t = time.perf_counter()
        rule_lookup, _ = resolve_rule(state["parameter"], as_of, state.get("student"))
        log.append({"tool": "resolve_rule", "input": {"parameter": state["parameter"], "as_of_date": str(as_of)},
                    "output": _rule_summary(rule_lookup), "status": "ok",
                    "ms": int((time.perf_counter() - t) * 1000)})
        outputs["resolve_rule"] = rule_lookup

    for step in state.get("plan", []):
        if clarification:
            break
        if step == "find_course":
            r = call("find_course", {"query": e.get("course")}, lambda: ST.find_course(sid, e.get("course") or ""))
            if r["status"] != "ok":
                opts = ", ".join(f"{c['course_code']} ({c['course_name']})" for c in r.get("candidates", []))
                clarification = (f"'{e.get('course')}' matches several of your courses: {opts}. Which one do you mean?"
                                 if r["status"] == "ambiguous" else
                                 _course_question(state, f"'{e.get('course')}' (not found among your courses)"))
            else:
                course = r
        elif step == "get_student_profile":
            call(step, {}, lambda: ST.get_student_profile(sid))
        elif step == "get_attendance":
            cc = course["course_code"] if course else None
            call(step, {"course_code": cc} if cc else {}, lambda: ST.get_attendance(sid, cc))
        elif step == "get_results":
            cc = course["course_code"] if course else None
            call(step, {"course_code": cc} if cc else {}, lambda: ST.get_results(sid, cc))
        elif step == "check_exam_eligibility":
            cc = course["course_code"]
            call(step, {"course_code": cc, "as_of_date": str(as_of)}, lambda: ET.check_exam_eligibility(sid, cc, as_of))
        elif step == "check_supplementary_eligibility":
            cc = course["course_code"]
            call(step, {"course_code": cc, "as_of_date": str(as_of)},
                 lambda: ET.check_supplementary_eligibility(sid, cc, as_of))
        elif step == "check_placement_eligibility":
            assume = [course["course_code"]] if (course and (e.get("assume_pass") or state["intent"] == "multi_step")) else []
            inp = {"as_of_date": str(as_of)} | ({"assume_pass": assume} if assume else {})
            call(step, inp, lambda: ET.check_placement_eligibility(sid, as_of, assume))
    return {"tool_log": log, "tool_outputs": outputs, "course": course, "clarification": clarification,
            "rule_lookup": rule_lookup}


def _rule_summary(rl: dict) -> dict:
    out = {"status": rl["status"]}
    if rl.get("rule"):
        r = rl["rule"]
        out.update(rule_id=r["rule_id"], value=r["display"], source_doc_id=r["source_doc_id"],
                   source_section=r["source_section"], effective_from=r["effective_from"])
    if rl.get("candidates"):
        out["candidates"] = [{"rule_id": c["rule_id"], "value": c["display"], "source_doc_id": c["source_doc_id"]}
                             for c in rl["candidates"]]
    out["overridden"] = [{"rule_id": o["rule_id"], "value": o["display"], "reason": o["reason"]}
                         for o in rl.get("overridden", [])]
    return out


# ------------------------------------------------------------------ 8 compose (+ 9 validate inline helpers)
def _citation_from_meta(m: dict) -> dict:
    ef = str(m.get("effective_from") or "")
    ef = f"{ef[:4]}-{ef[4:6]}-{ef[6:8]}" if len(ef) == 8 else ef
    return {"doc_id": m["doc_id"], "title": m.get("title", ""), "section": str(m.get("section", "")),
            "page": int(m["page"]) if m.get("page") not in (None, "") else None,
            "version": str(m.get("version", "")), "effective_from": ef}


def _citation_for_rule(rule: dict, state) -> dict:
    """Cite the clause behind a rule: retrieved chunk if present, else look the clause up; fields from metadata."""
    for c in state.get("chunks", []):
        if c["meta"]["doc_id"] == rule["source_doc_id"] and str(c["meta"].get("section")) == str(rule["source_section"]):
            return _citation_from_meta(c["meta"])
    hits = vector_store.get_section(rule["source_doc_id"], str(rule["source_section"]))
    if hits:
        cit = _citation_from_meta(hits[0]["meta"])
        cit["section"] = str(rule["source_section"])
        return cit
    src = repo.get_source(rule["source_doc_id"]) or {}
    return {"doc_id": rule["source_doc_id"], "title": src.get("title", ""), "section": str(rule["source_section"]),
            "page": None, "version": str(src.get("version", "")), "effective_from": src.get("effective_from", "")}


def _applied(rule: dict) -> dict:
    return {"rule_id": rule["rule_id"], "value": rule["display"], "source_doc_id": rule["source_doc_id"]}


def _rule_conflicts(rl: dict) -> list[dict]:
    out = []
    win = rl.get("rule")
    for o in rl.get("overridden", []):
        if win and o["value"] == win["value"]:
            continue                      # same value: superseded but no disagreement
        out.append({"parameter": rl["parameter"], "status": "resolved",
                    "winner": {"doc_id": win["source_doc_id"], "section": win["source_section"],
                               "value": win["display"]} if win else None,
                    "overridden": {"doc_id": o["source_doc_id"], "section": o["source_section"], "value": o["display"]},
                    "reason": o["reason"]})
    if rl["status"] == "conflict":
        out.append({"parameter": rl["parameter"], "status": "unresolved",
                    "candidates": [{"doc_id": c["source_doc_id"], "section": c["source_section"],
                                    "value": c["display"], "effective_from": c["effective_from"]}
                                   for c in rl["candidates"]],
                    "reason": "same authority and same effective date with different values (Annex A step 5)"})
    return out


def _rule_upcoming(rl: dict) -> list[dict]:
    return [{"doc_id": u["source_doc_id"], "section": u["source_section"], "rule_id": u["rule_id"],
             "value": u["display"], "effective_from": u["effective_from"],
             "note": "not yet effective on as_of_date"} for u in rl.get("upcoming", [])]


def _base(state) -> dict:
    return {"trace_id": state["trace_id"], "answer": "", "answer_type": "not_found", "citations": [],
            "tools_invoked": [{"tool": t["tool"], "input": t["input"], "output": t["output"]}
                              for t in state.get("tool_log", [])],
            "applied_rules": [], "conflicts_detected": [], "explanation": "",
            "as_of_date": state["as_of_date"].isoformat(), "upcoming_changes": list(state.get("upcoming", [])),
            "assumptions": [], "session_id": state.get("session_id")}


def _not_found(r: dict, why: str) -> dict:
    r.update(answer=NOT_FOUND_MESSAGE, answer_type="not_found", citations=[], explanation=why)
    return r


def _compose(state):
    r = _base(state)
    usage = LLMUsage()
    warnings = list(state.get("warnings", []))
    if state.get("refusal"):
        r.update(answer=state["refusal"], answer_type="refused",
                 explanation="Identity comes only from the X-Student-Id header; other students' records are never shared.")
        return {"response": r}
    if state.get("clarification"):
        r.update(answer=state["clarification"], answer_type="clarification_needed",
                 explanation="The question is ambiguous; please specify so the right record can be checked.")
        return {"response": r}

    outs = state.get("tool_outputs", {})
    checks = [k for k in ("check_exam_eligibility", "check_supplementary_eligibility", "check_placement_eligibility")
              if k in outs]
    no_rule = [k for k in checks if outs[k].get("result") == "UNKNOWN" and outs[k].get("status") == "none"]
    if checks and len(no_rule) == len(checks):
        # No threshold for this check exists in the authorised sources (e.g. NSUT's placement policy leaves
        # CGPA/backlog criteria to each company). Never invent one: answer from the documents instead.
        r = _compose_text(state, r, usage, warnings)
        params = ", ".join(sorted({p for k in no_rule for p in TOOL_PARAMETERS.get(k, [])}))
        r["explanation"] = (f"Eligibility could not be computed: the rule registry has no applicable rule for "
                            f"{params} on {state['as_of_date']}. " + r.get("explanation", ""))
        if r["answer_type"] == "retrieved_fact":
            r["answer"] = ("I cannot compute this eligibility: the authorised sources define no university-wide "
                           "threshold for it. What the documents say: " + r["answer"])
    elif checks or any(k in outs for k in ("get_attendance", "get_results", "get_student_profile")):
        r = _compose_calculated(state, r, outs, checks, usage, warnings)
    elif state.get("rule_lookup") and state["rule_lookup"]["status"] in ("ok", "conflict"):
        r = _compose_rule_fact(state, r, usage, warnings)
    else:
        r = _compose_text(state, r, usage, warnings)
    upd = {"response": r, **_usage_update(state, usage)}
    upd["warnings"] = upd.get("warnings", []) + [w for w in warnings if w not in upd.get("warnings", [])]
    return upd


def _llm_explain(state, facts: dict, fallback: str, usage: LLMUsage, warnings: list) -> str:
    if not llm.enabled():
        return fallback
    user = f"<question>{state['question']}</question>\n<tool_result>{llm.dumps(facts)}</tool_result>"
    out = call_json(EXPLAIN_SYSTEM, user, ExplainOut, usage)
    if not out or not out.explanation.strip():
        return fallback
    bad = ungrounded_numbers(out.explanation, llm.dumps(facts) + fallback)
    if bad:
        warnings.append(f"validator: LLM explanation had ungrounded numbers {bad}; template used")
        return fallback
    return out.explanation.strip()


def _compose_calculated(state, r, outs, checks, usage, warnings):
    sentences, expl, cites, applied, assumptions = [], [], [], [], []
    course = state.get("course") or {}
    cname = f"{course.get('course_code', '')} ({course.get('course_name', '')})" if course else ""
    unknown = []

    def add_rule(rid):
        rows = [x for x in repo.all_rules() if x["rule_id"] == rid]
        if rows:
            rule = {**rows[0], "display": format_value(rows[0])}
            applied.append(_applied(rule))
            cites.append(_citation_for_rule(rule, state))
            expl.append(f"Rule {rid} ({rule['source_doc_id']} §{rule['source_section']}, effective "
                        f"{rule['effective_from']}) sets {rule['parameter']} {rule['display']}.")

    if "get_attendance" in outs:
        a = outs["get_attendance"]
        if a.get("status") == "ok" and "courses" in a:
            sentences.append("Your attendance: " + "; ".join(
                f"{c['course_code']} {c['attendance_pct']}% ({c['classes_attended']}/{c['classes_held']})"
                for c in a["courses"]) + ".")
        elif a.get("status") == "ok":
            sentences.append(f"Your attendance in {cname} is {a['attendance_pct']}% "
                             f"({a['classes_attended']} of {a['classes_held']} classes).")
        else:
            sentences.append(f"I have no attendance record for you in {cname or 'any course'}.")
    if "get_results" in outs and "check_supplementary_eligibility" not in outs:
        rs = outs["get_results"].get("results", [])
        if rs:
            sentences.append("Your results: " + "; ".join(
                f"{x['course_code']} {x['exam_session']} {x['exam_type']}: {x['total_marks']}/{x['max_marks']} "
                f"({x['internal_marks']} internal + {x['external_marks']} external) -> {x['result']}" for x in rs) + ".")
        else:
            sentences.append(f"I have no result records for you{' in ' + cname if cname else ''}.")
    if "get_student_profile" in outs and not checks:
        p = outs["get_student_profile"]
        sentences.append(f"Your CGPA is {p['cgpa']} with {p['active_backlogs']} active backlog(s) "
                         f"({p['programme']}, batch {p['batch_year']}, semester {p['current_semester']}).")

    if "check_exam_eligibility" in outs:
        x = outs["check_exam_eligibility"]
        if x["result"] == "ELIGIBLE":
            sentences.append(f"You are eligible to appear in the end-semester exam for {cname}: attendance "
                             f"{x['attendance_pct']}% ({x['classes_attended']}/{x['classes_held']}) meets the "
                             f"minimum {x['required_pct']:g}%.")
        elif x["result"] == "NOT_ELIGIBLE":
            sentences.append(f"You are not eligible to appear in the end-semester exam for {cname}: attendance "
                             f"{x['attendance_pct']}% ({x['classes_attended']}/{x['classes_held']}) is below the "
                             f"required {x['required_pct']:g}% - short by {x['classes_short']} class(es).")
            rx = x.get("relaxation")
            if rx:
                if rx["outcome"] == "ELIGIBLE_IF_DEAN_RELAXES":
                    sentences.append(f"However, {x['attendance_pct']}% is within the relaxation the Dean Academics "
                                     f"may allow (down to {rx['min_with_dean_relaxation_pct']:g}%), so you could "
                                     f"become eligible if that relaxation is granted on documented medical or "
                                     f"authorised-activity grounds.")
                elif rx["outcome"] == "ELIGIBLE_IF_DEAN_AND_COMMITTEE_RELAX":
                    sentences.append(f"{x['attendance_pct']}% is below the Dean's relaxation limit but within the "
                                     f"further exceptional relaxation (down to "
                                     f"{rx['min_with_committee_relaxation_pct']:g}%) on committee recommendation.")
                else:
                    sentences.append(f"Even with the maximum relaxation you would not be eligible: the floor after "
                                     f"relaxation is {rx['floor_after_relaxation_pct']:g}%.")
                assumptions.append("Relaxation is discretionary and needs supporting documents; the outcome above "
                                   "is what the rules permit, not a decision.")
                for rid in rx["all_rule_ids"]:
                    add_rule(rid)
        elif x["result"] == "DETAINED":
            sentences.append(f"Your record shows you are DETAINED in {cname}, so you cannot appear in its "
                             f"end-semester exam ({x['reason']}).")
        else:
            unknown.append(x)
        if x.get("rule_id"):
            add_rule(x["rule_id"])
    if "check_supplementary_eligibility" in outs:
        x = outs["check_supplementary_eligibility"]
        if x["result"] in ("ELIGIBLE", "NOT_ELIGIBLE"):
            marks = f", {x['total_marks']}/{x['max_marks']}" if x.get("total_marks") is not None else ""
            verdict = "eligible" if x["result"] == "ELIGIBLE" else "not eligible"
            sentences.append(f"You are {verdict} for the supplementary exam in {cname}: your latest result "
                             f"({x['exam_session']} {x['exam_type']}{marks}) is {x['latest_result']}, and the "
                             f"supplementary exam is for results {' / '.join(x['allowed_results'])}.")
            if x.get("pass_rule_id"):
                add_rule(x["pass_rule_id"])
        else:
            unknown.append(x)
        if x.get("rule_id"):
            add_rule(x["rule_id"])
    if "check_placement_eligibility" in outs:
        x = outs["check_placement_eligibility"]
        if x["result"] in ("ELIGIBLE", "NOT_ELIGIBLE"):
            assumed = bool([a for a in x["assumptions"] if "assumed PASSED" in a])
            prefix = f"If you pass the supplementary in {course.get('course_code')}, you would be" if assumed else "You are"
            if x["result"] == "ELIGIBLE":
                sentences.append(f"{prefix} eligible for placement: CGPA {x['cgpa']} "
                                 f"(minimum {x['required_min_cgpa']}) and {x['active_backlogs_considered']} active "
                                 f"backlog(s) (maximum {x['allowed_max_backlogs']}).")
            else:
                sentences.append(f"{prefix} {'still ' if assumed else ''}not eligible for placement: "
                                 + "; ".join(x["failing_criteria"]) + ".")
            assumptions += x["assumptions"]
            for rid in x.get("rule_ids", []):
                add_rule(rid)
        else:
            unknown.append(x)

    conflicts = []
    for u in unknown:
        rl = u.get("rule_lookup") or {}
        if rl.get("status") == "conflict":
            conflicts += _rule_conflicts(rl)
            for c in rl.get("candidates", []):
                cites.append(_citation_for_rule(c, state))
        sentences.append(f"I could not determine this: {u.get('reason', u.get('status'))}.")

    # dedupe citations / rules
    cites = list({(c["doc_id"], c["section"]): c for c in cites}.values())
    applied = list({a["rule_id"]: a for a in applied}.values())
    for name in ("check_exam_eligibility", "check_supplementary_eligibility", "check_placement_eligibility"):
        for p in TOOL_PARAMETERS.get(name, []) if name in outs else []:
            rl, _ = resolve_rule(p, state["as_of_date"], state.get("student"))
            conflicts += [c for c in _rule_conflicts(rl) if c["status"] == "resolved"]
            r["upcoming_changes"] += _rule_upcoming(rl)

    base_expl = " ".join(expl) or "Computed from your university records in the student database."
    base_expl += " Results are computed by deterministic tools; the AI only explains them."
    if assumptions:
        base_expl += " Assumptions: " + "; ".join(assumptions) + "."
    facts = {"answer": " ".join(sentences), "tools": state.get("tool_log", []), "rules": expl,
             "assumptions": assumptions}
    r.update(answer=" ".join(sentences),
             answer_type="conflict_flagged" if any(c["status"] == "unresolved" for c in conflicts) else "calculated",
             citations=cites, applied_rules=applied, conflicts_detected=_dedupe(conflicts),
             explanation=_llm_explain(state, facts, base_expl, usage, warnings), assumptions=assumptions)
    r["upcoming_changes"] = _merge_upcoming(r["upcoming_changes"])
    if r["answer_type"] == "conflict_flagged":
        r["answer"] += " The sources conflict and the precedence policy cannot resolve it; please contact the issuing office."
    return r


def _merge_upcoming(items: list[dict]) -> list[dict]:
    """One entry per upcoming document; a rule-level entry (carries the new value) beats a chunk-level one."""
    best: dict = {}
    for u in items:
        k = u["doc_id"]
        if k not in best or (u.get("value") and not best[k].get("value")):
            best[k] = u
    return list(best.values())


def _dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for i in items:
        k = llm.dumps(i)
        if k not in seen:
            seen.add(k)
            out.append(i)
    return out


def _compose_rule_fact(state, r, usage, warnings):
    rl = state["rule_lookup"]
    r["conflicts_detected"] = _rule_conflicts(rl)
    r["upcoming_changes"] = _merge_upcoming(r["upcoming_changes"] + _rule_upcoming(rl))
    desc = PARAMETERS[rl["parameter"]]["desc"]
    if rl["status"] == "conflict":
        cands = rl["candidates"]
        r.update(answer_type="conflict_flagged",
                 answer=f"The sources conflict on '{desc}': " + "; ".join(
                     f"{c['source_doc_id']} §{c['source_section']} says {c['display']}" for c in cands)
                 + ". The precedence policy cannot resolve this (same authority, same effective date). "
                   "Please contact the issuing office.",
                 citations=[_citation_for_rule(c, state) for c in cands],
                 explanation=rl["precedence_decision"])
        return r
    rule = rl["rule"]
    cit = _citation_for_rule(rule, state)
    src = repo.get_source(rule["source_doc_id"]) or {}
    scope = scope_label(src.get("scope_programmes", "ALL"), src.get("scope_batches", "ALL"))
    answer = (f"{desc}: {rule['display']} - per {src.get('title', rule['source_doc_id'])} "
              f"(§{rule['source_section']}, version {src.get('version', '?')}, effective {rule['effective_from']}; "
              f"applies to {scope}).")
    expl = f"Precedence decision: {rl['precedence_decision']}."
    if r["upcoming_changes"]:
        expl += " Upcoming: " + "; ".join(f"{u['doc_id']} ({u.get('value', '')}) from {u['effective_from']}"
                                          for u in r["upcoming_changes"]) + "."
    r.update(answer_type="retrieved_fact", answer=answer, citations=[cit], applied_rules=[_applied(rule)],
             explanation=expl)
    return r


def _doc_block(c: dict) -> str:
    m = c["meta"]
    text, _ = sanitize(c["text"])
    tag = " informational=\"level 5 - unofficial, never authoritative\"" if c.get("informational") else ""
    return (f"<document id=\"{c['chunk_id']}\" title=\"{m.get('title')}\" section=\"{m.get('section')}\" "
            f"page=\"{m.get('page')}\" authority_level=\"{m.get('authority_level')}\" version=\"{m.get('version')}\" "
            f"effective_from=\"{_citation_from_meta(m)['effective_from']}\"{tag}>\n{text}\n</document>")


def _compose_text(state, r, usage, warnings):
    chunks = state.get("ordered_chunks", [])
    threshold = get_settings().not_found_threshold
    authoritative = [c for c in chunks if not c.get("informational")]
    if not authoritative or max(c["score"] for c in authoritative) < threshold:
        return _not_found(r, f"No applicable authorised source scored above the relevance threshold ({threshold}).")
    top = sorted(authoritative, key=lambda c: -c["score"])[:MAX_DOCS_TO_LLM]
    # keep precedence order among the selected chunks
    top = [c for c in chunks if c in top]
    evidence = "\n".join(c["text"] for c in top)
    missing_proper = H.proper_nouns_missing(state["question"], evidence)
    if missing_proper:
        return _not_found(r, f"The sources do not mention: {', '.join(missing_proper)}.")
    if any(c["meta"].get("suspicious") for c in top):
        warnings.append("instruction-like text in a retrieved document was masked (R8)")
    r["conflicts_detected"] = [{"type": "document", "overridden": f"{o['doc_id']}#{o['section']}", "reason": o["reason"]}
                               for o in state.get("overridden_chunks", []) if o["reason"].startswith("step 2")]

    out: ComposeOut | None = None
    if llm.enabled():
        user = (f"<question>{state.get('rewritten_question') or state['question']}</question>\n"
                f"<as_of_date>{state['as_of_date']}</as_of_date>\n"
                f"<precedence>{state.get('precedence_decision', '')}</precedence>\n"
                + "\n".join(_doc_block(c) for c in top))
        out = call_json(COMPOSE_SYSTEM, user, ComposeOut, usage)
    if out is not None:
        ids = {c["chunk_id"]: c for c in top}
        used = [ids[i] for i in out.used_chunk_ids if i in ids]
        if not out.sufficient:
            return _not_found(r, "The retrieved documents do not contain this information.")
        if not used:
            used = top[:1]
            warnings.append("validator: LLM cited no valid chunk ids; top precedence chunk cited")
        bad = ungrounded_numbers(out.answer + " " + out.explanation, user + " " + state["question"])
        if bad:
            warnings.append(f"validator: ungrounded numbers {bad} in LLM answer; extractive answer used")
            out = None
        else:
            r.update(answer=out.answer.strip(), explanation=out.explanation.strip(),
                     citations=_dedupe([_citation_from_meta(c["meta"]) for c in used]), answer_type="retrieved_fact")
    if out is None:
        if not llm.enabled():
            miss = missing_terms(state["question"], evidence)
            if miss and len(miss) / max(1, len(set(t for t in H._toks(state["question"]) if len(t) >= 4))) > 0.5:
                return _not_found(r, f"Retrieved text does not cover: {', '.join(sorted(miss))}.")
        # relevance first, then precedence among near-equally relevant passages
        best_score = max(c["score"] for c in top)
        near = [c for c in top if c["score"] >= best_score - RELEVANCE_MARGIN]
        # deterministic extractive mode: among near-equal passages prefer the one sharing most question terms
        # (passages covering most of the question compete on authority level: official beats FAQ)
        qterms = content_terms(state["question"])
        ov = {c["chunk_id"]: len(qterms & content_terms(c["text"])) for c in near}
        top_ov = max(ov.values()) or 1
        best = min(near, key=lambda c: (ov[c["chunk_id"]] < 0.6 * top_ov, int(c["meta"].get("authority_level", 4)),
                                        -ov[c["chunk_id"]], near.index(c)))
        picked = [best] + [c for c in near[1:2] if c["meta"]["doc_id"] == best["meta"]["doc_id"]]
        m = best["meta"]
        snippet = " ".join(" ".join(c["text"].split()) for c in picked)
        snippet, _ = sanitize(snippet[:900] + ("..." if len(snippet) > 900 else ""))
        r.update(answer_type="retrieved_fact", citations=_dedupe([_citation_from_meta(c["meta"]) for c in picked]),
                 answer=f"According to {m.get('title')} (§{m.get('section')}, p.{m.get('page')}): {snippet}",
                 explanation="Extractive answer: the most authoritative applicable passage is quoted directly. "
                             f"Precedence: {state.get('precedence_decision', '')}")
    if any(c.get("informational") for c in chunks):
        r["explanation"] += " Level-5 (unofficial) sources were found but are informational only."
    return r


# ------------------------------------------------------------------ 9 validate
def _validate(state):
    """Final deterministic checks: every citation must point at a registered source, factual answers need a
    citation, refusals/clarifications carry no evidence fields."""
    r = dict(state["response"])
    warnings = list(state.get("warnings", []))
    known = {s["doc_id"]: s for s in repo.list_sources()}
    good = [c for c in r["citations"] if c["doc_id"] in known]
    if len(good) != len(r["citations"]):
        warnings.append("validator: dropped citation(s) to unregistered documents")
    r["citations"] = good
    if r["answer_type"] in ("retrieved_fact", "conflict_flagged") and not good:
        warnings.append("validator: factual answer without a valid citation -> not_found")
        r = _not_found(r, "No verifiable citation supports an answer.")
    if r["answer_type"] in ("refused", "clarification_needed"):
        r["citations"], r["applied_rules"] = [], []
    return {"response": r, "warnings": warnings}




# ================================================================== architecture-level nodes
# Query Router -> {RAG | Structured | Hybrid} path -> Evidence/Source Authority Validator -> Qwen3 generate
# -> Safety & Grounding guardrails -> finalize (audit)

STRUCTURED_TOOLS = {"find_course", "get_student_profile", "get_attendance", "get_results", "resolve_rule",
                    "check_exam_eligibility", "check_supplementary_eligibility", "check_placement_eligibility"}


def route_for(plan_steps: list[str]) -> str:
    """rag = documents only; structured = SQLite/rule tools only; hybrid = both."""
    rag = "retrieve" in plan_steps
    tools = any(s in STRUCTURED_TOOLS for s in plan_steps)
    return "hybrid" if rag and tools else "structured" if tools else "rag"


@timed
def query_router(state):
    """Understand the question (LLM JSON + keyword fallback), build an allowlisted plan, pick the path."""
    upd = _classify(state)
    if upd.get("refusal"):
        return upd
    planned = _plan({**state, **upd})
    upd.update(planned)
    upd["route"] = route_for(planned["plan"])
    return upd


@timed
def rag_path(state):
    """BGE query embedding -> ChromaDB top-k chunks with Annex B metadata."""
    return _retrieve(state)


@timed
def structured_path(state):
    """Deterministic SQLite + rule-registry tools (no retrieval needed)."""
    return _run_tools(state)


@timed
def hybrid_path(state):
    """Both: tools compute the result, retrieval fetches the clause/procedure text behind it."""
    out = _retrieve(state)
    out.update(_run_tools({**state, **out}))
    return out


@timed
def evidence_validator(state):
    """Source-authority validation: Annex A precedence over retrieved chunks and registry rules (as_of_date,
    scope, supersession, authority, recency) -> ordered applicable evidence, overridden + upcoming sources."""
    return _resolve_precedence(state)


@timed
def generate(state):
    """Qwen3-8B (Ollama) writes grounded text from verified evidence; calculated answers are code templates."""
    return _compose(state)


@timed
def guardrails(state):
    """Safety & grounding: registered citations only, factual answers must be cited, else not_found."""
    return _validate(state)


# ------------------------------------------------------------------ 10 finalize
@timed
def finalize(state):
    r = state.get("response") or _compose(state)["response"]
    if r["answer_type"] == "not_found":
        r["answer"] = NOT_FOUND_MESSAGE
    latency = int((time.perf_counter() - state["t0"]) * 1000)
    st = dict(state)
    st["timings"] = state.get("timings", {})
    record = audit.build_record(st, r, latency)
    audit.log(record)
    session_store.update(state.get("session_id"), state.get("student_id"), state.get("memory", {}),
                         state["question"], r,
                         {"course": (state.get("course") or {}).get("course_code") or state.get("entities", {}).get("course"),
                          "intent": state.get("intent") if state.get("intent") in INTENT_ALLOWLIST else None,
                          "check": state.get("entities", {}).get("eligibility_check"),
                          "data_needed": state.get("entities", {}).get("data_needed"),
                          "parameter": state.get("parameter")})
    return {"response": r}
