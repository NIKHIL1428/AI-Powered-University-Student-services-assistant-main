# UniAssist — NSUT Student Services Assistant

HCLTech Future Ready AI Engineer Hackathon · AI-Powered University Student Services Assistant · NSUT · 6 Oct 2026

> *A multi-path AI university assistant: LangGraph orchestrates a query router between RAG and structured-data
> tools, BGE + ChromaDB provide semantic retrieval, SQLite provides deterministic data access, and a locally hosted
> Qwen3-8B writes grounded answers behind a source-authority validator and safety guardrails.*

---

## Architecture

```
                    ┌───────────────────────┐
                    │     USER / STUDENT    │
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │     STREAMLIT UI      │  chat · citations · tools · audit · ingest · sources
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │  FASTAPI (Pydantic v2)│  /ask /ingest /health /audit/{id} /sources /admin/load-students
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │  LANGGRAPH StateGraph │  auth_guard → contextualize (session memory)
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │     QUERY ROUTER      │  intent (Qwen3 JSON + keyword fallback) → allowlisted plan
                    └───────────┬───────────┘
              ┌─────────────────┼─────────────────┐
       ┌──────▼─────┐    ┌──────▼─────┐    ┌──────▼─────┐
       │  RAG PATH  │    │ STRUCTURED │    │ HYBRID PATH│
       │ BGE query  │    │ SQLite +   │    │ tools +    │
       │ → ChromaDB │    │ rule tools │    │ retrieval  │
       └──────┬─────┘    └──────┬─────┘    └──────┬─────┘
              └─────────────────┼─────────────────┘
                    ┌───────────▼───────────┐
                    │ EVIDENCE / SOURCE     │  Annex A precedence on chunks AND registry rules:
                    │ AUTHORITY VALIDATOR   │  as_of_date · scope · supersession · authority · recency
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │  QWEN3-8B (Ollama)    │  explanations / text answers from verified evidence only
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │ SAFETY & GROUNDING    │  registered citations · number grounding · not_found gate
                    │ GUARDRAILS            │  (+ injection masking, PII gate at ingest, header-only identity)
                    └───────────┬───────────┘
                    ┌───────────▼───────────┐
                    │ ANSWER + SOURCES      │  Section 6.1 JSON + audit record (trace_id)
                    └───────────────────────┘

              UNIVERSITY KNOWLEDGE LAYER
   Unstructured (44 docs: regulations, circulars,        Structured (SQLite, Annex C):
   notices, fee structures, scholarships, library,       students · courses · attendance · results
   placement policy, FAQ)  ──► BGE ──► ChromaDB           rule_registry · source_register · audit_log · sessions
```

| # | Layer | Components | Code |
|---|---|---|---|
| 1 | Presentation | Streamlit | `ui/streamlit_app.py` |
| 2 | Application / orchestration | FastAPI + LangGraph | `app/api/`, `app/graph/build.py` |
| 3 | Intelligence | Query Router + Qwen3-8B | `app/router/query_router.py`, `app/graph/nodes.py`, `app/llm/qwen.py` |
| 4 | Knowledge / retrieval | BGE + ChromaDB + SQLite | `app/embeddings/`, `app/vectorstore/`, `app/retrieval/`, `app/db/` |
| 5 | Trust / governance | Source validation + guardrails + audit | `app/precedence/`, `app/guardrails/`, `app/audit/` |

### Router paths

| Path | When | What runs | Example |
|---|---|---|---|
| **RAG** | procedures, notices, anything without a rule/record | BGE query → Chroma top-k → validator → Qwen3 | "Till when can I apply for the Kotak Kanya scholarship?" |
| **STRUCTURED** | the student's own records | `find_course` → `get_attendance` / `get_results` / `get_student_profile` | "What is my attendance in Data Structures?" |
| **HYBRID** | thresholds and eligibility | rule registry + tools **and** retrieval of the clause behind the rule | "Am I eligible for the end-sem exam in DS?", "What is the minimum attendance?" |

