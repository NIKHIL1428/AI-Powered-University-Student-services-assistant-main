"""Build the TEST-ONLY fixture corpus: text sources -> PDFs (one page per '\\f' line).

These documents are clearly marked as fixtures (or synthetic). They exist so the pipeline, precedence engine and
evaluation harness can be exercised before/alongside the official NSUT documents. They are not the submission corpus.
"""
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent


def build():
    out = HERE / "docs"
    out.mkdir(exist_ok=True)
    for src in sorted((HERE / "src").glob("*.txt")):
        pages = [p.strip() for p in src.read_text(encoding="utf-8").split("\\f")]
        doc = pymupdf.open()
        for text in pages:
            page = doc.new_page(width=595, height=842)
            rect = pymupdf.Rect(56, 56, 539, 786)
            page.insert_textbox(rect, text, fontsize=10.5, fontname="helv")
        doc.save(out / f"{src.stem}.pdf")
        doc.close()
    print("built", len(list(out.glob("*.pdf"))), "PDFs in", out)


if __name__ == "__main__":
    build()
