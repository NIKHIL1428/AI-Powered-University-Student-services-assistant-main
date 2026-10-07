"""Deterministic fallbacks used when the LLM is mocked/down or returns invalid JSON.

Also used to sanity-merge LLM classification (the LLM never decides identity or tools on its own).
"""
import re

from app.llm.prompts import ClassifyOut

ALIASES = {"maths": "mathematics", "math": "mathematics", "dsa": "data structures", "ds": "data structures",
           "dbms": "database management systems", "os": "operating systems", "cn": "computer networks",
           "oops": "object oriented programming", "oop": "object oriented programming",
           "daa": "design and analysis of algorithms", "coa": "computer organization and architecture",
           "toc": "theory of computation", "se": "software engineering", "ai": "artificial intelligence",
           "ml": "machine learning"}
ROMAN = {"i", "ii", "iii", "iv", "v", "1", "2", "3", "4"}

PERSONAL = re.compile(r"\b(my|mine|am i|i am|i'm|i have|i've|i failed|i got|do i|can i|will i|should i|me|i)\b", re.I)
PROCEDURE = re.compile(r"\b(how (do|can|to|should|does|is)|procedure|process|steps?|apply|application|"
                       r"register(ation)?|form|submit|where (do|can|should|to)|whom|deadline|last date)\b", re.I)
ELIG = re.compile(r"\b(eligib\w*|allowed to|permitted|can i (sit|appear|write|take|register)|qualif\w*|"
                  r"debarred|detained)\b", re.I)
WHATIF = re.compile(r"\b(if i|what if|suppose|assuming|after i|once i|in case i)\b", re.I)
# questions that can only be answered from the asker's own records
OWN_RECORDS = re.compile(r"\b(my|mine|am i|do i have|have i)\b", re.I)
DATA = re.compile(r"\b(attendance|marks?|grades?|results?|scores?|cgpa|sgpa|backlogs?|semester|profile)\b", re.I)


def detect_check(q: str) -> str:
    ql = q.lower()
    if "placement" in ql or "placements" in ql or "campus recruitment" in ql:
        return "placement"
    if re.search(r"supplementar|supple\b|re-?exam|back ?paper|reappear", ql):
        return "supplementary"
    if re.search(r"end.?sem|mid.?sem|exam|appear|attendance|relax|condon|\bmse\b|\bese\b", ql):
        return "exam"
    return "none"


THRESHOLD = re.compile(r"\b(minimum|maximum|min|max|required|requirement|requirements|need(ed)?|enough|"
                       r"cut-?off|criteria|criterion|percentage|how much|how many|at least|rule|threshold|"
                       r"passing|pass marks?|eligib\w*|who can|which students|applies|cgpa)\b|%", re.I)


def detect_parameter(q: str) -> str | None:
    ql = q.lower()
    if not THRESHOLD.search(q):
        return None
    if "placement" in ql:
        if "backlog" in ql:
            return "placement_max_backlogs"
        return "placement_min_cgpa"
    if re.search(r"supplementar", ql) and re.search(r"eligib|who can|allowed|which students", ql):
        return "supplementary_allowed_results"
    if re.search(r"relax|condon", ql):
        if "how many times" in ql or "times" in ql:
            return "max_attendance_relaxations"
        if re.search(r"after (the )?relax|floor|lowest|below which|even with relax", ql):
            return "min_attendance_after_relaxation_pct"
        return "attendance_relaxation_dean_pct"
    if "attendance" in ql:
        return "min_attendance_pct"
    if re.search(r"pass(ing)? marks?|marks? (required )?to pass|minimum marks|pass mark|passing (criteria|percentage)", ql):
        return "min_total_marks_pct"
    return None


def keyword_classify(q: str) -> ClassifyOut:
    personal = bool(PERSONAL.search(q))
    procedure = bool(PROCEDURE.search(q))
    elig = bool(ELIG.search(q))
    whatif = bool(WHATIF.search(q))
    check = detect_check(q)
    ql = q.lower()
    data_needed = []
    if "attendance" in ql:
        data_needed.append("attendance")
    if re.search(r"\b(marks?|results?|grades?|scores?|fail\w*|pass\w*)\b", ql):
        data_needed.append("results")
    if re.search(r"\b(cgpa|sgpa|backlogs?|semester|profile|batch|programme)\b", ql):
        data_needed.append("profile")

    if personal and whatif and (elig or check == "placement"):
        intent = "multi_step"
    elif personal and elig:
        intent = "personal_eligibility"
    elif personal and procedure and (not re.search(r"\bmy\b", ql) or
                                     re.search(r"\b(where|how|whom|when)\b.{0,30}\b(submit|apply|pay|get|register)",
                                               ql)):
        intent = "procedure"          # "where should I submit my medical certificate" asks for a procedure
    elif personal and re.search(r"\bmy\b|\bi (have|got|failed)\b|\bam i\b", ql) and DATA.search(q):
        intent = "personal_data"
    elif procedure:
        intent = "procedure"
    else:
        intent = "policy_fact"
    return ClassifyOut(intent=intent, course=None, data_needed=data_needed,
                       eligibility_check=check if intent in ("personal_eligibility", "multi_step") else "none",
                       parameter=detect_parameter(q), assume_pass=whatif)


def _toks(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def course_mention(q: str, courses: list[dict]) -> str | None:
    """Find a course reference in free text, restricted to the student's courses."""
    ql = q.lower()
    for c in courses:
        if re.search(rf"\b{re.escape(c['course_code'].lower())}\b", ql.replace(" ", "")) or \
           re.search(rf"\b{re.escape(c['course_code'].lower())}\b", ql):
            return c["course_code"]
    expanded = " ".join(ALIASES.get(t, t) for t in _toks(ql))
    full = [c for c in courses if c["course_name"].lower() in ql or " ".join(_toks(c["course_name"])) in expanded]
    if full:
        return max(full, key=lambda c: len(c["course_name"]))["course_name"]
    qset = set(_toks(expanded))
    hits = []
    for c in courses:
        sig = [t for t in _toks(c["course_name"]) if t not in ROMAN and t not in {"and", "of", "to", "the", "in"}]
        if sig and all(t in qset for t in sig):
            hits.append(" ".join(sig))
    if hits:
        return max(hits, key=len)
    return None


def proper_nouns_missing(q: str, evidence: str) -> list[str]:
    """Capitalised words (not sentence-initial, not acronyms we know) absent from evidence."""
    words = re.findall(r"(?<![.?!]\s)(?<!^)\b([A-Z][a-z]{3,})\b", q.strip())
    ev = evidence.lower()
    skip = {"what", "when", "where", "which", "how", "data", "structures", "mathematics", "placement",
            "exam", "semester", "university", "nsut"}
    return [w for w in words if w.lower() not in skip and w.lower()[:5] not in ev]


FOLLOWUP = re.compile(r"^\s*(and|aur|what about|how about|same for|also|then|ok and|in)\b", re.I)


def is_followup(q: str) -> bool:
    return bool(FOLLOWUP.search(q)) or len(q.split()) <= 4
