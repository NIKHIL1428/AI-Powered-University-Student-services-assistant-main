"""OCR / text-layer noise cleanup."""
import re
from collections import Counter


def _fix_digits(m: re.Match) -> str:
    return m.group(0).replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")


def clean_text(text: str) -> str:
    text = text.replace("­", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"[“”]", '"', text)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)                          # hyphenated line breaks
    text = re.sub(r"(?<=\d)[OolI](?=\d)|(?<=\d)[OolI](?=\s*%)", _fix_digits, text)  # 7O% -> 70%
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(ln for ln in lines if not (len(ln) < 130 and LETTERHEAD.search(ln))).strip()


# university letterhead lines repeated on every notice: they carry no content and dominate small chunks' embeddings
LETTERHEAD = re.compile(r"netaji\s*subhas|azad\s*hind\s*fa\w*\s*marg|phone\s*no|fax[.:]|website\s*:|"
                        r"a\s*state\s*university|govt\.?\s*of\s*n\.?\s*c\.?\s*t|^\s*nsu[it]?\W*$|^dwarka", re.I)


def strip_repeating_lines(pages: list[str], min_pages: int = 3) -> list[str]:
    """Remove header/footer lines that repeat on most pages (page numbers normalised)."""
    if len(pages) < min_pages:
        return pages
    norm = lambda l: re.sub(r"\d+", "#", l.strip().lower())
    counts = Counter()
    for p in pages:
        lines = [l for l in p.splitlines() if l.strip()]
        counts.update({norm(l) for l in lines[:3] + lines[-3:]})
    repeated = {k for k, v in counts.items() if v >= max(min_pages, int(0.6 * len(pages))) and len(k) < 120}
    return ["\n".join(l for l in p.splitlines() if norm(l) not in repeated) for p in pages]
