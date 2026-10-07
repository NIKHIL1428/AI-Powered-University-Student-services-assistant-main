"""Personal-data gate: student lists in official notices never reach chunks / Chroma / the LLM."""
import json

import pymupdf
from fastapi.testclient import TestClient

from app.guardrails.pii import count_rolls, redact_pages

NOTICE = """NOTIFICATION REGARDING SHORT OF ATTENDANCE
The following B.Tech. students are having very short attendance. Therefore, they are not allowed to appear in the
End Semester Examination.
S.No. Roll No Name Semester
1 2023UCS1234 RAHUL KUMAR V
2 2023UEC4321 PRIYA SHARMA V
This issues with the approval of the Competent Authority.
Copy to: All HoDs"""
CONTINUATION = "3 2023UME1111 AMIT VERMA V\n4 2023UIT2222 NEHA GUPTA V"


def test_list_removed_notice_kept():
    pages, stats = redact_pages([NOTICE, CONTINUATION])
    text = "\n".join(pages)
    assert stats["flagged"] and stats["rolls_before"] == 4 and stats["rolls_after"] == 0
    assert "not allowed to appear" in text
    for name in ("RAHUL", "PRIYA", "AMIT", "NEHA"):
        assert name not in text
    assert "personal data redacted" in text


def test_clean_document_untouched():
    pages, stats = redact_pages(["7.2 A student must have a minimum of 75% attendance."])
    assert not stats["flagged"] and pages[0].startswith("7.2")


def test_ingest_strips_personal_data_before_indexing():
    from app.main import app
    from app.retrieval.retriever import retrieve
    d = pymupdf.open()
    d.new_page().insert_textbox(pymupdf.Rect(56, 56, 539, 786), NOTICE, fontsize=10)
    meta = {"doc_id": "PII-TEST-01", "title": "Short attendance notice (test)", "issuer": "Academics",
            "authority_level": 2, "doc_type": "circular", "version": "1", "effective_from": "2026-01-01",
            "scope_programmes": "ALL", "scope_batches": "ALL", "synthetic": "Y"}
    r = TestClient(app).post("/ingest", files={"file": ("n.pdf", d.tobytes(), "application/pdf")},
                             data={"metadata": json.dumps(meta)})
    assert r.status_code == 200 and any("personal data redacted" in w for w in r.json()["warnings"])
    hits = [h for h in retrieve("short attendance students list RAHUL KUMAR", k=10) if h["meta"]["doc_id"] == "PII-TEST-01"]
    assert hits and all(count_rolls(h["text"]) == 0 and "RAHUL" not in h["text"] for h in hits)
