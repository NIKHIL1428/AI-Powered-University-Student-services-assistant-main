"""Clause-aware chunking: one numbered clause = one chunk (split >350 words with 50-word overlap).

Sections carry across page breaks, but a chunk never spans pages so the cited page is exact.
"""
import re
from dataclasses import dataclass

HEADING = re.compile(
    r"^\s*(?:(?:clause|section|rule|article|regulation)\s+)?(\d{1,2}(?:\.\d{1,2}){0,3}|Q\d{1,3})[.):]?\s+"
    r"(?!(?:lakhs?|crores?|cr|lpa|rs|inr|percent|years?|months?|days?|hours?|hrs|am|pm|a\.m|p\.m|kg|km)\b)"
    r"(?=[A-Za-z(\"'])",
    re.I)
# after "Copy to:" the numbered lines are a distribution list, not clauses
COPY_TO = re.compile(r"^\s*copy\s*(to|forwarded)", re.I)
# a clause number alone on its line ("11.2." followed by the clause text on the next lines), as in NSUT's
# regulations; only dotted numbers, or "11." followed by an ALL-CAPS title, so table serial numbers are not headings
NUMBER_ONLY = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s*$|^\s*(\d{1,2})\.?\s*$")
MAX_WORDS, OVERLAP = 350, 50


def _number_only_heading(lines: list[str], i: int):
    m = NUMBER_ONLY.match(lines[i])
    if not m:
        return None
    if m.group(1):
        return re.match(r"\s*(\d{1,2}(?:\.\d{1,2}){1,3})", lines[i])
    nxt = next((ln.strip() for ln in lines[i + 1:i + 3] if ln.strip()), "")
    if nxt and nxt.upper() == nxt and re.search(r"[A-Z]{4,}", nxt):
        return re.match(r"\s*(\d{1,2})", lines[i])
    return None


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    page: int
    section: str
    heading: str
    text: str


def _split_words(text: str) -> list[str]:
    words = text.split()
    if len(words) <= MAX_WORDS:
        return [text]
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + MAX_WORDS]))
        if i + MAX_WORDS >= len(words):
            break
        i += MAX_WORDS - OVERLAP
    return out


def chunk_clauses(doc_id: str, pages: list[tuple[int, str]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    section, heading = "", ""
    for page_no, text in pages:
        buf: list[str] = []
        cur_sec, cur_head = section, heading

        def flush():
            body = "\n".join(buf).strip()
            if len(body) < 15:
                return
            sec = cur_sec or f"p{page_no}"
            for piece in _split_words(body):
                idx = sum(1 for c in chunks if c.page == page_no and c.section == sec)
                chunks.append(Chunk(f"{doc_id}::p{page_no}::s{sec}::{idx}", doc_id, page_no, sec, cur_head, piece))

        lines = text.splitlines()
        in_copy = False
        for i, line in enumerate(lines):
            in_copy = in_copy or bool(COPY_TO.match(line))
            m = None if in_copy else (HEADING.match(line) or _number_only_heading(lines, i))
            if m and len(line) < 400:
                flush()
                buf = []
                cur_sec, cur_head = m.group(1), line.strip()[:120]
            buf.append(line)
        flush()
        section, heading = cur_sec, cur_head
    return chunks


def chunk_fixed(doc_id: str, pages: list[tuple[int, str]], size: int = 500, overlap: int = 50) -> list[Chunk]:
    """Baseline for the eval comparison: fixed-size character windows, section = page."""
    chunks = []
    for page_no, text in pages:
        t = re.sub(r"\s+", " ", text).strip()
        i = 0
        while i < len(t):
            piece = t[i:i + size]
            if len(piece) >= 15:
                chunks.append(Chunk(f"{doc_id}::p{page_no}::fixed::{i}", doc_id, page_no, f"p{page_no}", "", piece))
            i += size - overlap
    return chunks
