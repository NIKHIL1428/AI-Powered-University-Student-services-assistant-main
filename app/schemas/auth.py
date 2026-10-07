"""Authentication schemas."""
from pydantic import BaseModel, Field


class AuthStatusRequest(BaseModel):
    student_id: str = Field(..., description="Student roll identifier, e.g. S1001")


class AuthStatusResponse(BaseModel):
    student_id: str
    status: str  # "password_required", "setup_required", "unverified"
    message: str | None = None


class LoginRequest(BaseModel):
    student_id: str
    password: str


class SetupPasswordRequest(BaseModel):
    student_id: str
    password: str


class ForgotPasswordVerifyRequest(BaseModel):
    student_id: str
    course: str


class ForgotPasswordVerifyResponse(BaseModel):
    status: str
    reset_token: str


class ForgotPasswordResetRequest(BaseModel):
    reset_token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AuthTokenResponse(BaseModel):
    token: str
    student: dict
    message: str | None = None


class MessageResponse(BaseModel):
    status: str = "ok"
    message: str
