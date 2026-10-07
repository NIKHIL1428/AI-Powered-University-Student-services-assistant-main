"""PII masking for audit/memory text: emails, phone numbers, other students' ids."""
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
SID = re.compile(r"\bS\d{4}\b", re.I)


def redact(text: str, keep_id: str | None = None) -> str:
    if not text:
        return text
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    return SID.sub(lambda m: m.group(0) if keep_id and m.group(0).upper() == keep_id else "[student-id]", text)
