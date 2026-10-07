"""All SQL lives here. Every query is parameterised."""
import json
import secrets
from datetime import datetime, timezone, timedelta

from app.db.connection import get_conn


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ---------- students / courses ----------
def get_student(student_id: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
        return dict(r) if r else None


def student_exists(student_id: str) -> bool:
    return get_student(student_id) is not None


def all_student_names() -> list[tuple[str, str]]:
    with get_conn() as c:
        return [(r["student_id"], r["full_name"]) for r in c.execute("SELECT student_id, full_name FROM students")]


def list_student_ids() -> list[str]:
    with get_conn() as c:
        return [r[0] for r in c.execute("SELECT student_id FROM students ORDER BY student_id")]


def courses_for_programme(programme: str) -> list[dict]:
    with get_conn() as c:
        return _rows(c.execute("SELECT * FROM courses WHERE programme = ? ORDER BY course_code", (programme,)))


def courses_for_student(student_id: str) -> list[dict]:
    """Courses the student has records for, plus their programme's catalogue."""
    with get_conn() as c:
        return _rows(c.execute(
            """SELECT DISTINCT c.* FROM courses c
               WHERE c.programme = (SELECT programme FROM students WHERE student_id = ?)
                  OR c.course_code IN (SELECT course_code FROM attendance WHERE student_id = ?)
                  OR c.course_code IN (SELECT course_code FROM results WHERE student_id = ?)
               ORDER BY c.course_code""", (student_id, student_id, student_id)))


def get_attendance(student_id: str, course_code: str | None = None) -> list[dict]:
    q = """SELECT a.course_code, c.course_name, a.classes_held, a.classes_attended
           FROM attendance a LEFT JOIN courses c USING(course_code) WHERE a.student_id = ?"""
    args: list = [student_id]
    if course_code:
        q += " AND a.course_code = ?"
        args.append(course_code)
    with get_conn() as c:
        return _rows(c.execute(q + " ORDER BY a.course_code", args))


def get_results(student_id: str, course_code: str | None = None, exam_type: str | None = None) -> list[dict]:
    q = """SELECT r.course_code, c.course_name, r.exam_session, r.exam_type, r.internal_marks,
                  r.external_marks, r.total_marks, r.max_marks, r.result
           FROM results r LEFT JOIN courses c USING(course_code) WHERE r.student_id = ?"""
    args: list = [student_id]
    if course_code:
        q += " AND r.course_code = ?"
        args.append(course_code)
    if exam_type:
        q += " AND r.exam_type = ?"
        args.append(exam_type)
    with get_conn() as c:
        return _rows(c.execute(q + " ORDER BY r.course_code, r.exam_session", args))


# ---------- rules / sources ----------
def rules_for_parameter(parameter: str) -> list[dict]:
    with get_conn() as c:
        return _rows(c.execute(
            """SELECT r.*, s.authority_level, s.supersedes AS doc_supersedes, s.title AS doc_title,
                      s.version AS doc_version
               FROM rule_registry r LEFT JOIN source_register s ON s.doc_id = r.source_doc_id
               WHERE r.parameter = ?""", (parameter,)))


def all_rules() -> list[dict]:
    with get_conn() as c:
        return _rows(c.execute("SELECT * FROM rule_registry ORDER BY parameter, effective_from"))


def upsert_rule(rule: dict) -> None:
    rule = {**rule, "created_at": rule.get("created_at") or now_iso()}
    cols = ["rule_id", "description", "parameter", "operator", "value", "scope_programmes",
            "scope_batches", "effective_from", "effective_to", "source_doc_id", "source_section",
            "extraction_method", "created_at"]
    with get_conn() as c:
        c.execute(f"INSERT OR REPLACE INTO rule_registry ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                  [rule.get(k) for k in cols])


def get_source(doc_id: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT * FROM source_register WHERE doc_id = ?", (doc_id,)).fetchone()
        return dict(r) if r else None


def list_sources() -> list[dict]:
    with get_conn() as c:
        return _rows(c.execute("SELECT * FROM source_register ORDER BY authority_level, doc_id"))


def upsert_source(row: dict) -> None:
    cols = ["doc_id", "title", "issuer", "authority_level", "doc_type", "version", "effective_from",
            "effective_to", "supersedes", "scope_programmes", "scope_batches", "provenance",
            "retrieved_on", "synthetic", "file_name", "file_hash", "pages", "ocr_pages",
            "chunks_indexed", "ingested_at"]
    with get_conn() as c:
        c.execute(f"INSERT OR REPLACE INTO source_register ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                  [row.get(k) for k in cols])


def counts() -> dict:
    with get_conn() as c:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("students", "courses", "attendance", "results", "rule_registry", "source_register")}


# ---------- audit / sessions ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_audit(record: dict) -> None:
    with get_conn() as c:
        c.execute("INSERT OR REPLACE INTO audit_log (trace_id, timestamp, student_id, record_json) VALUES (?,?,?,?)",
                  (record["trace_id"], record["timestamp"], record.get("student_id"), json.dumps(record, default=str)))


def get_audit(trace_id: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT record_json FROM audit_log WHERE trace_id = ?", (trace_id,)).fetchone()
        return json.loads(r[0]) if r else None


def get_session(session_id: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(r) if r else None


def save_session(session_id: str, student_id: str | None, memory: dict) -> None:
    with get_conn() as c:
        c.execute("INSERT OR REPLACE INTO sessions (session_id, student_id, memory_json, updated_at) VALUES (?,?,?,?)",
                  (session_id, student_id, json.dumps(memory), now_iso()))


# ---------- student authentication & session security ----------
def get_student_auth(student_id: str) -> dict | None:
    with get_conn() as c:
        r = c.execute("SELECT * FROM student_auth WHERE student_id = ?", (student_id,)).fetchone()
        return dict(r) if r else None


def upsert_student_auth(student_id: str, password_hash: str) -> None:
    t = now_iso()
    with get_conn() as c:
        existing = c.execute("SELECT created_at FROM student_auth WHERE student_id = ?", (student_id,)).fetchone()
        created_at = existing["created_at"] if existing else t
        c.execute(
            """INSERT OR REPLACE INTO student_auth 
               (student_id, password_hash, password_set, created_at, updated_at, failed_attempts, locked_until)
               VALUES (?, ?, 1, ?, ?, 0, NULL)""",
            (student_id, password_hash, created_at, t),
        )


def record_failed_login(student_id: str, max_attempts: int = 5, lock_minutes: int = 15) -> tuple[int, str | None]:
    with get_conn() as c:
        r = c.execute("SELECT failed_attempts FROM student_auth WHERE student_id = ?", (student_id,)).fetchone()
        if not r:
            return 0, None
        attempts = (r["failed_attempts"] or 0) + 1
        locked_until = None
        if attempts >= max_attempts:
            locked_until = (datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c.execute(
            "UPDATE student_auth SET failed_attempts = ?, locked_until = ?, updated_at = ? WHERE student_id = ?",
            (attempts, locked_until, now_iso(), student_id),
        )
        return attempts, locked_until


def reset_failed_attempts(student_id: str) -> None:
    with get_conn() as c:
        c.execute(
            "UPDATE student_auth SET failed_attempts = 0, locked_until = NULL, updated_at = ? WHERE student_id = ?",
            (now_iso(), student_id),
        )


def create_auth_session(student_id: str, ttl_hours: int = 24) -> str:
    token = secrets.token_urlsafe(32)
    created_at = now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_conn() as c:
        c.execute(
            "INSERT INTO auth_sessions (token, student_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, student_id, created_at, expires_at),
        )
    return token


def get_auth_session(token: str) -> dict | None:
    if not token or not token.strip():
        return None
    with get_conn() as c:
        r = c.execute("SELECT * FROM auth_sessions WHERE token = ?", (token.strip(),)).fetchone()
        if not r:
            return None
        sess = dict(r)
        if sess["expires_at"] < now_iso():
            c.execute("DELETE FROM auth_sessions WHERE token = ?", (token.strip(),))
            return None
        return sess


def delete_auth_session(token: str) -> None:
    if not token:
        return
    with get_conn() as c:
        c.execute("DELETE FROM auth_sessions WHERE token = ?", (token.strip(),))


def create_password_reset_token(student_id: str, ttl_minutes: int = 15) -> str:
    token = secrets.token_urlsafe(32)
    created_at = now_iso()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_conn() as c:
        c.execute(
            "INSERT INTO password_reset_tokens (token, student_id, created_at, expires_at, used) VALUES (?, ?, ?, ?, 0)",
            (token, student_id, created_at, expires_at),
        )
    return token


def get_valid_password_reset_token(token: str) -> dict | None:
    if not token or not token.strip():
        return None
    with get_conn() as c:
        r = c.execute("SELECT * FROM password_reset_tokens WHERE token = ? AND used = 0", (token.strip(),)).fetchone()
        if not r:
            return None
        rec = dict(r)
        if rec["expires_at"] < now_iso():
            return None
        return rec


def mark_password_reset_used(token: str) -> None:
    with get_conn() as c:
        c.execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token.strip(),))


def verify_student_course_match(student_id: str, course_query: str) -> bool:
    s = get_student(student_id)
    if not s:
        return False
    q = (course_query or "").strip().lower()
    if not q:
        return False
    
    # 1. Match programme
    prog = (s.get("programme") or "").lower()
    if q in prog or prog in q:
        return True
        
    # 2. Match student courses
    courses = courses_for_student(student_id)
    for c in courses:
        code = (c.get("course_code") or "").lower()
        name = (c.get("course_name") or "").lower()
        if q == code or q == name:
            return True
        if q in code or q in name or code in q or name in q:
            return True
            
    return False

