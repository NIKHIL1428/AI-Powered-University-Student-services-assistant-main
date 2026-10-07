"""Evaluation runner.

  # retrieval-only comparison (no LLM, fast): hit@k for each config
  python eval/run_eval.py retrieval --configs bge_k4 bge_k8 minilm_k8 bge_fixed_k8
  # full pipeline for one config (env from the YAML is applied before the app is imported)
  python eval/run_eval.py full --config bge_k8
  # write eval/EVAL_REPORT_RESULTS.md tables from everything in eval/results/
  python eval/run_eval.py report

Each config YAML may set: embed_model, top_k, chunk_strategy, classify_mode, mock_llm.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EVAL = ROOT / "eval"
RESULTS = EVAL / "results"


def load_cfg(name: str) -> dict:
    return yaml.safe_load((EVAL / "configs" / f"{name}.yaml").read_text()) or {}


def apply_env(cfg: dict) -> None:
    for k, v in cfg.items():
        if k != "description":
            os.environ[k.upper()] = str(v).lower() if isinstance(v, bool) else str(v)


QUESTIONS = os.environ.get("EVAL_QUESTIONS", str(EVAL / "questions.jsonl"))


def questions() -> list[dict]:
    return [json.loads(l) for l in Path(QUESTIONS).read_text(encoding="utf-8").splitlines() if l.strip()]


def run_retrieval(configs: list[str]) -> dict:
    from app.retrieval.retriever import retrieve
    from eval.metrics import hit_at_k
    for e in {load_cfg(n).get("embed_model", "bge") for n in configs}:
        retrieve("warm-up", embed=e)
    out = {}
    qs = [q for q in questions() if q.get("expected_sources")]
    for name in configs:
        cfg = load_cfg(name)
        hits, lat = [], []
        for q in qs:
            t = time.perf_counter()
            chunks = retrieve(q["question"], k=int(cfg.get("top_k", 8)), embed=cfg.get("embed_model", "bge"),
                              strategy=cfg.get("chunk_strategy", "clause"))
            lat.append((time.perf_counter() - t) * 1000)
            hits.append({"id": q["id"], "hit": hit_at_k(q["expected_sources"], chunks),
                         "top": [f"{c['meta']['doc_id']}#{c['meta'].get('section')}" for c in chunks[:3]]})
        out[name] = {"config": cfg, "n": len(qs), "hit_rate": round(100 * sum(h["hit"] for h in hits) / len(hits), 1),
                     "avg_retrieval_ms": round(sum(lat) / len(lat), 1), "per_question": hits}
        print(f"{name:16s} hit@{cfg.get('top_k', 8)} = {out[name]['hit_rate']}%  ({out[name]['avg_retrieval_ms']} ms)")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "retrieval_comparison.json").write_text(json.dumps(out, indent=2))
    return out


def run_full(name: str) -> dict:
    cfg = load_cfg(name)
    apply_env(cfg)
    from datetime import date
    from app.db import repo
    from app.graph.build import run
    from eval.metrics import score, summarize
    from app.retrieval.retriever import retrieve
    retrieve("warm-up")                       # load the embedding model outside the timed loop
    rows = []
    for q in questions():
        t = time.perf_counter()
        resp = run(q["question"], q.get("student_id"), date.fromisoformat(q["as_of_date"]))
        ms = int((time.perf_counter() - t) * 1000)
        audit = repo.get_audit(resp["trace_id"]) or {}
        s = score(q, resp) | {"latency_ms": ms, "llm_calls": audit.get("llm_calls", 0),
                               "tokens": audit.get("tokens", 0), "trace_id": resp["trace_id"],
                               "answer": resp["answer"][:240]}
        rows.append(s)
        flag = "OK " if s["answer_correct"] else "XX "
        print(f"{flag}{q['id']} {resp['answer_type']:20s} {ms:6d}ms  {resp['answer'][:90]}")
    summary = summarize(rows)
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r["answer_correct"])
    summary["by_category"] = {k: f"{sum(v)}/{len(v)}" for k, v in by_cat.items()}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"full_{name}.json").write_text(json.dumps({"config": cfg, "summary": summary, "rows": rows}, indent=2))
    print(json.dumps(summary, indent=2))
    return summary


def report() -> str:
    lines = ["## Retrieval comparison (hit@k over questions with an expected source)", "",
             "| config | embedding | chunking | top_k | hit rate | avg retrieval ms |", "|---|---|---|---|---|---|"]
    rc = RESULTS / "retrieval_comparison.json"
    if rc.exists():
        for name, r in json.loads(rc.read_text()).items():
            c = r["config"]
            lines.append(f"| {name} | {c.get('embed_model')} | {c.get('chunk_strategy', 'clause')} | {c.get('top_k')} | "
                         f"{r['hit_rate']}% | {r['avg_retrieval_ms']} |")
    lines += ["", "## Full pipeline", "",
              "| config | answer correctness | citation accuracy | abstention accuracy | tool-result correctness | "
              "p50 ms | p95 ms | LLM calls/q | tokens/q |", "|---|---|---|---|---|---|---|---|---|"]
    for f in sorted(RESULTS.glob("full_*.json")):
        d = json.loads(f.read_text())
        s = d["summary"]
        lines.append(f"| {f.stem[5:]} | {s['answer_correctness']}% | {s['citation_accuracy']}% | "
                     f"{s['abstention_accuracy']}% | {s['tool_result_correctness']}% | {s['latency_p50_ms']} | "
                     f"{s['latency_p95_ms']} | {s['llm_calls_avg']} | {s['tokens_avg']} |")
    lines += ["", "### Per-category answer correctness", ""]
    for f in sorted(RESULTS.glob("full_*.json")):
        d = json.loads(f.read_text())
        lines.append(f"- **{f.stem[5:]}**: " + ", ".join(f"{k} {v}" for k, v in d["summary"]["by_category"].items()))
        fails = [r for r in d["rows"] if not r["answer_correct"]]
        for r in fails:
            lines.append(f"  - FAIL {r['id']} ({r['category']}): got `{r['answer_type']}` - {r['answer'][:150]}")
    text = "\n".join(lines) + "\n"
    (EVAL / "EVAL_RESULTS.md").write_text(text, encoding="utf-8")
    print(text)
    return text


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["retrieval", "full", "report"])
    ap.add_argument("--configs", nargs="*", default=["bge_k4", "bge_k8", "minilm_k8", "bge_fixed_k8"])
    ap.add_argument("--config", default="bge_k8")
    a = ap.parse_args()
    if a.mode == "retrieval":
        run_retrieval(a.configs)
    elif a.mode == "full":
        run_full(a.config)
    else:
        report()
