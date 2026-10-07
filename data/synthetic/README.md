# data/synthetic

Place the LLM-generated Annex C CSVs here: `students.csv`, `courses.csv`, `attendance.csv`, `results.csv`
(plus `generation_summary.json` and `raw/`). Load with:

    python scripts/load_students.py --dir data/synthetic

Edge-case thresholds in this data must match the values in `data/rules_seed.csv` (taken from the NSUT documents).
