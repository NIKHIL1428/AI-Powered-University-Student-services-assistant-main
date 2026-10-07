# Evaluation report (NSUT corpus)

Corpus: 44 documents (42 official NSUT notices + 2 synthetic) in `data/documents/`, 52 synthetic students in
`data/synthetic/`. The earlier fixture-corpus evaluation is preserved in `tests/fixtures/eval/` and
`eval/results/fixture_corpus/`.

## Method

- **Set:** `eval/questions.jsonl`, 29 questions, each with an expected `answer_type` and, where applicable, expected tool values, keywords and expected source (`doc_id` or `doc_id#clause`).

  | Category | Guide minimum | Ours |
  |---|---|---|
  | Not answerable from sources | 3 | 4 (Q01–Q04) |
  | Versions / conflicting documents | 3 | 5 (Q05–Q09) |
  | Personal questions via tools | 4 | 6 (Q10–Q15) |
  | Another student's data | 2 | 3 (Q16–Q18) |
  | Multi-step / what-if | 2 | 3 (Q19–Q21) |
  | Policy / procedure from notices | – | 7 (Q22–Q28) |
  | Prompt injection in a document | – | 1 (Q29) |

- **Answer correctness:**
  - exact match on `answer_type`;
  - exact match on tool values (`result`, `attendance_pct`, `classes_short`, relaxation outcome, CGPA, backlogs);
  - rule_id, upcoming document and overridden documents where specified;
  - a keyword rubric fixed before running (for example Q24 must contain "30 September" and Q07 must not present "65%").

  No LLM-as-judge.
- **Citation accuracy:** at least one citation matches an expected source. For notices without clause numbers, the document is the unit. The team opened the cited pages for Q22–Q28 by hand.
- **Abstention:** unanswerable → `not_found`; answerable → not `not_found`.
- **Tool-result correctness:** tool outputs in `tools_invoked` match `expected_values`.
- **Retrieval hit rate:** an expected source is in the top-k for the *raw question* (no pipeline query expansion, no LLM).
- **Latency and cost:** wall clock per question; LLM calls and tokens from the audit record.
- **Hardware:** laptop CPU only. qwen3:8b with `OLLAMA_NUM_GPU=0`, because the 4 GB GPU cannot hold the model.

## Results

### Retrieval comparison (hit@k over questions with an expected source)

| config | embedding | chunking | top_k | hit rate | avg retrieval ms |
|---|---|---|---|---|---|
| bge_k4 | bge | clause | 4 | 82.4% | 20.9 |
| bge_k8 | bge | clause | 8 | 82.4% | 22.3 |
| minilm_k8 | minilm | clause | 8 | 76.5% | 13.0 |
| bge_fixed_k8 | bge | fixed | 8 | 76.5% | 24.6 |

### Full pipeline

| config | answer correctness | citation accuracy | abstention accuracy | tool-result correctness | p50 ms | p95 ms | LLM calls/q | tokens/q |
|---|---|---|---|---|---|---|---|---|
| llm_bge_k8 | 93.1% | 94.1% | 100.0% | 100.0% | 32264.0 | 94862.6 | 1.52 | 1039.3 |
| mock_bge_k8 | 100.0% | 100.0% | 100.0% | 100.0% | 38.0 | 49.2 | 0 | 0 |

#### Per-category answer correctness

- **llm_bge_k8**: not_answerable 4/4, versions_conflicts 4/5, personal_tools 6/6, cross_student 3/3, multi_step 3/3, policy_procedure 6/7, safety_injection 1/1
  - FAIL Q08 (versions_conflicts): got `retrieved_fact` - The final list of students not allowed to appear in the Nov-Dec 2025 end-semester exams due to short attendance is provided in the notification NSUT-D
  - FAIL Q26 (policy_procedure): got `refused` - This is a personal question. Please identify yourself (X-Student-Id header / select your student ID) - I cannot look up records without it.
- **mock_bge_k8**: not_answerable 4/4, versions_conflicts 5/5, personal_tools 6/6, cross_student 3/3, multi_step 3/3, policy_procedure 7/7, safety_injection 1/1


### Decisions taken from these numbers

1. **Embedding: bge-small-en-v1.5.** 82.4% hit@8 vs 76.5% for MiniLM on the real corpus. MiniLM is faster (13 vs 22 ms), but both are negligible next to the LLM.
2. **Chunking: clause-aware.** It also beats fixed 500-character chunks (82.4% vs 76.5%), and only clause chunks carry the section number that citations need (R2) and that supersession (`DOC#11.2`) matches against.
3. **top_k 8.** On this set top-4 has the same hit rate. 8 is kept because the procedure answers (Q24, Q27) use several chunks of the same notice, and the extra chunks only cost prompt tokens on the RAG path.
4. **Retrieval misses explained.**
   - Q11 and Q12 ("Am I eligible…") are raw-question misses only. In the pipeline the hybrid path appends the rule description to the query, and the citation comes from the rule's clause (citation accuracy 100%).
   - Q09 ranks the synthetic circular above clause 11.2, but its answer comes from the rule registry.
5. **Mock vs LLM.** Both paths are fully correct on tools, refusals and abstention. The LLM adds synthesised answers for notices, e.g. Q24 "The last date to apply … is 30 September, 2026" instead of a quoted OCR paragraph. That improves readability, not correctness. Correctness lives in the tools, the precedence engine and the validators.

### Failure analysis and honesty notes

- **Q08 (LLM run):** the answer names the right notice (`NSUT-DETENTION-2025-11`, cited correctly) but does not contain the rubric keyword "supersession". It is counted as a fail; we did not change the rubric after the run.
- **Q26 (LLM run):** "If I am placed in a Dream category company, can I apply…?" asked with no login was classified as personal by the LLM and refused. That is wrong: it is a hypothetical policy question. **Fixed after the run** (refusal for missing identity now requires an own-records reference such as "my" or "am I"). The fixed behaviour was re-checked on Q26 alone ("No … you cannot apply for any further companies", citing the Placement Policy) but **the full 29-question LLM run was not repeated** (≈25 min on CPU). The table shows the pre-fix numbers.
- **Tuned after seeing results (mock path), disclosed:** Q22 (router mapped "relax the minimum" to the floor rule) and Q28 (a synthetic level-4 FAQ beat the official level-2 notification) failed in the first mock run and were fixed. Q09 was replaced: the original asked about a superseded notice, which precedence correctly hides (see README limitations).
- **Small, team-written set.** 100% on the mock path shows the pipeline works end to end on these questions; it does not prove robustness to unseen phrasing. Next steps: questions written by a member who did not build the system, and a rehearsal with judge-style uploads.
- **Latency** is dominated by CPU-only qwen3:8b: p50 32 s, p95 95 s. Calculated answers, refusals and rule facts are correct with no LLM call (`MOCK_LLM=true`, p50 38 ms).

## Reproduce

```bash
make ingest                                   # + extra collections: scripts/ingest_all.py --extra bge:fixed,minilm:clause
python eval/run_eval.py retrieval
python eval/run_eval.py full --config mock_bge_k8
python eval/run_eval.py full --config llm_bge_k8
python eval/run_eval.py report
```
