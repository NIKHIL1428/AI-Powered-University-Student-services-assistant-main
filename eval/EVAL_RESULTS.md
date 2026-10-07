## Retrieval comparison (hit@k over questions with an expected source)

| config | embedding | chunking | top_k | hit rate | avg retrieval ms |
|---|---|---|---|---|---|
| bge_k4 | bge | clause | 4 | 82.4% | 20.9 |
| bge_k8 | bge | clause | 8 | 82.4% | 22.3 |
| minilm_k8 | minilm | clause | 8 | 76.5% | 13.0 |
| bge_fixed_k8 | bge | fixed | 8 | 76.5% | 24.6 |

## Full pipeline

| config | answer correctness | citation accuracy | abstention accuracy | tool-result correctness | p50 ms | p95 ms | LLM calls/q | tokens/q |
|---|---|---|---|---|---|---|---|---|
| llm_bge_k8 | 93.1% | 94.1% | 100.0% | 100.0% | 32264.0 | 94862.6 | 1.52 | 1039.3 |
| mock_bge_k8 | 100.0% | 100.0% | 100.0% | 100.0% | 38.0 | 49.2 | 0 | 0 |

### Per-category answer correctness

- **llm_bge_k8**: not_answerable 4/4, versions_conflicts 4/5, personal_tools 6/6, cross_student 3/3, multi_step 3/3, policy_procedure 6/7, safety_injection 1/1
  - FAIL Q08 (versions_conflicts): got `retrieved_fact` - The final list of students not allowed to appear in the Nov-Dec 2025 end-semester exams due to short attendance is provided in the notification NSUT-D
  - FAIL Q26 (policy_procedure): got `refused` - This is a personal question. Please identify yourself (X-Student-Id header / select your student ID) - I cannot look up records without it.
- **mock_bge_k8**: not_answerable 4/4, versions_conflicts 5/5, personal_tools 6/6, cross_student 3/3, multi_step 3/3, policy_procedure 7/7, safety_injection 1/1
