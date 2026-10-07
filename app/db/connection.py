import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

SCHEMA = Path(__file__).with_name("schema.sql")


def db_file() -> Path:
    p = get_settings().path(get_settings().db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_file(), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as c:
        c.executescript(SCHEMA.read_text(encoding="utf-8"))
