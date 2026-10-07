"""R7: identity comes only from the X-Student-Id header. Requests for other students' data are refused."""
import re

from app.db import repo

STUDENT_ID = re.compile(r"^S\d{4}$")
ID_IN_TEXT = re.compile(r"\bS\d{4}\b", re.I)
THIRD_PARTY = re.compile(
    r"\b(my\s+(friend|classmate|roommate|brother|sister|batchmate)s?'?s?|friend'?s|classmate'?s|"
    r"(another|other|some other|a different)\s+student'?s?|someone\s+else'?s?)\b", re.I)
DATA_WORDS = re.compile(r"\b(attendance|marks?|grades?|results?|cgpa|sgpa|backlogs?|eligib\w*|record|profile|"
                        r"detained|scores?)\b", re.I)


def validate_header(student_id: str | None) -> tuple[str | None, str | None]:
    """Returns (normalised_id, error). Empty header -> (None, None) = general user."""
    if student_id is None or not student_id.strip():
        return None, None
    sid = student_id.strip().upper()
    if not STUDENT_ID.match(sid):
        return None, "X-Student-Id must look like S1234"
    if not repo.student_exists(sid):
        return None, f"unknown student id {sid}"
    return sid, None


def other_student_reference(question: str, student_id: str | None) -> str | None:
    """Return a reason string if the question targets another student's data."""
    for m in ID_IN_TEXT.findall(question):
        if m.upper() != (student_id or ""):
            return f"question references student id {m.upper()}"
    q = question.lower()
    for sid, name in repo.all_student_names():
        if sid != student_id and name and len(name.split()) >= 2 and name.lower() in q:
            return "question references another student by name"
    if THIRD_PARTY.search(question) and DATA_WORDS.search(question):
        return "question asks for another person's records"
    return None
