-- Annex C tables (exact names/columns). Extra columns/tables are additive only.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
  student_id TEXT PRIMARY KEY CHECK (student_id GLOB 'S[0-9][0-9][0-9][0-9]'),
  full_name TEXT NOT NULL,
  programme TEXT NOT NULL,
  batch_year INTEGER NOT NULL,
  current_semester INTEGER NOT NULL CHECK (current_semester BETWEEN 1 AND 10),
  cgpa REAL NOT NULL CHECK (cgpa BETWEEN 0 AND 10),
  active_backlogs INTEGER NOT NULL CHECK (active_backlogs >= 0)
);

CREATE TABLE IF NOT EXISTS courses (
  course_code TEXT PRIMARY KEY,
  course_name TEXT NOT NULL,
  programme TEXT NOT NULL,
  semester INTEGER,
  credits INTEGER
);

CREATE TABLE IF NOT EXISTS attendance (
  student_id TEXT NOT NULL REFERENCES students(student_id),
  course_code TEXT NOT NULL REFERENCES courses(course_code),
  classes_held INTEGER NOT NULL CHECK (classes_held > 0),
  classes_attended INTEGER NOT NULL CHECK (classes_attended >= 0 AND classes_attended <= classes_held),
  PRIMARY KEY (student_id, course_code)
);

CREATE TABLE IF NOT EXISTS results (
  student_id TEXT NOT NULL REFERENCES students(student_id),
  course_code TEXT NOT NULL REFERENCES courses(course_code),
  exam_session TEXT NOT NULL,
  exam_type TEXT NOT NULL CHECK (exam_type IN ('REGULAR','SUPPLEMENTARY')),
  internal_marks INTEGER,
  external_marks INTEGER,
  total_marks INTEGER,
  max_marks INTEGER,
  result TEXT NOT NULL CHECK (result IN ('PASS','FAIL','ABSENT','DETAINED')),
  PRIMARY KEY (student_id, course_code, exam_session, exam_type)
);

CREATE TABLE IF NOT EXISTS rule_registry (
  rule_id TEXT PRIMARY KEY,
  description TEXT,
  parameter TEXT NOT NULL,
  operator TEXT NOT NULL,
  value TEXT NOT NULL,
  scope_programmes TEXT DEFAULT 'ALL',
  scope_batches TEXT DEFAULT 'ALL',
  effective_from TEXT,
  effective_to TEXT,
  source_doc_id TEXT NOT NULL,
  source_section TEXT NOT NULL,
  extraction_method TEXT DEFAULT 'seed',   -- seed | metadata | regex | llm
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS source_register (
  doc_id TEXT PRIMARY KEY, title TEXT, issuer TEXT, authority_level INTEGER,
  doc_type TEXT, version TEXT, effective_from TEXT, effective_to TEXT,
  supersedes TEXT, scope_programmes TEXT, scope_batches TEXT,
  provenance TEXT, retrieved_on TEXT, synthetic TEXT,
  file_name TEXT, file_hash TEXT, pages INTEGER, ocr_pages INTEGER,
  chunks_indexed INTEGER, ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  trace_id TEXT PRIMARY KEY, timestamp TEXT, student_id TEXT, record_json TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, student_id TEXT, memory_json TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS student_auth (
  student_id TEXT PRIMARY KEY REFERENCES students(student_id),
  password_hash TEXT NOT NULL,
  password_set INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT
);

CREATE TABLE IF NOT EXISTS auth_sessions (
  token TEXT PRIMARY KEY,
  student_id TEXT NOT NULL REFERENCES students(student_id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  token TEXT PRIMARY KEY,
  student_id TEXT NOT NULL REFERENCES students(student_id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used INTEGER NOT NULL DEFAULT 0
);

