from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db import repo
from app.llm import qwen as llm
from app.vectorstore import chroma_manager as vector_store

router = APIRouter()


@router.get("/health")
def health():
    out = {"api": "ok"}
    try:
        out["vector_store"] = {"status": "ok", "chunks": vector_store.count(),
                               "collection": vector_store.collection_name()}
    except Exception as e:
        out["vector_store"] = {"status": "down", "error": type(e).__name__}
    try:
        c = repo.counts()
        out["sqlite"] = {"status": "ok", "students": c["students"], "rules": c["rule_registry"],
                         "sources": c["source_register"]}
    except Exception as e:
        out["sqlite"] = {"status": "down", "error": type(e).__name__}
    out["llm"] = llm.health()
    from app.main import BOOTSTRAP
    out["bootstrap"] = BOOTSTRAP
    return out


@router.get("/audit/{trace_id}")
def audit(trace_id: str):
    rec = repo.get_audit(trace_id)
    if not rec:
        raise HTTPException(404, f"no audit record for trace_id {trace_id}")
    return rec


@router.get("/sources")
def sources():
    return {"sources": repo.list_sources(), "rules": repo.all_rules()}


@router.get("/admin/students")
def student_ids():
    """IDs only (no names) - used by the UI's login selector."""
    return {"students": repo.list_student_ids()}


class LoadRequest(BaseModel):
    dir: str


@router.post("/admin/load-students")
def load_students(req: LoadRequest):
    from scripts.load_students import load_dir
    p = Path(req.dir)
    p = p if p.is_absolute() else get_settings().path(req.dir)
    if not p.is_dir():
        raise HTTPException(404, f"directory not found: {req.dir}")
    return load_dir(p)
