"""Unified document loader: PDF / TXT / MD / HTML / images -> per-page text.

PDF pages use the text layer when it has >= 50 chars, otherwise OCR (Tesseract or RapidOCR). Images are OCR'd.
HTML is reduced to visible text (scripts/styles dropped, block tags become line breaks so clause headings survive).
"""
import hashlib
import html as htmllib
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.ingestion.ocr import OCRUnavailable, ocr_page

MIN_TEXT_CHARS = 50


@dataclass
class PageText:
    page: int
    text: str
    ocr: bool
    confidence: float | None = None


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


SUPPORTED = {".pdf", ".txt", ".md", ".html", ".htm", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|section|article|table)>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", " | ", raw)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", raw))
    return "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines() if ln.strip())


def _render(page, dpi: int = 300) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return arr[:, :, :3] if pix.n >= 3 else arr


def extract_pages(path: Path, data: bytes, warnings: list[str]) -> list[PageText]:
    h = file_hash(data)
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        text = data.decode("utf-8", errors="replace")
        # form-feed separates pages in plain-text sources
        return [PageText(i + 1, t, False) for i, t in enumerate(text.split("\f"))]
    if suffix in {".html", ".htm"}:
        return [PageText(1, html_to_text(data.decode("utf-8", errors="replace")), False)]
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        import cv2
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        try:
            t, c = ocr_page(h, 1, lambda: img[:, :, ::-1])
            return [PageText(1, t, True, c)]
        except OCRUnavailable as e:
            warnings.append(str(e))
            return []
    if suffix != ".pdf":
        raise ValueError(f"unsupported file type {suffix}")

    import pymupdf
    pages: list[PageText] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            if len(text.strip()) >= MIN_TEXT_CHARS:
                pages.append(PageText(i + 1, text, False))
                continue
            try:
                t, c = ocr_page(h, i + 1, lambda p=page: _render(p))
                pages.append(PageText(i + 1, t, True, c))
                if c < 60:
                    warnings.append(f"page {i + 1}: low OCR confidence {c:.0f}")
            except OCRUnavailable as e:
                if str(e) not in warnings:
                    warnings.append(str(e))
                pages.append(PageText(i + 1, text, False))
    return pages
