"""Personal-data gate for documents (guide 4.1: no documents with names or roll numbers - exclude or redact).

Official NSUT notices often append student lists (short attendance, detention, make-up exams, UFM, fee defaulters).
Policy: keep the notice text, drop the list.
  1. On each page, everything from the first list header ("Name"/"Roll No" table header) or first roll-number line
     onward is removed (closing "Copy to / approval" lines are kept).
  2. Once a list has started, later pages that still contain roll numbers / list headers are dropped entirely.
  3. If a document contained a list at all, a strict filter keeps only prose lines (>= 5 words) and official
     header lines - short capitalised lines are how names appear in OCR'd or text-layer tables.
Runs on every ingest (including judge uploads) before chunking/embedding, so personal data never reaches Chroma.
"""
import re

# NSUT roll numbers look like 2021UCS1588 / 2024U1C3636 / 2023UEC1234 (OCR may mangle letters into digits)
ROLL = re.compile(r"\b(19|20)\d{2}\s?[A-Z0-9]{1,4}[A-Z][A-Z0-9]{0,3}\s?\d{3,5}\b")
ROLL_FRAGMENT = re.compile(r"\b(19|20)\d{2}[A-Z]{2,4}\d{0,4}\b")
LIST_HEADER = re.compile(r"(student'?s?\s*name|name\s*of\s*(the\s*)?student|roll\s*\.?\s*no|enrol+ment\s*no|"
                         r"\bS\.?\s*No\.?\b.{0,40}\bname\b|^\s*name\s*$)", re.I)
OFFICIAL = re.compile(r"(dated|f\.?\s*no|no\.?\s*f\.|notification|notice|subject|university|technology|"
                      r"copy\s*(to|forwarded)|registrar|dean|controller|semester|approval|authority|www\.|phone)",
                      re.I)
CLOSING = re.compile(r"issues?\s*with\s*the\s*approval|competent\s*authority|copy\s*(to|forwarded)", re.I)
MARK = "[student list removed: personal data redacted]"
MARK_CONT = "[student list continued: personal data redacted]"


def count_rolls(text: str) -> int:
    return len(ROLL.findall(text or ""))


def redact_page(text: str) -> tuple[str, int]:
    """Returns (kept_text, removed_line_count)."""
    lines = text.splitlines()
    cut = next((i for i, ln in enumerate(lines) if LIST_HEADER.search(ln) or ROLL.search(ln)), None)
    if cut is None:
        return text, 0
    kept = [ln for ln in lines[:cut] if not ROLL.search(ln)]
    tail_start = next((j for j in range(len(lines) - 1, cut, -1) if CLOSING.search(lines[j])), None)
    tail = []
    if tail_start is not None:
        tail = [ln for ln in lines[tail_start:] if not ROLL.search(ln) and not LIST_HEADER.search(ln)]
    return "\n".join(kept + [MARK] + tail), len(lines) - len(kept) - len(tail)


def strict_filter(text: str) -> str:
    keep = []
    for ln in text.splitlines():
        if ROLL.search(ln) or ROLL_FRAGMENT.search(ln):
            continue
        if ln.startswith("[student list") or len(ln.split()) >= 5 or OFFICIAL.search(ln):
            keep.append(ln)
    return "\n".join(keep)


def redact_pages(pages: list[str]) -> tuple[list[str], dict]:
    out, removed, in_list = [], 0, False
    for t in pages:
        has = count_rolls(t) > 0 or bool(LIST_HEADER.search(t))
        if in_list and has:
            out.append(MARK_CONT)
            removed += len(t.splitlines())
            continue
        kept, r = redact_page(t)
        in_list = in_list or bool(r)
        out.append(kept)
        removed += r
    flagged = in_list or any(count_rolls(p) for p in pages)
    if flagged:
        out = [strict_filter(p) for p in out]
    return out, {"flagged": flagged, "lines_removed": removed,
                 "rolls_before": sum(count_rolls(p) for p in pages), "rolls_after": sum(count_rolls(p) for p in out)}
