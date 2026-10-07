import json
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from app.config import get_settings
from app.ingestion.document_loader import SUPPORTED
from app.ingestion.pipeline import ingest_document
from app.schemas.source import SourceMetadata

router = APIRouter()
ALLOWED = SUPPORTED


@router.post("/ingest")
async def ingest(file: UploadFile = File(...), metadata: str = Form(...)):
    try:
        meta = SourceMetadata.model_validate(json.loads(metadata))
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"metadata is not valid JSON: {e}")
    except ValidationError as e:
        raise HTTPException(422, json.loads(e.json()))
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(422, f"unsupported file type '{suffix}'; allowed: {sorted(ALLOWED)}")
    data = await file.read()
    if not data:
        raise HTTPException(422, "empty file")
    s = get_settings()
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(file.filename).name)
    dest = s.path(s.docs_dir) / f"{meta.doc_id}__{safe}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        # OCR/embedding is CPU-bound: keep the event loop free for /health and /ask
        return await run_in_threadpool(ingest_document, dest, meta, data)
    except ValueError as e:
        raise HTTPException(422, str(e))