Refusals (another student's data, personal question without `X-Student-Id`) and clarifications short-circuit to
`generate` before any retrieval or tool runs. The audit record stores the chosen `route`.

**LLM only in two places** (router classification, generation). Everything that must be correct — identity,
precedence, eligibility, arithmetic, citation fields — is code. *Why not multi-agent?* every step after
classification is deterministic; extra agents would add LLM calls and failure modes without changing a decision.

### RAG pipeline

```
INDEXING   PDF / TXT / HTML / image ─► unified loader (text layer, else OCR: Tesseract | RapidOCR, cached)
           ─► PII gate (student lists removed) ─► cleaning (letterhead, hyphenation, OCR digits)
           ─► clause-aware chunks (one clause = one chunk, ≤350 words + 50 overlap, never across pages)
           ─► Annex B metadata ─► BGE-small-en-v1.5 (384-d) ─► ChromaDB  (+ rule extraction ─► rule_registry)
QUERY      question ─► router ─► BGE query embedding (instruction prefix) ─► Chroma top-8 (no date filter)
           ─► precedence validator ─► Qwen3-8B (<document> blocks, JSON answer) ─► grounding guardrails
```

Chroma runs as an embedded **PersistentClient** on disk (`chroma_db/`) — the guide requires a persisted store and
judges test offline. `CHROMA_MODE=cloud` switches to Chroma Cloud (`CHROMA_API_KEY/TENANT/DATABASE` in `.env`,
never committed); it is off by default and not used for the reported results.

## The NSUT corpus (`data/documents/`, `data/source_register.csv`)

44 documents: **42 official NSUT notices** downloaded from nsut.ac.in across 8 areas (attendance, examination,
academic, fees, scholarships, library, placement) + **2 synthetic** (marked `synthetic=Y`).

- **Personal data:** 15 official notices carry student lists (short attendance, detention, make-up exams, UFM,
  fee defaulters, merit lists — 1,800+ roll numbers). The guide forbids such content, so the originals are
  **not stored**; `scripts/prepare_corpus.py` keeps a redacted text rendering (list removed, page numbers kept).
  The same PII gate (`app/guardrails/pii.py`) runs on every `/ingest`, so judge uploads are protected too.
- **Scanned pages:** 58 of the 234 stored pages are scanned and are OCR'd. The Docker image uses Tesseract; hosts without it fall back to RapidOCR.
- **Real versioning in the corpus:** the 20-Nov-2025 short-attendance notice supersedes notices 1616/1617; the
  21-Nov-2025 final detention list is issued "in supersession of all previous notifications". These are encoded
  in `supersedes` and resolved by Annex A step 2.
- **Synthetic docs:** `SYN-CIRC-01` (level-2 circular, 80% attendance from 2027-01-01, supersedes clause 11.2) →
  an *upcoming change* today and a step-2 winner for `as_of_date ≥ 2027-01-01`. `SYN-FAQ-01` (level-4 FAQ:
  "65% is enough" + a prompt-injection line) → overridden by authority (step 3); the injection is masked.
- Duplicate downloads (2) were dropped. Where an OCR'd date was illegible the file-name date was used; this is
  stated per document in `provenance`.

### Rule registry — only what the documents say

| rule_id | parameter | value | source |
|---|---|---|---|
| ATT-MIN-01 | min_attendance_pct | ≥ 75 | NSUT-ACAD-RULES-ATT §11.2 |
| ATT-RELAX-DEAN-01 | attendance_relaxation_dean_pct | ≤ 10 | §11.3 |
| ATT-RELAX-COMM-01 | attendance_relaxation_committee_pct | ≤ 5 | §11.4 |
| ATT-RELAX-MAX-01 | max_attendance_relaxations | ≤ 2 | §11.5 |
| ATT-FLOOR-01 | min_attendance_after_relaxation_pct | ≥ 60 | §11.6 |
| ATT-SYN-CIRC-01 | min_attendance_pct | ≥ 80 (from 2027-01-01) | SYN-CIRC-01 §1 — *extracted at ingest* |
| ATT-SYN-FAQ-01 | min_attendance_pct | ≥ 65 | SYN-FAQ-01 Q1 — *extracted at ingest, always outranked* |

The team's draft `rule_registry.csv` (kept in `data/csv_original/`) was checked against the documents:
the 75% value is confirmed but its citation ("ATT_REG_2026 Section 4.2") was wrong → re-cited to clause 11.2;
`PASS_MIN_2026` (40 marks) and `BACKLOG_MAX_EXAM` (3) cite `EXAM_REG_2026` / `ACADEMIC_REG_2026`, which are **not
in the corpus**, so they were not seeded. The Placement Policy 2025-26 leaves CGPA/backlog criteria **to each
company**, so no university-wide placement threshold exists: placement-eligibility questions get an honest
"cannot compute" plus what the policy actually says. Adding the NSUT ordinance through `/ingest` (with optional
`rules` metadata) makes pass-mark / supplementary checks work immediately — no code change.

## Requirements → implementation

| Req | How | Proof |
|---|---|---|
| R1 retrieval | answers only from retrieved chunks, tool outputs or registry rows | eval Q22–Q28 |
| R2 citations | citation fields copied from chunk/source metadata (doc, title, section, page, version, effective date) | `test_api_contract.py` |
| R3 no fabrication | relevance threshold, proper-noun coverage, LLM `sufficient`, number grounding, exact not_found text | eval Q01–Q04 |
| R4 versions | Annex A engine (`app/precedence/engine.py`) at `as_of_date`; upcoming changes reported | `test_precedence.py`, eval Q05–Q09 |
| R5 tools | thresholds read from `rule_registry`; integer cross-multiplication at the boundary | `test_tools.py` (registry monkeypatch flips result) |
| R6 multi-step | e.g. attendance what-if: 11.2 → 11.3 → 11.4 → 11.6 with assumptions | eval Q19–Q21 |
| R7 auth | header-only identity; ID / name / "my friend's" detection; tools take the ID from auth context | `test_auth.py`, eval Q16–Q18 |
| R8 untrusted content | `<document>` data blocks, injection masking, suspicious chunks excluded from rule extraction | `test_injection.py`, eval Q29 |
| R9 typing | 6-value `answer_type`; AI explanation labelled in UI | contract test |
| R10 audit | `/audit/{trace_id}`: route, plan, sources+scores, precedence decision, tools (in/out/status/ms), rules, model, LLM calls, tokens, latency, node timings | `docs/sample_audits/` |
| R11 live ingestion | `/ingest` → OCR → PII gate → chunks → Chroma → rule extraction → usable at once | `test_ingest.py`, `test_pii.py` |
| R12 evaluation | 29 NSUT questions, 6 metrics, 4 retrieval configs, mock vs LLM | `eval/EVAL_REPORT.md` |

## Setup and run

### Docker (submission path)

```bash
cp .env.example .env
docker compose up --build        # API :8000, UI :8501
```

`./data` (documents, SQLite, OCR cache) and `./chroma_db` are volumes; on start the API registers sources, seeds
rules and ingests only new/changed documents (SHA-256), so restarts never re-embed or re-OCR. Both embedding models
are baked into the image.

**Ollama on the host:** `ollama pull qwen3:8b`; the container reaches `http://host.docker.internal:11434`
(`extra_hosts: host-gateway`). GPUs with < ~6 GB VRAM: set `OLLAMA_NUM_GPU=0` (partial offload crashes on 4 GB).
Slow CPU hosts: `CLASSIFY_MODE=keyword` saves one LLM call per question. **Cloud fallback (disclosed):**
`LLM_PROVIDER=cloud` + `CLOUD_*` for any OpenAI-compatible endpoint — off by default, not used for results.
`MOCK_LLM=true` runs everything with deterministic fallbacks.

### Local

```bash
py -3.10 -m venv .venv && .venv/Scripts/pip install -r requirements.txt
make corpus       # (only if rebuilding from the raw download) redact + register NSUT documents
make students     # convert team CSVs to Annex C, apply logged repairs, validate, load
make ingest       # register + seed rules + ingest data/documents into chroma_db/
make api          # uvicorn on :8000
make ui           # streamlit on :8501
make test         # 72 tests (fixture corpus, MOCK_LLM)
make eval         # retrieval comparison + full pipeline (mock) + report
```

### Judge test students

```bash
python scripts/load_students.py --dir test_students/
```

Loads any of `courses/students/attendance/results.csv` in FK order; validates every row (format, ranges,
attended ≤ held, total = internal + external); skips + reports bad rows; `INSERT OR REPLACE`; accepts S9xxx / JDG*.
Also `POST /admin/load-students {"dir": "..."}`.

## API examples

```bash
curl -s localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question":"What is the minimum attendance required to appear for end-semester exams?","as_of_date":"2026-10-06"}'
curl -s localhost:8000/ask -H "Content-Type: application/json" -H "X-Student-Id: S1003" \
  -d '{"question":"Am I eligible for the end-sem exam in Data Structures?"}'
curl -s localhost:8000/ask -H "Content-Type: application/json" -H "X-Student-Id: S1052" \
  -d '{"question":"If the Dean grants relaxation, can I appear in the end-sem exam for Data Structures?","session_id":"demo"}'
curl -s localhost:8000/ingest -F "file=@circular.pdf" -F 'metadata={"doc_id":"ACAD-2026-12","title":"Circular","issuer":"Office of the Dean (Academics)","authority_level":2,"doc_type":"circular","version":"1.0","effective_from":"2026-12-01","effective_to":"","supersedes":"NSUT-ACAD-RULES-ATT#11.2","scope_programmes":"B.Tech","scope_batches":"ALL","provenance":"judge","retrieved_on":"2026-10-06","synthetic":"N"}'
curl -s localhost:8000/health ; curl -s localhost:8000/sources ; curl -s localhost:8000/audit/<trace_id>
```

Response = Section 6.1 fields + additive `upcoming_changes`, `assumptions`, `session_id`. not_found answer is exactly
*"I could not find this information in the authorised university sources."*

## Assumptions

- Attendance eligibility per subject: `attended × 100 ≥ min_pct × held` (no floats at 75.0%).
- Relaxation what-if: Dean (11.3) lowers the bar by ≤10 points, committee (11.4) by ≤5 more, never below the 11.6
  floor (60%). The answer states what the rules *permit*; granting is discretionary (stated in `assumptions`).
- A DETAINED result row for a subject means not eligible for that subject's end-semester exam.
- Clause 11 is dated by its enclosing notification (15.09.2026); the regulation's original enactment date is not in
  the corpus, so `as_of_date` earlier than that finds no attendance rule (it is reported as an upcoming change).

## Limitations / known edge cases

- **Superseded notices are excluded even when asked about by name** (e.g. "what did the 20-Nov notice say?" is
  answered from the 21-Nov notice that supersedes it). This is Annex A applied literally.
- **OCR quality:** RapidOCR (local fallback) sometimes drops spaces/lines; the Docker image uses Tesseract.
  Low-confidence pages are flagged; judges should open the cited page.
- **Tables** (fee structures, NSP scholarship tables) are OCR'd as linear text; amounts are retrievable but row
  alignment can be lost.
- **No pass-mark / supplementary / placement thresholds** in the corpus (see rule registry) → those checks answer
  "cannot compute" with the relevant policy text instead of inventing numbers.
- **Rule extraction** is regex-based for a fixed parameter vocabulary; unusual phrasing → pass `rules` in metadata.
- **Latency on CPU-only hosts**: ~10 s classify + 20–40 s compose with qwen3:8b; calculated answers stay correct
  without the LLM.

## Repository map

```
app/  api/ graph/ router/ embeddings/ vectorstore/ retrieval/ ingestion/ precedence/ tools/ llm/ guardrails/ memory/ audit/ db/
ui/streamlit_app.py
data/ documents/<category>/  source_register.csv  rules_seed.csv  synthetic/ (Annex C)  csv_original/  structured/ (SQLite, gitignored)
chroma_db/ (gitignored)
scripts/ prepare_corpus · convert_to_annex_c · repair_synthetic_data · validate_synthetic_data · load_students · ingest_all · seed_rules
eval/   questions.jsonl  run_eval.py  metrics.py  configs/  results/  EVAL_REPORT.md
tests/  72 tests + fixtures/ (test-only corpus, students, fixture eval set)
docs/   DATA_CARD · AI_USAGE · CONTRIBUTION · DECLARATION · validation_output.txt · sample_audits/
```
