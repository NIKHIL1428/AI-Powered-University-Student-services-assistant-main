"""Parse -> Pydantic-validate -> retry with error feedback (2x) -> None (caller falls back deterministically)."""
import json
import re

from pydantic import BaseModel, ValidationError

from app.llm.qwen import LLMUnavailable, LLMUsage, chat


def _extract_json(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text


def call_json(system: str, user: str, model: type[BaseModel], usage: LLMUsage, retries: int = 2):
    schema = model.model_json_schema()
    prompt = user
    for attempt in range(retries + 1):
        try:
            raw = chat(system, prompt, schema, usage)
        except LLMUnavailable:
            return None
        try:
            return model.model_validate(json.loads(_extract_json(raw)))
        except (json.JSONDecodeError, ValidationError) as e:
            usage.errors.append(f"invalid JSON (attempt {attempt + 1}): {str(e)[:200]}")
            prompt = (f"{user}\n\nYour previous output was invalid: {str(e)[:300]}\n"
                      f"Return ONLY a JSON object matching the schema.")
    return None
