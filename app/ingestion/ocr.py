"""OCR for scanned pages: Tesseract (primary, in the Docker image) or RapidOCR (pip-only fallback for hosts
without the tesseract binary). OpenCV preprocessing; per-page cache keyed by file hash so restarts never re-OCR."""
import json
import shutil
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import get_settings


class OCRUnavailable(RuntimeError):
    pass


def tesseract_available() -> bool:
    try:
        import pytesseract
        return bool(shutil.which(pytesseract.pytesseract.tesseract_cmd) or shutil.which("tesseract"))
    except Exception:
        return False


@lru_cache(maxsize=1)
def _rapid():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except Exception:
        return None


def engine() -> str | None:
    pref = get_settings().ocr_engine
    if pref in ("auto", "tesseract") and tesseract_available():
        return "tesseract"
    if pref in ("auto", "rapidocr") and _rapid() is not None:
        return "rapidocr"
    return None


def _cache_file(file_hash: str, page_no: int) -> Path:
    d = get_settings().path(get_settings().ocr_cache_dir) / file_hash
    d.mkdir(parents=True, exist_ok=True)
    return d / f"page_{page_no}.json"


def preprocess(img: np.ndarray) -> np.ndarray:
    import cv2
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
    gray = cv2.medianBlur(gray, 3)
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


def _tesseract(img: np.ndarray) -> tuple[str, float]:
    import pytesseract
    data = pytesseract.image_to_data(preprocess(img), lang=get_settings().ocr_lang, config="--psm 6",
                                     output_type=pytesseract.Output.DICT)
    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        lines.setdefault((data["block_num"][i], data["par_num"][i], data["line_num"][i]), []).append(word)
        if float(data["conf"][i]) >= 0:
            confs.append(float(data["conf"][i]))
    return "\n".join(" ".join(ws) for _, ws in sorted(lines.items())), (sum(confs) / len(confs) if confs else 0.0)


def _rapidocr(img: np.ndarray) -> tuple[str, float]:
    result, _ = _rapid()(img)
    if not result:
        return "", 0.0
    # result: [[box, text, score], ...]; rebuild reading order line by line from box y/x
    items = sorted(((b[0][1], b[0][0], t, float(s)) for b, t, s in result), key=lambda r: (r[0], r[1]))
    lines, cur, last_y = [], [], None
    for y, x, t, s in items:
        if last_y is not None and abs(y - last_y) > 12:
            lines.append(" ".join(w for _, w in sorted(cur)))
            cur = []
        cur.append((x, t))
        last_y = y
    if cur:
        lines.append(" ".join(w for _, w in sorted(cur)))
    return "\n".join(lines), 100 * sum(r[3] for r in items) / len(items)


def ocr_image(img: np.ndarray) -> tuple[str, float]:
    """Returns (text with line breaks, mean confidence 0-100)."""
    eng = engine()
    if eng == "tesseract":
        return _tesseract(img)
    if eng == "rapidocr":
        return _rapidocr(img)
    raise OCRUnavailable("no OCR engine: install tesseract-ocr (Docker image) or `pip install rapidocr-onnxruntime`")


def ocr_page(file_hash: str, page_no: int, img_fn) -> tuple[str, float]:
    """img_fn: lazy callable returning an RGB numpy array (rendering is skipped on cache hit)."""
    cf = _cache_file(file_hash, page_no)
    if cf.exists():
        d = json.loads(cf.read_text(encoding="utf-8"))
        return d["text"], d["confidence"]
    text, conf = ocr_image(img_fn())
    cf.write_text(json.dumps({"text": text, "confidence": conf, "engine": engine()}), encoding="utf-8")
    return text, conf
