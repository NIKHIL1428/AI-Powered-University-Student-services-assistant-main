"""Create all tables (idempotent)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.connection import db_file, init_db  # noqa: E402

if __name__ == "__main__":
    init_db()
    print("initialised", db_file())
