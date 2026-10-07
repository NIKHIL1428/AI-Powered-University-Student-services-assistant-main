"""Test session: isolated temp stores, fixture corpus + fixture students, MOCK_LLM=true."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures" / "corpus"
TMP = Path(tempfile.mkdtemp(prefix="uniassist_test_"))
shutil.copy(FIX / "register.csv", TMP / "register.csv")      # /ingest appends to it
if not (FIX / "docs" / "FIX-REG-2024.pdf").exists():
    sys.path.insert(0, str(ROOT))
    from tests.fixtures.corpus.build_fixtures import build
    build()
shutil.copytree(FIX / "docs", TMP / "docs")                   # /ingest writes uploads into DOCS_DIR

os.environ.update({
    "MOCK_LLM": "true", "DB_PATH": str(TMP / "university.db"), "CHROMA_PATH": str(TMP / "chroma"),
    "DOCS_DIR": str(TMP / "docs"), "REGISTER_CSV": str(TMP / "register.csv"),
    "RULES_SEED_CSV": str(FIX / "rules_seed.csv"), "OCR_CACHE_DIR": str(TMP / "ocr"),
    "CLASSIFY_MODE": "keyword",
})
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def corpus():
    from scripts.ingest_all import ingest_all
    from scripts.load_students import load_dir
    ingest_all()
    load_dir(FIX / "students")
    yield TMP


@pytest.fixture
def ask():
    from datetime import date
    from app.graph.build import run

    def _ask(q, sid=None, as_of="2026-10-06", session=None):
        return run(q, sid, date.fromisoformat(as_of), session)
    return _ask
