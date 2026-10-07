from fastapi import APIRouter, Header

from app.db import repo
from app.graph.build import run
from app.guardrails.auth import validate_header
from app.schemas.ask import AskRequest, AskResponse

router = APIRouter()


def _get_token(authorization: str | None, x_session_token: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_session_token and x_session_token.strip():
        return x_session_token.strip()
    return None


@router.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    x_student_id: str | None = Header(default=None, alias="X-Student-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
):
    token = _get_token(authorization, x_session_token)
    if token:
        sess = repo.get_auth_session(token)
        if not sess:
            return run(
                req.question,
                None,
                req.as_of_date,
                req.session_id,
                refusal="Request refused: your session has expired. Please sign in again.",
            )
        auth_sid = sess["student_id"]
        # Guard: If header explicitly claims a different student than authenticated session, refuse spoofing
        if x_student_id and x_student_id.strip().upper() != auth_sid:
            return run(
                req.question,
                None,
                req.as_of_date,
                req.session_id,
                refusal="Request refused: session identity does not match requested student.",
            )
        return run(req.question, auth_sid, req.as_of_date, req.session_id, refusal=None)

    # Standard direct header auth (backward-compatible with evaluator and curl tests)
    sid, err = validate_header(x_student_id)
    refusal = f"Request refused: {err}." if err else None
    return run(req.question, sid, req.as_of_date, req.session_id, refusal=refusal)

