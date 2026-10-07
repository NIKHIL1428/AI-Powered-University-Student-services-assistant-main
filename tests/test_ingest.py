"""R11 live ingestion: a new circular is usable immediately - no code change, no restart."""
import json

import pymupdf
from fastapi.testclient import TestClient

from app.ingestion.chunker import chunk_clauses
from app.ingestion.text_cleaner import clean_text


def _pdf(text: str) -> bytes:
    d = pymupdf.open()
    d.new_page().insert_textbox(pymupdf.Rect(56, 56, 539, 786), text, fontsize=10.5)
    return d.tobytes()


META = {"doc_id": "LIVE-CIRC-2026-12", "title": "Circular ACAD-2026-12: Attendance relaxation (test)",
        "issuer": "Office of the Dean (Academics)", "authority_level": 2, "doc_type": "circular", "version": "1.0",
        "effective_from": "2026-12-01", "effective_to": "", "supersedes": "SYN-CIRC-01#1",
        "scope_programmes": "B.Tech", "scope_batches": "ALL", "provenance": "test", "retrieved_on": "2026-10-06",
        "synthetic": "Y"}
TEXT = ("Circular ACAD-2026-12\nOffice of the Dean (Academics)\n\n1. Attendance relaxation\n"
        "With effect from 1 December 2026, a student must have a minimum of 77% attendance in each course "
        "to be eligible to appear in the end-semester examination.\n")


def client():
    from app.main import app
    return TestClient(app)


def test_live_circular_changes_eligibility(ask):
    before = ask("Am I eligible for the end-sem exam in CS201?", "S8002", as_of="2026-12-15")
    assert before["answer"].startswith("You are not eligible")
    pdf = _pdf(TEXT)
    r = client().post("/ingest", files={"file": ("circ.pdf", pdf, "application/pdf")},
                      data={"metadata": json.dumps(META)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc_id"] == META["doc_id"] and body["chunks_indexed"] >= 1 and body["status"] == "ingested"
    assert body["rules_extracted"] == 1 and body["rules"][0]["value"] == "77"
    after = ask("Am I eligible for the end-sem exam in CS201?", "S8002", as_of="2026-12-15")
    assert after["answer"].startswith("You are eligible")
    assert after["applied_rules"][0]["source_doc_id"] == META["doc_id"]
    # before its effective date it is only an upcoming change
    now = ask("What is the minimum attendance required to appear for end-semester exams?", as_of="2026-10-06")
    assert ">=80%" in now["answer"]
    assert any(u["doc_id"] == META["doc_id"] for u in now["upcoming_changes"])
    # re-upload of the same file is a no-op
    again = client().post("/ingest", files={"file": ("circ.pdf", pdf, "application/pdf")},
                          data={"metadata": json.dumps(META)})
    assert again.json()["status"] == "unchanged"


def test_bad_metadata_422():
    bad = {**META, "authority_level": 9}
    r = client().post("/ingest", files={"file": ("x.pdf", _pdf(TEXT), "application/pdf")},
                      data={"metadata": json.dumps(bad)})
    assert r.status_code == 422
    r = client().post("/ingest", files={"file": ("x.pdf", _pdf(TEXT), "application/pdf")}, data={"metadata": "{"})
    assert r.status_code == 422


def test_explicit_rules_in_metadata():
    meta = {**META, "doc_id": "LIVE-PLC-RULES", "supersedes": "", "effective_from": "2030-01-01",
            "rules": [{"parameter": "placement_min_cgpa", "operator": ">=", "value": "7.5", "section": "2"}]}
    r = client().post("/ingest", files={"file": ("p.txt", b"2. Placement CGPA rule text", "text/plain")},
                      data={"metadata": json.dumps(meta)})
    assert r.status_code == 200 and r.json()["rules"][0]["method"] == "metadata"


def test_clause_chunking_and_cleaning():
    pages = [(1, clean_text("7. Attendance\n7.2 A student must have 7O% atten-\ndance.\n7.3 Condonation up to 10%."))]
    chunks = chunk_clauses("D", pages)
    assert [c.section for c in chunks] == ["7.2", "7.3"]          # heading-only line is not a chunk
    assert "70% attendance" in chunks[0].text
    assert chunks[0].chunk_id == "D::p1::s7.2::0"
