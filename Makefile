PY ?= .venv/Scripts/python
FIX = DB_PATH=data/dev/university.db CHROMA_PATH=data/dev/chroma DOCS_DIR=tests/fixtures/corpus/docs \
      REGISTER_CSV=tests/fixtures/corpus/register.csv RULES_SEED_CSV=tests/fixtures/corpus/rules_seed.csv

init:            ## create tables
	$(PY) scripts/init_db.py
ingest:          ## register + seed rules + ingest new/changed docs in data/documents
	$(PY) scripts/ingest_all.py
corpus:          ## rebuild data/documents + source_register.csv from the raw NSUT download (redacts student lists)
	$(PY) scripts/prepare_corpus.py --raw ../data/data
students:        ## convert + repair + validate + load synthetic students (Annex C CSVs)
	$(PY) scripts/convert_to_annex_c.py --src data/csv_original && $(PY) scripts/repair_synthetic_data.py && 	$(PY) scripts/validate_synthetic_data.py --dir data/synthetic --out docs/validation_output.txt && 	$(PY) scripts/load_students.py --dir data/synthetic
api:
	$(PY) -m uvicorn app.main:app --reload --port 8000
ui:
	$(PY) -m streamlit run ui/streamlit_app.py
test:
	$(PY) -m pytest
fixture-eval:    ## the original fixture-corpus eval set
	$(FIX) EVAL_QUESTIONS=tests/fixtures/eval/questions_fixture.jsonl $(PY) eval/run_eval.py full --config mock_bge_k8
dev-fixtures:    ## fixture corpus + fixture students into data/dev (test-only data)
	$(FIX) $(PY) scripts/ingest_all.py --extra bge:fixed,minilm:clause && $(FIX) $(PY) scripts/load_students.py --dir tests/fixtures/corpus/students
dev-api:
	$(FIX) $(PY) -m uvicorn app.main:app --port 8000
eval:            ## retrieval comparison + full pipeline (mock) + report
	$(PY) scripts/ingest_all.py --extra bge:fixed,minilm:clause && $(PY) eval/run_eval.py retrieval && 	$(PY) eval/run_eval.py full --config mock_bge_k8 && $(PY) eval/run_eval.py report
up:
	docker compose up --build
