"""Post-generation checks: citations come from retrieved metadata; numbers must be grounded in evidence."""
import re

NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
STOP = set("""a an the is are was were be been of to in on for and or with by at from as it its this that what which
who whom how when where why do does did can could will would should shall may might must my me i you your our we
they them their there here than then about into any all some no not yes if so such per each other more most less
please tell know want need get give find show list much many required requirement requirements rule rules
minimum maximum students student university nsut college""".split())


def _canon(n: str) -> str:
    return n.rstrip("0").rstrip(".") if "." in n else n.lstrip("0") or "0"


def numbers(text: str) -> set[str]:
    return {_canon(n) for n in NUM.findall(text or "")}


def ungrounded_numbers(answer: str, evidence: str) -> list[str]:
    """Numbers in the answer that do not occur anywhere in the evidence text (1-digit list markers ignored)."""
    ev = numbers(evidence)
    return sorted(n for n in numbers(answer) if n not in ev and not (len(n) == 1 and n.isdigit()))


def content_terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]{4,}", (text or "").lower()) if t not in STOP}


def missing_terms(question: str, evidence: str) -> set[str]:
    ev = (evidence or "").lower()
    return {t for t in content_terms(question) if t[:5] not in ev}
