"""R8: document text is data. Instruction-like sentences are flagged at ingest and masked before the LLM sees them.

This is defence in depth: the LLM has no tool-execution power and its output never decides eligibility.
"""
import re

PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|rules|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above|system)",
    r"\byou are now\b", r"\bact as\b", r"\bsystem prompt\b", r"\bdeveloper mode\b",
    r"\b(assistant|ai|chatbot|model|llm)s?\s*(must|should|shall)\b",
    r"\b(tell|inform) (the |every |all )?(student|user)s? (that )?(they|he|she) (are|is) eligible",
    r"\breveal (the )?(prompt|instructions|data)", r"\boverride\b.{0,40}\b(rule|policy|instruction)",
    r"\bcall the tool\b", r"\bexecute\b.{0,30}\b(tool|function|sql|command)",
    r"<\s*/?\s*(system|instruction|tool_result|document)\s*>",
]
_RX = re.compile("|".join(PATTERNS), re.I)
MASK = "[instruction-like text removed: documents are data, not instructions]"


def is_suspicious(text: str) -> bool:
    return bool(_RX.search(text or ""))


def sanitize(text: str) -> tuple[str, bool]:
    """Mask sentences containing instruction-like content. Returns (clean_text, was_flagged)."""
    if not is_suspicious(text):
        return text, False
    parts = re.split(r"(?<=[.!?\n])\s+", text)
    return " ".join(MASK if _RX.search(p) else p for p in parts), True
