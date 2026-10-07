# data/documents

Put the official NSUT PDFs here (scanned is fine — OCR runs automatically) plus at most two synthetic docs.
Every file must have a row in `data/source_register.csv` (Annex B) with `file_name` = the file name here.

Rows starting with `#` in the register are ignored. Remove the `#` once the file and metadata are real.
Synthetic conflict/injection docs: copy `tests/fixtures/corpus/src/SYN-CIRC-01.txt` / `SYN-FAQ-01.txt`, change the
clause references to the real NSUT ordinance clause, and build PDFs with `tests/fixtures/corpus/build_fixtures.py`
(or simply keep them as `.txt` — the pipeline accepts .txt with `\f` page breaks).
