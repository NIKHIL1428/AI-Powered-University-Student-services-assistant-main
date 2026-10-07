"""Tests for student authentication, password lifecycle, sessions, and security."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import repo


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_status_flow(client):
    # Non-existent student
    r = client.post("/auth/status", json={"student_id": "S9999"})
    assert r.status_code == 200
    assert r.json()["status"] == "unverified"

    # Valid student needing setup
    r = client.post("/auth/status", json={"student_id": "S8001"})
    assert r.status_code == 200
    assert r.json()["status"] in ("setup_required", "password_required")


def test_password_strength_and_setup(client):
    # Weak passwords
    r = client.post("/auth/setup-password", json={"student_id": "S8001", "password": "weak"})
    assert r.status_code == 400
    assert "at least 8 characters" in r.json()["detail"].lower()

    r = client.post("/auth/setup-password", json={"student_id": "S8001", "password": "nouppercase123"})
    assert r.status_code == 400
    assert "uppercase" in r.json()["detail"].lower()

    # Valid password setup
    r = client.post("/auth/setup-password", json={"student_id": "S8001", "password": "Password123!"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["student"]["student_id"] == "S8001"
    assert "password" not in data["student"]
    assert "password_hash" not in data["student"]

    # Re-setup must fail
    r = client.post("/auth/setup-password", json={"student_id": "S8001", "password": "Password123!"})
    assert r.status_code == 400


def test_login_and_account_locking(client):
    # Bad credentials
    r = client.post("/auth/login", json={"student_id": "S8001", "password": "WrongPassword1"})
    assert r.status_code == 401
    assert "we couldn't verify those details" in r.json()["detail"].lower()

    # Repeated failures trigger lockout
    for _ in range(4):
        client.post("/auth/login", json={"student_id": "S8001", "password": "WrongPassword1"})

    r = client.post("/auth/login", json={"student_id": "S8001", "password": "Password123!"})
    assert r.status_code == 423
    assert "locked" in r.json()["detail"].lower()

    # Reset attempts for subsequent tests
    repo.reset_failed_attempts("S8001")
    r = client.post("/auth/login", json={"student_id": "S8001", "password": "Password123!"})
    assert r.status_code == 200
    assert "token" in r.json()


def test_session_token_authorization(client):
    # Login to obtain valid token
    r = client.post("/auth/login", json={"student_id": "S8001", "password": "Password123!"})
    token = r.json()["token"]

    # Verify profile endpoint
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["student"]["student_id"] == "S8001"

    # Ask personal question with session token (without passing X-Student-Id)
    r = client.post("/ask", json={"question": "What is my attendance in CS201?"},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["answer_type"] in ("calculated", "retrieved_fact")

    # Anti-spoofing: passing another student's ID in header with valid S8001 token is refused
    r = client.post("/ask", json={"question": "What is my attendance in CS201?"},
                    headers={"Authorization": f"Bearer {token}", "X-Student-Id": "S8002"})
    assert r.status_code == 200
    assert r.json()["answer_type"] == "refused"


def test_forgot_password_recovery(client):
    # Invalid course info fails generically
    r = client.post("/auth/forgot-password/verify", json={"student_id": "S8001", "course": "NonExistentCourse"})
    assert r.status_code == 400
    assert "we couldn't verify those details" in r.json()["detail"].lower()

    # Valid student course/programme verification
    student = repo.get_student("S8001")
    programme = student["programme"]
    r = client.post("/auth/forgot-password/verify", json={"student_id": "S8001", "course": programme})
    assert r.status_code == 200
    reset_token = r.json()["reset_token"]

    # Reset password
    r = client.post("/auth/forgot-password/reset", json={"reset_token": reset_token, "new_password": "NewPassword99!"})
    assert r.status_code == 200

    # Reset token cannot be reused
    r = client.post("/auth/forgot-password/reset", json={"reset_token": reset_token, "new_password": "AnotherPassword99!"})
    assert r.status_code == 400

    # Login with new password
    r = client.post("/auth/login", json={"student_id": "S8001", "password": "NewPassword99!"})
    assert r.status_code == 200


def test_logout(client):
    r = client.post("/auth/login", json={"student_id": "S8001", "password": "NewPassword99!"})
    token = r.json()["token"]

    # Logout
    r = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    # Token is now invalid
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
