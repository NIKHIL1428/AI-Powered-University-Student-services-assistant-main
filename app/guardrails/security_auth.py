"""Authentication security utilities: password policy, bcrypt hashing, safe profiles."""
import re
import bcrypt

PASSWORD_MIN_LENGTH = 8


def validate_password_strength(password: str) -> tuple[bool, str | None]:
    """Enforces academic portal password policy:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    """
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        return False, "Password must be at least 8 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number."
    return True, None


def hash_password(password: str) -> str:
    """Hash password securely using bcrypt with automatic salt generation."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash in constant time."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def safe_student_profile(student: dict) -> dict:
    """Return authorized student portal attributes. Never exposes credentials or internal keys."""
    return {
        "student_id": student.get("student_id"),
        "full_name": student.get("full_name"),
        "programme": student.get("programme"),
        "batch_year": student.get("batch_year"),
        "current_semester": student.get("current_semester"),
        "cgpa": student.get("cgpa"),
        "active_backlogs": student.get("active_backlogs"),
    }
