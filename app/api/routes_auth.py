"""Authentication endpoints: login, first-time setup, verification, recovery, sessions."""
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException, status

from app.db import repo
from app.guardrails.security_auth import (
    hash_password,
    safe_student_profile,
    validate_password_strength,
    verify_password,
)
from app.schemas.auth import (
    AuthStatusRequest,
    AuthStatusResponse,
    AuthTokenResponse,
    ChangePasswordRequest,
    ForgotPasswordResetRequest,
    ForgotPasswordVerifyRequest,
    ForgotPasswordVerifyResponse,
    LoginRequest,
    MessageResponse,
    SetupPasswordRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_AUTH_ERROR = "We couldn't verify those details."


def _extract_token(authorization: str | None, x_session_token: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_session_token and x_session_token.strip():
        return x_session_token.strip()
    return None


def get_current_student(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> dict:
    token = _extract_token(authorization, x_session_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in to your university portal.",
        )
    sess = repo.get_auth_session(token)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please sign in again.",
        )
    student = repo.get_student(sess["student_id"])
    if not student:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student account not found.",
        )
    return student


@router.post("/status", response_model=AuthStatusResponse)
def check_status(req: AuthStatusRequest):
    sid = req.student_id.strip().upper()
    student = repo.get_student(sid)
    if not student:
        return AuthStatusResponse(student_id=sid, status="unverified", message=GENERIC_AUTH_ERROR)
    
    auth_rec = repo.get_student_auth(sid)
    if not auth_rec or not auth_rec.get("password_set"):
        return AuthStatusResponse(student_id=sid, status="setup_required")
    return AuthStatusResponse(student_id=sid, status="password_required")


@router.post("/setup-password", response_model=AuthTokenResponse)
def setup_password(req: SetupPasswordRequest):
    sid = req.student_id.strip().upper()
    student = repo.get_student(sid)
    if not student:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_AUTH_ERROR)
    
    auth_rec = repo.get_student_auth(sid)
    if auth_rec and auth_rec.get("password_set"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password has already been set for this account. Please sign in or use password recovery.",
        )
    
    valid, err_msg = validate_password_strength(req.password)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    
    pwd_hash = hash_password(req.password)
    repo.upsert_student_auth(sid, pwd_hash)
    token = repo.create_auth_session(sid, ttl_hours=24)
    return AuthTokenResponse(
        token=token,
        student=safe_student_profile(student),
        message="Password created successfully.",
    )


@router.post("/login", response_model=AuthTokenResponse)
def login(req: LoginRequest):
    sid = req.student_id.strip().upper()
    student = repo.get_student(sid)
    if not student:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_AUTH_ERROR)
    
    auth_rec = repo.get_student_auth(sid)
    if not auth_rec or not auth_rec.get("password_set"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="First-time setup required: Please create your password first.",
        )
    
    # Check account lock
    locked_until = auth_rec.get("locked_until")
    if locked_until:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if locked_until > now_str:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account temporarily locked due to multiple failed login attempts. Please try again later.",
            )
        else:
            repo.reset_failed_attempts(sid)
            
    # Verify password
    if not verify_password(req.password, auth_rec["password_hash"]):
        attempts, locked = repo.record_failed_login(sid, max_attempts=5, lock_minutes=15)
        if locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account temporarily locked due to multiple failed login attempts. Please try again later.",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_AUTH_ERROR)
    
    # Reset attempts on success
    repo.reset_failed_attempts(sid)
    token = repo.create_auth_session(sid, ttl_hours=24)
    return AuthTokenResponse(token=token, student=safe_student_profile(student))


@router.post("/forgot-password/verify", response_model=ForgotPasswordVerifyResponse)
def forgot_password_verify(req: ForgotPasswordVerifyRequest):
    sid = req.student_id.strip().upper()
    is_valid = repo.verify_student_course_match(sid, req.course)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_AUTH_ERROR)
    
    reset_token = repo.create_password_reset_token(sid, ttl_minutes=15)
    return ForgotPasswordVerifyResponse(status="verified", reset_token=reset_token)


@router.post("/forgot-password/reset", response_model=MessageResponse)
def forgot_password_reset(req: ForgotPasswordResetRequest):
    rec = repo.get_valid_password_reset_token(req.reset_token)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password recovery session is invalid or has expired. Please verify your details again.",
        )
    
    valid, err_msg = validate_password_strength(req.new_password)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    
    sid = rec["student_id"]
    pwd_hash = hash_password(req.new_password)
    repo.upsert_student_auth(sid, pwd_hash)
    repo.mark_password_reset_used(req.reset_token)
    repo.reset_failed_attempts(sid)
    return MessageResponse(status="ok", message="Password reset successfully.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    req: ChangePasswordRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
):
    student = get_current_student(authorization, x_session_token)
    sid = student["student_id"]
    auth_rec = repo.get_student_auth(sid)
    if not auth_rec or not verify_password(req.current_password, auth_rec["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password verification failed.")
    
    valid, err_msg = validate_password_strength(req.new_password)
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    
    pwd_hash = hash_password(req.new_password)
    repo.upsert_student_auth(sid, pwd_hash)
    return MessageResponse(status="ok", message="Password updated successfully.")


@router.get("/me")
def me(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
):
    student = get_current_student(authorization, x_session_token)
    return {"student": safe_student_profile(student)}


@router.post("/logout", response_model=MessageResponse)
def logout(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
):
    token = _extract_token(authorization, x_session_token)
    if token:
        repo.delete_auth_session(token)
    return MessageResponse(status="ok", message="Signed out successfully.")
