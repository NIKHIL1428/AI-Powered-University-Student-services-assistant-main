# AI-usage disclosure

| Part | AI-generated? | How it was verified |
|---|---|---|
| Application code (`app/`, `scripts/`, `ui/`) | Drafted with Claude Code (Anthropic, Claude Opus) from our implementation plan, then reviewed and edited by the team | 54 pytest tests (unit, integration, contract, safety); manual runs against the API and UI; the evaluation set |
| Precedence engine (`app/precedence/`) | AI-drafted from Annex A | Annex A.3 worked example and 11 more cases in `tests/test_precedence.py` |
| Eligibility tools (`app/tools/`) | AI-drafted | boundary tests (exactly at threshold, one class below, CGPA at cut-off), registry-monkeypatch test proving no constants |
| Test fixture corpus (`tests/fixtures/corpus/`) | Written with AI assistance; **clearly labelled TEST FIXTURE / SYNTHETIC, not official documents** | used only by tests/eval scaffolding |
| Synthetic student data (`data/synthetic/`) | Generated with an LLM by the team: see `docs/DATA_CARD.md` and `prompts/` | `validate_synthetic_data.py` output in `docs/validation_output.txt` |
| Evaluation questions | Written by the team (AI-assisted drafting); expected answers checked by hand against the documents | `eval/EVAL_REPORT.md` |
| README / docs | AI-drafted, edited by the team | reviewed for accuracy against the code |

Runtime LLM: Ollama `qwen3:8b` on the host, used only to classify questions and explain verified evidence. No cloud LLM was used for the reported results.
No code was copied from other teams or from tutorial projects. Open-source libraries are listed in `requirements.txt`.
