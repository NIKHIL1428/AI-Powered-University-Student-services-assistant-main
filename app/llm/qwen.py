"""LLM client: Ollama (default) | OpenAI-compatible cloud fallback (config switch) | mock.

The LLM is only used to (1) classify the question and (2) write explanations over verified evidence.
It never computes eligibility, never chooses identity and never writes citation fields.
"""
import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

log = logging.getLogger("uniassist.llm")


@dataclass
class LLMUsage:
    calls: int = 0
    tokens: int = 0
    ms: int = 0
    errors: list[str] = field(default_factory=list)


class LLMUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return not get_settings().mock_llm


def chat(system: str, user: str, schema: dict | None, usage: LLMUsage) -> str:
    s = get_settings()
    if s.mock_llm:
        raise LLMUnavailable("MOCK_LLM=true")
    t0 = time.perf_counter()
    try:
        if s.llm_provider == "cloud":
            text, tokens = _cloud(system, user, s)
        else:
            text, tokens = _ollama(system, user, schema, s)
    except httpx.HTTPError as e:
        usage.errors.append(f"{type(e).__name__}: {e}")
        raise LLMUnavailable(str(e)) from e
    finally:
        usage.ms += int((time.perf_counter() - t0) * 1000)
    usage.calls += 1
    usage.tokens += tokens
    return text


def _ollama(system: str, user: str, schema: dict | None, s) -> tuple[str, int]:
    body = {"model": s.ollama_model, "stream": False, "think": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_ctx": 6144, "seed": 7}}
    if s.ollama_num_gpu is not None:
        body["options"]["num_gpu"] = s.ollama_num_gpu
    if schema:
        body["format"] = schema
    r = httpx.post(f"{s.ollama_host.rstrip('/')}/api/chat", json=body, timeout=s.llm_timeout_s)
    if r.status_code == 400 and "think" in r.text:      # older Ollama without the think flag
        body.pop("think")
        r = httpx.post(f"{s.ollama_host.rstrip('/')}/api/chat", json=body, timeout=s.llm_timeout_s)
    r.raise_for_status()
    d = r.json()
    return d["message"]["content"], int(d.get("prompt_eval_count", 0)) + int(d.get("eval_count", 0))


def _cloud(system: str, user: str, s) -> tuple[str, int]:
    r = httpx.post(f"{s.cloud_base_url.rstrip('/')}/chat/completions",
                   headers={"Authorization": f"Bearer {s.cloud_api_key}"},
                   json={"model": s.cloud_model, "temperature": 0, "response_format": {"type": "json_object"},
                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                   timeout=s.llm_timeout_s)
    r.raise_for_status()
    d = r.json()
    return d["choices"][0]["message"]["content"], int(d.get("usage", {}).get("total_tokens", 0))


def health() -> dict:
    s = get_settings()
    if s.mock_llm:
        return {"status": "mock", "model": "mock"}
    if s.llm_provider == "cloud":
        return {"status": "ok" if s.cloud_base_url else "down", "model": s.cloud_model, "provider": "cloud"}
    try:
        r = httpx.get(f"{s.ollama_host.rstrip('/')}/api/tags", timeout=2)
        r.raise_for_status()
        names = [m["name"] for m in r.json().get("models", [])]
        ok = any(n == s.ollama_model or n.split(":")[0] == s.ollama_model for n in names)
        return {"status": "ok" if ok else "model_missing", "model": s.ollama_model, "available": names[:10]}
    except Exception as e:
        return {"status": "down", "model": s.ollama_model, "error": type(e).__name__}


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)
