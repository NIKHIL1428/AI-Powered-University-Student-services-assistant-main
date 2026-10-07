"""UniAssist — NSUT Student Services Portal & University Knowledge Assistant.

Authentic, university-grade portal interface with server-enforced authentication,
deterministic student records, authoritative citations, asynchronous LLM execution,
input locking during generation, and user-controlled termination.
"""
import json
import os
import threading
import time
import uuid
from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

# Institutional branding & status maps
PORTAL_NAME = "UniAssist"
UNIVERSITY_NAME = "Netaji Subhas University of Technology"
UNIVERSITY_SUBTITLE = "State University established by Govt. of NCT of Delhi · Sector-3, Dwarka, New Delhi"

ANSWER_TYPE_MAP = {
    "retrieved_fact": ("Official University Regulation", "#38bdf8", "rgba(56, 189, 248, 0.15)"),
    "calculated": ("Verified Student Record", "#34d399", "rgba(52, 211, 153, 0.15)"),
    "not_found": ("No Authoritative Record Found", "#94a3b8", "rgba(148, 163, 184, 0.15)"),
    "clarification_needed": ("Clarification Required", "#fbbf24", "rgba(251, 191, 36, 0.15)"),
    "refused": ("Access Restricted", "#f87171", "rgba(248, 113, 113, 0.15)"),
    "conflict_flagged": ("Regulatory Notice", "#c084fc", "rgba(192, 132, 252, 0.15)"),
}

