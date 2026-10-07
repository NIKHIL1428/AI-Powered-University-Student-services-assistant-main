"""One LangGraph StateGraph implementing the architecture:

  auth_guard -> contextualize -> QUERY ROUTER -+-> RAG path ---------+
                                               +-> STRUCTURED path --+-> EVIDENCE / SOURCE AUTHORITY VALIDATOR
                                               +-> HYBRID path ------+        -> QWEN3 generate -> SAFETY & GROUNDING
                                                                                 GUARDRAILS -> finalize (audit) -> END
  refusal (auth or no identity) / clarification short-circuit straight to generate.

The LLM is called only inside query_router (classification JSON) and generate (explanations / text answers).
"""
import time
import uuid
from datetime import date
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.graph import nodes as N
from app.graph.state import GraphState

PATHS = {"rag": "rag_path", "structured": "structured_path", "hybrid": "hybrid_path"}


def _after_auth(s):
    return "generate" if s.get("refusal") else "contextualize"


def _after_router(s):
    if s.get("refusal") or s.get("clarification"):
        return "generate"
    return PATHS[s.get("route", "rag")]


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(GraphState)
    for name in ("auth_guard", "contextualize", "query_router", "rag_path", "structured_path", "hybrid_path",
                 "evidence_validator", "generate", "guardrails", "finalize"):
        g.add_node(name, getattr(N, name))
    g.add_edge(START, "auth_guard")
    g.add_conditional_edges("auth_guard", _after_auth, ["generate", "contextualize"])
    g.add_edge("contextualize", "query_router")
    g.add_conditional_edges("query_router", _after_router, ["generate", *PATHS.values()])
    for path in PATHS.values():
        g.add_edge(path, "evidence_validator")
    g.add_edge("evidence_validator", "generate")
    g.add_edge("generate", "guardrails")
    g.add_edge("guardrails", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


def run(question: str, student_id: str | None, as_of: date | None = None, session_id: str | None = None,
        refusal: str | None = None) -> dict:
    state = {"trace_id": uuid.uuid4().hex[:8], "question": question, "student_id": student_id,
             "as_of_date": as_of or date.today(), "session_id": session_id, "refusal": refusal,
             "t0": time.perf_counter(), "warnings": [], "timings": {}, "llm_calls": 0, "tokens": 0}
    out = build_graph().invoke(state)
    return out["response"]
