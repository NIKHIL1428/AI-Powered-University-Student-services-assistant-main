"""ChromaDB retrieval over the fixture corpus: relevance, Annex B metadata, no date filter, HTML loading."""
from app.ingestion.document_loader import html_to_text
from app.retrieval.retriever import retrieve, to_candidate


def test_top_k_finds_the_procedure_clause():
    hits = retrieve("How do I apply for the supplementary examination?", k=4)
    assert any(h["meta"]["doc_id"] == "FIX-REG-2024" and h["meta"]["section"] == "9.2" for h in hits)


def test_chunk_metadata_is_complete():
    h = retrieve("minimum attendance", k=1)[0]
    for k in ("doc_id", "title", "authority_level", "version", "effective_from", "effective_to", "supersedes",
              "scope_programmes", "scope_batches", "section", "page", "synthetic", "suspicious"):
        assert k in h["meta"]
    c = to_candidate(h)
    assert c.authority_level in range(1, 6) and c.effective_from is not None


def test_no_date_filter_upcoming_docs_are_retrievable():
    hits = retrieve("placement registration minimum CGPA 7.0 from 2027", k=8)
    assert any(h["meta"]["doc_id"] == "FIX-PLC-2027" for h in hits)     # effective 2027 -> still retrieved


def test_scores_are_cosine_similarities():
    hits = retrieve("supplementary examination fee", k=3)
    assert all(-1.0 <= h["score"] <= 1.0 for h in hits)
    assert hits == sorted(hits, key=lambda h: -h["score"])


def test_html_loader_keeps_clause_structure():
    text = html_to_text("<html><head><script>x()</script></head><body><h3>7.2 Attendance</h3>"
                        "<p>Minimum 75% &amp; above.</p><table><tr><td>a</td><td>b</td></tr></table></body></html>")
    assert text.splitlines()[0] == "7.2 Attendance" and "75% & above." in text and "x()" not in text
