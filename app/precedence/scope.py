"""Programme / batch scope matching (Annex A step 1)."""
import re


def _norm_prog(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(".", "").strip().lower())


def programme_in_scope(programme: str | None, scope: str | None) -> bool:
    """scope: ALL | 'B.Tech' (covers 'B.Tech CSE') | 'B.Tech CSE;B.Tech IT'."""
    if not scope or scope.strip().upper() == "ALL" or not programme:
        return True
    p = _norm_prog(programme)
    for part in scope.split(";"):
        s = _norm_prog(part)
        if s and (p == s or p.startswith(s + " ")):
            return True
    return False


def batch_in_scope(batch_year: int | None, scope: str | None) -> bool:
    """scope: ALL | 2023 | 2023+ | 2021-2023, ';'-separated."""
    if not scope or scope.strip().upper() == "ALL" or batch_year is None:
        return True
    for part in scope.split(";"):
        part = part.strip()
        if m := re.fullmatch(r"(\d{4})\+", part):
            if batch_year >= int(m[1]):
                return True
        elif m := re.fullmatch(r"(\d{4})-(\d{4})", part):
            if int(m[1]) <= batch_year <= int(m[2]):
                return True
        elif part.isdigit() and batch_year == int(part):
            return True
        elif part.upper() == "ALL":
            return True
    return False


def scope_label(programmes: str, batches: str) -> str:
    if (programmes or "ALL").upper() == "ALL" and (batches or "ALL").upper() == "ALL":
        return "all students"
    return f"{programmes or 'ALL'} students, batches {batches or 'ALL'}"