st.set_page_config(
    page_title="UniAssist — NSUT Student Services Portal",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ----------------- University Custom Styling -----------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Institutional Header Banner */
    .uni-portal-header {
        background: linear-gradient(135deg, #0f294a 0%, #1e3a8a 100%);
        color: #ffffff !important;
        padding: 1.25rem 2rem;
        border-radius: 8px;
        margin-bottom: 1.25rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    }
    .uni-portal-header * {
        color: #ffffff !important;
    }
    .uni-portal-header-left {
        display: flex;
        align-items: center;
        gap: 1.25rem;
    }
    .uni-crest-icon {
        font-size: 2.25rem;
        background: rgba(255,255,255,0.15);
        padding: 0.5rem 0.65rem;
        border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.25);
    }
    .uni-title-main {
        font-size: 1.25rem;
        font-weight: 700;
        letter-spacing: -0.01em;
        margin: 0;
        line-height: 1.3;
    }
    .uni-subtitle {
        font-size: 0.82rem;
        color: #cbd5e1 !important;
        margin: 0;
        line-height: 1.4;
    }
    .uni-portal-badge {
        display: inline-block;
        background: rgba(255,255,255,0.2);
        color: #e2e8f0 !important;
        font-size: 0.72rem;
        font-weight: 600;
        padding: 0.2rem 0.55rem;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.25rem;
    }

    /* Student welcome bar */
    .student-welcome-bar {
        background: #1e293b;
        color: #f8fafc !important;
        border: 1px solid #334155;
        border-left: 4px solid #38bdf8;
        border-radius: 6px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }
    .student-welcome-bar * {
        color: #f8fafc !important;
    }

    /* Cards */
    .uni-card {
        background: #1e293b;
        color: #f8fafc !important;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 1.25rem;
    }
    .uni-card * {
        color: #f8fafc !important;
    }
    .uni-card-header {
        font-size: 1.05rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        border-bottom: 1px solid #334155;
        padding-bottom: 0.5rem;
    }

    /* Metric boxes */
    .student-metric-box {
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 0.75rem 1rem;
        text-align: center;
    }
    .student-metric-num {
        font-size: 1.4rem;
        font-weight: 700;
        color: #38bdf8 !important;
    }
    .student-metric-label {
        font-size: 0.75rem;
        color: #94a3b8 !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }

    /* Quick service chips */
    .service-chip-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.5rem;
    }

    /* Answer type badge */
    .answer-badge {
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.25rem 0.65rem;
        border-radius: 4px;
        border: 1px solid transparent;
        margin-bottom: 0.5rem;
    }

    /* Evidence metadata block */
    .evidence-meta {
        font-size: 0.84rem;
        color: #cbd5e1;
        background: #0f172a;
        border-left: 3px solid #38bdf8;
        padding: 0.6rem 0.85rem;
        margin-top: 0.5rem;
        margin-bottom: 0.5rem;
        border-radius: 0 4px 4px 0;
    }

    /* Password requirements list */
    .req-list {
        font-size: 0.82rem;
        color: #cbd5e1;
        line-height: 1.5;
        margin: 0.5rem 0 1rem 0;
        padding-left: 1.25rem;
    }

    /* Button styling */
    div.stButton > button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.15s ease;
    }

    /* Tab navigation */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1.5rem !important;
        border-bottom: 2px solid #334155 !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        padding-bottom: 0.75rem !important;
        color: #94a3b8 !important;
    }
    .stTabs [aria-selected="true"] {
        color: #38bdf8 !important;
        font-weight: 700 !important;
        border-bottom: 3px solid #38bdf8 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------- API Client -----------------
def api(method: str, path: str, token: str | None = None, **kw) -> tuple[int, dict | str]:
    headers = kw.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.request(method, f"{API}{path}", headers=headers, timeout=120, **kw)
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.status_code, r.json()
        return r.status_code, r.text
    except requests.RequestException as e:
        return 0, str(e)


# ----------------- Session State Initialization -----------------
if "auth_token" not in st.session_state:
    st.session_state.auth_token = None
if "current_student" not in st.session_state:
    st.session_state.current_student = None
if "auth_view" not in st.session_state:
    st.session_state.auth_view = "login"
if "reset_token" not in st.session_state:
    st.session_state.reset_token = None
if "reset_student_id" not in st.session_state:
    st.session_state.reset_student_id = None
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex
if "history" not in st.session_state:
    st.session_state.history = []
if "show_profile" not in st.session_state:
    st.session_state.show_profile = False
if "prefilled_query" not in st.session_state:
    st.session_state.prefilled_query = ""
if "is_thinking" not in st.session_state:
    st.session_state.is_thinking = False
if "current_task" not in st.session_state:
    st.session_state.current_task = None

# Clean up any legacy dangling turns that had r=None while not thinking
for t in st.session_state.history:
    if t.get("r") is None and not st.session_state.is_thinking:
        t["pending"] = False
        t["r"] = {
            "answer": "Inquiry interrupted or connection reset. Please re-enter your question below.",
            "answer_type": "refused",
            "trace_id": "interrupted",
        }


# ----------------- Portal Header Component -----------------
def render_portal_header():
    student = st.session_state.current_student
    right_content = ""
    if student:
        right_content = f"""
        <div style="text-align: right;">
            <div style="font-size: 0.88rem; font-weight: 600; color: #ffffff;">{student.get('full_name')}</div>
            <div style="font-size: 0.78rem; color: #cbd5e1;">Roll No: {student.get('student_id')} · {student.get('programme')}</div>
        </div>
        """
    st.markdown(
        f"""
        <div class="uni-portal-header">
            <div class="uni-portal-header-left">
                <div class="uni-crest-icon">🏛️</div>
                <div>
                    <h1 class="uni-title-main">{UNIVERSITY_NAME}</h1>
                    <p class="uni-subtitle">{UNIVERSITY_SUBTITLE}</p>
                    <span class="uni-portal-badge">{PORTAL_NAME} · Student Services & Academic Portal</span>
                </div>
            </div>
            {right_content}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ----------------- Authentication Views -----------------
def render_auth_container():
    render_portal_header()
    col1, col2, col3 = st.columns([1, 1.8, 1])
    with col2:
        if st.session_state.auth_view == "login":
            render_login_view()
        elif st.session_state.auth_view == "setup":
            render_setup_password_view()
        elif st.session_state.auth_view == "forgot":
            render_forgot_password_view()
        elif st.session_state.auth_view == "reset":
            render_reset_password_view()


def render_login_view():
    st.markdown(
        """
        <div class="uni-card">
            <div class="uni-card-header">Student Services Assistant — Sign In</div>
            <p style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem;">
                Secure access to your university records, academic regulations, and personalized student services.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("login_form", clear_on_submit=False):
        student_id = st.text_input("Student ID (Roll Number)", placeholder="e.g. S1001", max_chars=10).strip().upper()
        password = st.text_input("Password", type="password", placeholder="Enter your portal password")
        submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

        if submitted:
            if not student_id or not password:
                st.error("Please provide both your Student ID and Password.")
            else:
                code, resp = api("POST", "/auth/login", json={"student_id": student_id, "password": password})
                if code == 200:
                    st.session_state.auth_token = resp["token"]
                    st.session_state.current_student = resp["student"]
                    st.session_state.session_id = uuid.uuid4().hex
                    st.session_state.history = []
                    st.session_state.is_thinking = False
                    st.session_state.current_task = None
                    st.success("Authentication successful. Redirecting to your student dashboard...")
                    st.rerun()
                elif code == 400 and "setup" in str(resp.get("detail", "")).lower():
                    st.session_state.reset_student_id = student_id
                    st.session_state.auth_view = "setup"
                    st.info("First-time setup required: Please create your student password.")
                    st.rerun()
                elif code == 423:
                    st.error("Account temporarily locked due to multiple failed login attempts. Please try again later.")
                else:
                    st.error("We couldn't verify those details.")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Set up password (First-time user)", use_container_width=True):
            st.session_state.auth_view = "setup"
            st.rerun()
    with col_b:
        if st.button("Forgot password?", use_container_width=True):
            st.session_state.auth_view = "forgot"
            st.rerun()


def render_setup_password_view():
    st.markdown(
        """
        <div class="uni-card">
            <div class="uni-card-header">Set Up Your Student Password</div>
            <p style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem;">
                Create a secure password to access your student records and university services.
            </p>
            <ul class="req-list">
                <li>At least 8 characters in length</li>
                <li>At least one uppercase letter (A-Z)</li>
                <li>At least one lowercase letter (a-z)</li>
                <li>At least one numeric digit (0-9)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("setup_form", clear_on_submit=False):
        prefill = st.session_state.reset_student_id or ""
        student_id = st.text_input("Student ID (Roll Number)", value=prefill, placeholder="e.g. S1001").strip().upper()
        pwd1 = st.text_input("New Password", type="password", placeholder="Enter new password")
        pwd2 = st.text_input("Confirm New Password", type="password", placeholder="Re-enter password")
        submit_setup = st.form_submit_button("Create Password", type="primary", use_container_width=True)

        if submit_setup:
            if not student_id or not pwd1 or not pwd2:
                st.error("All fields are required.")
            elif pwd1 != pwd2:
                st.error("Passwords do not match.")
            else:
                code, resp = api("POST", "/auth/setup-password", json={"student_id": student_id, "password": pwd1})
                if code == 200:
                    st.session_state.auth_token = resp["token"]
                    st.session_state.current_student = resp["student"]
                    st.session_state.reset_student_id = None
                    st.session_state.auth_view = "login"
                    st.session_state.is_thinking = False
                    st.session_state.current_task = None
                    st.success("Password created successfully. Logging you in...")
                    st.rerun()
                else:
                    detail = resp.get("detail", "We couldn't verify those details.") if isinstance(resp, dict) else str(resp)
                    st.error(detail)

    if st.button("← Return to Sign In", use_container_width=True):
        st.session_state.auth_view = "login"
        st.rerun()


def render_forgot_password_view():
    st.markdown(
        """
        <div class="uni-card">
            <div class="uni-card-header">Verify Your Student Identity</div>
            <p style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem;">
                To recover your credentials, verify your student identification and enrolled programme or course.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("verify_identity_form"):
        sid = st.text_input("Student ID", placeholder="e.g. S1001").strip().upper()
        course = st.text_input("Enrolled Course or Programme", placeholder="e.g. Data Structures or B.Tech CSE")
        submitted = st.form_submit_button("Verify Identity", type="primary", use_container_width=True)

        if submitted:
            if not sid or not course:
                st.error("Please enter both Student ID and Course/Programme details.")
            else:
                code, resp = api("POST", "/auth/forgot-password/verify", json={"student_id": sid, "course": course})
                if code == 200:
                    st.session_state.reset_token = resp["reset_token"]
                    st.session_state.reset_student_id = sid
                    st.session_state.auth_view = "reset"
                    st.success("Student identity verified successfully.")
                    st.rerun()
                else:
                    st.error("We couldn't verify those details.")

    if st.button("← Return to Sign In", use_container_width=True):
        st.session_state.auth_view = "login"
        st.rerun()


def render_reset_password_view():
    st.markdown(
        f"""
        <div class="uni-card">
            <div class="uni-card-header">Create a New Password</div>
            <p style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.25rem;">
                Set a new password for Student ID <strong>{st.session_state.reset_student_id}</strong>.
            </p>
            <ul class="req-list">
                <li>At least 8 characters in length</li>
                <li>At least one uppercase letter (A-Z)</li>
                <li>At least one lowercase letter (a-z)</li>
                <li>At least one numeric digit (0-9)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("reset_pwd_form"):
        pwd1 = st.text_input("New Password", type="password", placeholder="Enter new password")
        pwd2 = st.text_input("Confirm New Password", type="password", placeholder="Re-enter password")
        submitted = st.form_submit_button("Reset Password", type="primary", use_container_width=True)

        if submitted:
            if not pwd1 or not pwd2:
                st.error("Please enter and confirm your new password.")
            elif pwd1 != pwd2:
                st.error("Passwords do not match.")
            else:
                code, resp = api(
                    "POST",
                    "/auth/forgot-password/reset",
                    json={"reset_token": st.session_state.reset_token, "new_password": pwd1},
                )
                if code == 200:
                    st.session_state.reset_token = None
                    st.session_state.reset_student_id = None
                    st.session_state.auth_view = "login"
                    st.success("Password reset successfully. Please sign in with your new password.")
                    st.rerun()
                else:
                    detail = resp.get("detail", "Password reset failed.") if isinstance(resp, dict) else str(resp)
                    st.error(detail)

    if st.button("Cancel and return to Sign In", use_container_width=True):
        st.session_state.reset_token = None
        st.session_state.auth_view = "login"
        st.rerun()


# ----------------- Query Execution & Termination Logic -----------------
def trigger_query(question: str):
    q = question.strip()
    if not q or st.session_state.is_thinking:
        return
    st.session_state.is_thinking = True
    st.session_state.history.append({"q": q, "r": None, "pending": True})

    task_box = {"done": False, "code": None, "resp": None, "aborted": False}
    st.session_state.current_task = task_box

    def _worker(token, text, date_str, sess_id, box):
        try:
            c, r = api(
                "POST",
                "/ask",
                token=token,
                json={"question": text, "as_of_date": date_str, "session_id": sess_id},
            )
            if not box.get("aborted"):
                box["code"] = c
                box["resp"] = r
                box["done"] = True
        except Exception as e:
            if not box.get("aborted"):
                box["code"] = 500
                box["resp"] = {"answer": f"Inquiry processing error: {e}", "answer_type": "refused"}
                box["done"] = True

    t = threading.Thread(
        target=_worker,
        args=(
            st.session_state.auth_token,
            q,
            date.today().isoformat(),
            st.session_state.session_id,
            task_box,
        ),
        daemon=True,
    )
    t.start()
    st.rerun()


def abort_current_generation():
    if st.session_state.current_task:
        st.session_state.current_task["aborted"] = True
    st.session_state.current_task = None
    st.session_state.is_thinking = False
    if st.session_state.history:
        last = st.session_state.history[-1]
        if last.get("pending"):
            last["pending"] = False
            last["r"] = {
                "answer": "⚠️ **Inquiry generation terminated by student.** You may ask another question below.",
                "answer_type": "refused",
                "trace_id": "terminated_by_user",
            }
    st.toast("LLM generation terminated.", icon="⏹️")


# ----------------- Authenticated Student Dashboard -----------------
def render_authenticated_portal():
    render_portal_header()
    student = st.session_state.current_student
    is_thinking = st.session_state.is_thinking

    # Top Navigation & Utility Controls
    c_left, c_right = st.columns([2.5, 1])
    with c_left:
        now_hour = datetime.now().hour
        greeting = "Good morning" if now_hour < 12 else ("Good afternoon" if now_hour < 17 else "Good evening")
        st.markdown(
            f"""
            <div class="student-welcome-bar">
                <div style="font-size: 1.15rem; font-weight: 700; color: #ffffff;">
                    {greeting}, {student.get('full_name')}
                </div>
                <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.15rem;">
                    Programme: <strong style="color: #ffffff;">{student.get('programme')}</strong> · Batch: <strong style="color: #ffffff;">{student.get('batch_year')}</strong> · Semester: <strong style="color: #ffffff;">{student.get('current_semester')}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_right:
        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            if st.button("👤 Profile", use_container_width=True, disabled=is_thinking):
                st.session_state.show_profile = not st.session_state.show_profile
        with b2:
            if st.button("🔄 New Chat", use_container_width=True, disabled=is_thinking):
                st.session_state.session_id = uuid.uuid4().hex
                st.session_state.history = []
                st.session_state.is_thinking = False
                st.session_state.current_task = None
                st.rerun()
        with b3:
            if st.button("🚪 Logout", use_container_width=True):
                abort_current_generation()
                api("POST", "/auth/logout", token=st.session_state.auth_token)
                st.session_state.auth_token = None
                st.session_state.current_student = None
                st.session_state.history = []
                st.session_state.show_profile = False
                st.session_state.is_thinking = False
                st.session_state.current_task = None
                st.rerun()

    # Expandable Student Profile Panel
    if st.session_state.show_profile:
        render_student_profile_panel(student)

    # Portal Tab Navigation
    tab_assistant, tab_sources, tab_admin = st.tabs([
        "🏛️ Student Services Assistant",
        "📚 University Sources & Regulations",
        "📑 Document Administration (Ingest)",
    ])

    with tab_assistant:
        render_assistant_tab(student)

    with tab_sources:
        render_sources_tab()

    with tab_admin:
        render_ingest_tab()


def render_student_profile_panel(student: dict):
    with st.expander("🎓 Student Academic Profile & Security", expanded=True):
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.markdown(
                f"""
                <div class="student-metric-box">
                    <div class="student-metric-num">{student.get('student_id')}</div>
                    <div class="student-metric-label">Roll Number</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with p2:
            st.markdown(
                f"""
                <div class="student-metric-box">
                    <div class="student-metric-num">Sem {student.get('current_semester')}</div>
                    <div class="student-metric-label">Current Semester</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with p3:
            st.markdown(
                f"""
                <div class="student-metric-box">
                    <div class="student-metric-num">{student.get('cgpa', 'N/A')}</div>
                    <div class="student-metric-label">Cumulative GPA</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with p4:
            st.markdown(
                f"""
                <div class="student-metric-box">
                    <div class="student-metric-num">{student.get('active_backlogs', 0)}</div>
                    <div class="student-metric-label">Active Backlogs</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<hr style='margin: 1rem 0; border: none; border-top: 1px solid #334155;'>", unsafe_allow_html=True)
        st.markdown("<strong>Update Account Password</strong>", unsafe_allow_html=True)
        with st.form("change_pwd_form"):
            cp1, cp2, cp3 = st.columns(3)
            with cp1:
                old_pwd = st.text_input("Current Password", type="password")
            with cp2:
                new_pwd1 = st.text_input("New Password", type="password")
            with cp3:
                new_pwd2 = st.text_input("Confirm New Password", type="password")
            submit_change = st.form_submit_button("Update Password", type="secondary")

            if submit_change:
                if not old_pwd or not new_pwd1 or not new_pwd2:
                    st.error("Please fill in all password fields.")
                elif new_pwd1 != new_pwd2:
                    st.error("New passwords do not match.")
                else:
                    code, resp = api(
                        "POST",
                        "/auth/change-password",
                        token=st.session_state.auth_token,
                        json={"current_password": old_pwd, "new_password": new_pwd1},
                    )
                    if code == 200:
                        st.success("Password updated successfully.")
                    else:
                        st.error(resp.get("detail", "Password update failed.") if isinstance(resp, dict) else str(resp))


def render_assistant_tab(student: dict):
    is_thinking = st.session_state.is_thinking

    # Quick Services Chips
    st.markdown('<div class="service-chip-label">Quick University Inquiries</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        if st.button("📊 Attendance in DS", use_container_width=True, disabled=is_thinking):
            trigger_query("What is my attendance in Data Structures?")
    with c2:
        if st.button("📝 End-Sem Eligibility", use_container_width=True, disabled=is_thinking):
            trigger_query("Am I eligible for the end-sem exam in Data Structures?")
    with c3:
        if st.button("🏛️ Dean's Relaxation", use_container_width=True, disabled=is_thinking):
            trigger_query("If the Dean grants relaxation, can I appear in the end-sem exam for Data Structures?")
    with c4:
        if st.button("💰 Kotak Scholarship", use_container_width=True, disabled=is_thinking):
            trigger_query("Till when can I apply for the Kotak Kanya scholarship?")
    with c5:
        if st.button("📜 Minimum Attendance", use_container_width=True, disabled=is_thinking):
            trigger_query("What is the minimum attendance required to appear for end-semester exams?")

    st.markdown("<hr style='margin: 0.75rem 0 1.25rem 0; border: none; border-top: 1px solid #334155;'>", unsafe_allow_html=True)

    # Conversation History Display
    for i, turn in enumerate(st.session_state.history):
        with st.chat_message("user", avatar="🎓"):
            st.markdown(f"**Student Inquiry:** {turn['q']}")
        with st.chat_message("assistant", avatar="🏛️"):
            if turn.get("pending"):
                # Active Thinking State with Live Terminate Button
                c_status, c_abort = st.columns([3, 1])
                with c_status:
                    st.info("⏳ **Consulting university regulations and records...** The assistant is generating a response.")
                with c_abort:
                    if st.button("⏹️ Terminate LLM", type="primary", use_container_width=True, key=f"terminate_btn_{i}"):
                        abort_current_generation()
                        st.rerun()
            elif turn.get("r"):
                render_response_card(turn["r"])

    # Polling & Input Locking Controller
    if is_thinking:
        task = st.session_state.current_task
        if task and task.get("done") and not task.get("aborted"):
            # Task finished! Render result
            st.session_state.is_thinking = False
            st.session_state.current_task = None
            if st.session_state.history:
                last_turn = st.session_state.history[-1]
                last_turn["pending"] = False
                code = task.get("code")
                resp = task.get("resp")
                if code == 200 and isinstance(resp, dict):
                    last_turn["r"] = resp
                else:
                    last_turn["r"] = {
                        "answer": f"Unable to process inquiry (HTTP {code}): {resp}",
                        "answer_type": "refused",
                        "trace_id": "error",
                    }
            st.rerun()
        else:
            # Still generating: chat input is strictly locked to prevent sending another message
            st.warning("🔒 **Chat input is locked while assistant is generating.** Click **Terminate LLM** above to stop.")
            time.sleep(1)
            st.rerun()
    else:
        # Not generating: chat input is available
        default_text = st.session_state.prefilled_query
        q = st.chat_input("Ask about academic regulations, attendance, exams, fees, scholarships, policies...")
        if default_text and not q:
            q = default_text
            st.session_state.prefilled_query = ""

        if q:
            trigger_query(q)


def render_response_card(resp: dict):
    ans_type = resp.get("answer_type", "retrieved_fact")
    label, text_color, bg_color = ANSWER_TYPE_MAP.get(ans_type, (ans_type, "#38bdf8", "rgba(56, 189, 248, 0.15)"))

    st.markdown(
        f"""
        <div style="margin-bottom: 0.5rem;">
            <span class="answer-badge" style="background-color: {bg_color}; color: {text_color}; border-color: {text_color}40;">
                ● {label}
            </span>
            <span style="font-size: 0.75rem; color: #94a3b8; margin-left: 0.5rem;">
                Trace ID: {resp.get('trace_id', '-')}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Core Answer
    st.markdown(resp.get("answer", ""))

    # AI Context / Explanation (subtly distinguished)
    if resp.get("explanation"):
        st.markdown(
            f"""
            <div class="evidence-meta">
                <strong>Administrative Note:</strong> {resp['explanation']}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Assumptions & Warnings
    if resp.get("assumptions"):
        st.info("📌 **Regulatory Assumptions:** " + "; ".join(resp["assumptions"]))

    if resp.get("conflicts_detected"):
        with st.expander(f"⚠️ Regulatory Conflicts Flagged ({len(resp['conflicts_detected'])})"):
            st.json(resp["conflicts_detected"])

    if resp.get("upcoming_changes"):
        st.warning("⏱️ **Upcoming Policy Amendments:** " + "; ".join(
            f"{u['doc_id']} ({u.get('value', '')}) effective from {u.get('effective_from', '')}"
            for u in resp["upcoming_changes"]
        ))

    # Authoritative Citations Panel
    citations = resp.get("citations", [])
    if citations:
        with st.expander(f"📜 Authoritative Citations & Evidentiary Sources ({len(citations)})", expanded=False):
            df_cite = pd.DataFrame(citations)
            rename_cols = {
                "source_doc_id": "Document ID",
                "title": "Title / Policy",
                "section": "Section / Clause",
                "page": "Page",
                "authority_level": "Authority Level",
                "version": "Version",
                "effective_from": "Effective From",
            }
            display_cols = [c for c in rename_cols if c in df_cite.columns]
            df_display = df_cite[display_cols].rename(columns=rename_cols)
            st.dataframe(df_display, hide_index=True, use_container_width=True)

    # Deterministic Tools Executed
    tools_invoked = resp.get("tools_invoked", [])
    if tools_invoked:
        with st.expander(f"🛠️ Deterministic Service Tools ({len(tools_invoked)})", expanded=False):
            for t in tools_invoked:
                st.markdown(f"**Tool:** `{t['tool']}` · **Parameters:** `{json.dumps(t['input'])}`")
                st.json(t["output"], expanded=False)

    # Applied Registry Rules
    if resp.get("applied_rules"):
        rules_text = ", ".join(f"{r['rule_id']} [{r['value']}] from {r['source_doc_id']}" for r in resp["applied_rules"])
        st.caption(f"Governance Rules Applied: {rules_text}")


def render_sources_tab():
    st.markdown(
        """
        <div class="uni-card">
            <div class="uni-card-header">Official University Source Register & Rule Registry</div>
            <p style="font-size: 0.85rem; color: #94a3b8;">
                All answers are grounded strictly in the 44 official university notices, academic ordinances,
                and statutory regulations listed below.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    code, body = api("GET", "/sources")
    if code == 200:
        st.subheader("Authoritative Document Register")
        st.dataframe(pd.DataFrame(body["sources"]), hide_index=True, use_container_width=True)
        st.subheader("University Rule & Parameter Registry")
        st.dataframe(pd.DataFrame(body["rules"]), hide_index=True, use_container_width=True)
    else:
        st.error(f"Unable to retrieve university registry: {body}")


def render_ingest_tab():
    st.markdown(
        """
        <div class="uni-card">
            <div class="uni-card-header">Document Ingestion & Regulatory Registration</div>
            <p style="font-size: 0.85rem; color: #94a3b8;">
                Administrative portal to ingest new notifications, circulars, or regulations with automatic
                PII sanitization, OCR fallback, vector embedding, and statutory rule extraction.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    f = st.file_uploader("Upload University Notice / PDF / Scanned Image", type=["pdf", "png", "jpg", "jpeg", "txt"])
    c1, c2, c3 = st.columns(3)
    doc_id = c1.text_input("Document Identifier (doc_id)", "NEW-CIRC-2026-01")
    title = c2.text_input("Document Title", "")
    issuer = c3.text_input("Issuing Authority", "Office of the Dean (Academics)")
    level = c1.selectbox("Authority Hierarchy Level", [1, 2, 3, 4, 5], index=1)
    doc_type = c2.selectbox("Document Classification", ["regulation", "circular", "notice", "faq", "handbook", "unofficial"], index=1)
    version = c3.text_input("Version Tag", "1.0")
    eff_from = c1.date_input("Effective Date", value=date.today())
    eff_to = c2.text_input("Effective Until (optional)", "")
    supersedes = c3.text_input("Supersedes (DOC#clause)", "")
    progs = c1.text_input("Applicable Programmes", "ALL")
    batches = c2.text_input("Applicable Batches", "ALL")
    provenance = c3.text_input("Provenance / Archival Note", "Dean's Office Publication")
    synthetic = c1.selectbox("Synthetic Notice Indicator", ["N", "Y"])
    raw_json = st.text_area("Optional Raw Metadata JSON (overrides form inputs)", "")

    if st.button("Ingest and Register Document", type="primary", disabled=f is None):
        meta = json.loads(raw_json) if raw_json.strip() else {
            "doc_id": doc_id,
            "title": title or doc_id,
            "issuer": issuer,
            "authority_level": level,
            "doc_type": doc_type,
            "version": version,
            "effective_from": eff_from.isoformat(),
            "effective_to": eff_to,
            "supersedes": supersedes,
            "scope_programmes": progs,
            "scope_batches": batches,
            "provenance": provenance,
            "retrieved_on": date.today().isoformat(),
            "synthetic": synthetic,
        }
        with st.spinner("Extracting text layer, OCR verification, chunking, and embedding into ChromaDB..."):
            c, body = api(
                "POST",
                "/ingest",
                token=st.session_state.auth_token,
                files={"file": (f.name, f.getvalue())},
                data={"metadata": json.dumps(meta)},
            )
        if c == 200:
            st.success("Document ingested and registered successfully!")
            st.json(body)
        else:
            st.error(f"Ingestion failed with status HTTP {c}: {body}")


# ----------------- Main Controller -----------------
def main():
    if not st.session_state.auth_token:
        render_auth_container()
    else:
        render_authenticated_portal()


if __name__ == "__main__":
    main()
