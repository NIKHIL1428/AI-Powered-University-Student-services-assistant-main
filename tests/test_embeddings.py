"""BGE-small-en-v1.5 local embeddings: 384-d, L2-normalised, query instruction prefix."""
import math

from app.embeddings.bge_model import MODELS, embed_docs, embed_query


def test_bge_dimension_and_norm():
    v = embed_docs(["A student must have a minimum attendance of 75%."], "bge")[0]
    assert len(v) == 384
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-3)


def test_query_prefix_is_used_for_bge_only():
    assert MODELS["bge"]["query_prefix"].startswith("Represent this sentence")
    assert MODELS["minilm"]["query_prefix"] == ""
    q = embed_query("minimum attendance", "bge")
    d = embed_docs(["minimum attendance"], "bge")[0]
    assert q != d                                   # asymmetric: query is embedded with the instruction


def test_semantic_similarity_orders_correctly():
    q = embed_query("How much attendance do I need for exams?", "bge")
    a, b = embed_docs(["Minimum attendance of 75% is required to appear in the examination.",
                       "The library is open on Saturdays from 10 am to 5:30 pm."], "bge")
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))
    assert dot(q, a) > dot(q, b)
