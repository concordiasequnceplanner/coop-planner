import os
import re
import json
import datetime
import random


import pandas as pd
import pymysql  # needed for mysql+pymysql SQLAlchemy dialect
import resend
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import create_engine, text
from html import escape


from utils import (
    load_data,
    load_programs_requirements,
    parse_term,
    send_email,
    send_otp_email,
    calculate_cgpa,
    process_student_data,
    load_sequences,
    load_restrictions,
    get_email_recipients,
    debug_no_emails,
) 

# =========================================================
# STATUS CONSTANTS
# =========================================================
STATUS_PENDING_APPROVAL = "PENDING APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_REWORK = "REWORK"
STATUS_SAVED_DRAFT = "SAVED DRAFT"
STATUS_IGNORED = "IGNORED"

def _get_priority1_email_db(target_sid: str) -> str:
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            q = text("""
                SELECT `Primary Email`
                FROM `Sid_Email_Admission`
                WHERE `Student ID` = :sid
                ORDER BY `email_priority` ASC
                LIMIT 1
            """)
            r = conn.execute(q, {"sid": target_sid}).fetchone()
            if r and r[0]:
                return str(r[0]).strip()
    except Exception as e:
        print(f"❌ get_priority1_email_db error: {e}")
    return None

app = Flask(__name__)
app.secret_key = "SVsecretKEY_MIAE_2024"

# =========================================================
# SESSION TIMEOUT (auto-logoff)
# =========================================================
SESSION_TIMEOUT_STUDENT = 5 * 60    # 30 minutes (seconds)
SESSION_TIMEOUT_POWER   = 8 * 60 * 60  # 8 hours (seconds)
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=9)  # absolute max cookie lifetime

@app.before_request
def check_session_timeout():
    # Skip for static files, login, verify, health, favicon
    if request.endpoint in (None, 'static', 'login', 'verify', 'health', 'favicon'):
        return
    if 'student_id' not in session:
        return

    now = datetime.datetime.now().timestamp()
    last_active = session.get('last_active', now)

    is_power = str(session.get('student_id', '')).startswith('9') and not session.get('is_guest', False)
    timeout = SESSION_TIMEOUT_POWER if is_power else SESSION_TIMEOUT_STUDENT

    if now - last_active > timeout:
        session.clear()
        return redirect(url_for('login'))

    session['last_active'] = now

# =========================================================
# RATE LIMITING
# =========================================================
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per 15 minutes"],
    storage_uri="memory://"
)

# =========================================================
# DATABASE
# =========================================================
DB_USER = os.environ.get("planner_db_USER")
DB_PASS = os.environ.get("planner_db_password")
DB_HOST = os.environ.get("planner_db_HOST")
DB_NAME = os.environ.get("planner_db_NAME")

engine = None
if DB_PASS:
    DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}"
    engine = create_engine(
        DATABASE_URI,
        pool_pre_ping=True,
        pool_recycle=280,
        pool_size=10,
        max_overflow=20,
        connect_args={"ssl": {}},
    )

# =========================================================
# HELPERS
# =========================================================

def _require_login():
    return ("student_id" in session) and (engine is not None)


def _is_power_user():
    sid = str(session.get("student_id", "")).strip()
    return sid.startswith("9") and not session.get("is_guest", False)


def _current_sid():
    return str(session.get("student_id", "")).strip()


def _viewing_sid():
    cur = _current_sid()
    if _is_power_user():
        return str(session.get("admin_view_sid", cur)).strip()
    return cur


def _safe_json_load(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "nan"):
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _get_student_email_db(target_sid: str) -> str:
    """Best-effort email for a student."""
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            q = text(
                "SELECT `Primary Email` FROM `Sid_Email_Admission` "
                "WHERE `Student ID` = :sid ORDER BY `email_priority` ASC LIMIT 1"
            )
            r = conn.execute(q, {"sid": target_sid}).fetchone()
            if r and r[0]:
                return str(r[0]).strip()
    except Exception as e:
        print(f"❌ get_student_email_db error: {e}")
    return None


def _get_student_name_db(target_sid: str) -> str:
    """Best-effort name for a student."""
    if engine is None:
        return None
    try:
        with engine.connect() as conn:
            # View name (preferred)
            r = conn.execute(
                text("SELECT `Name` FROM `login vs id` WHERE `Student ID` = :sid LIMIT 1"),
                {"sid": target_sid},
            ).fetchone()
            if r and r[0]:
                return str(r[0]).strip()
    except Exception:
        pass

    try:
        with engine.connect() as conn:
            # Fallback: Transcripts.NAME if present
            r = conn.execute(
                text(
                    "SELECT NAME FROM Transcripts WHERE `Student ID` = :sid "
                    "AND NAME IS NOT NULL AND NAME <> '' LIMIT 1"
                ),
                {"sid": target_sid},
            ).fetchone()
            if r and r[0]:
                return str(r[0]).strip()
    except Exception:
        pass

    return None

def fmt_cr(v):
    try:
        x = float(v or 0)
        return str(int(x)) if x.is_integer() else str(x)
    except Exception:
        return str(v or 0)

def nl2html(txt, fallback=""):
    s = str(txt or "").strip()
    if not s:
        s = fallback
    return escape(s).replace("\n", "<br>")

def build_terms_html(term_summary, include_grades=True):
    if not term_summary:
        return ""

    # Check if user is power user
    is_power = _is_power_user()

    out = []
    out.append("<table style='width:100%;border-collapse:collapse;margin-top:15px;font-size:13px;'>")
    out.append("<thead><tr style='color:white;'>")
    out.append("<th style='background:#34495e;padding:10px;border:1px solid #ddd;width:16%;'>Year</th>")
    out.append("<th style='background:#27ae60;padding:10px;border:1px solid #ddd;width:28%;'>Summer</th>")
    out.append("<th style='background:#f39c12;padding:10px;border:1px solid #ddd;width:28%;'>Fall</th>")
    out.append("<th style='background:#3498db;padding:10px;border:1px solid #ddd;width:28%;'>Winter</th>")
    out.append("</tr></thead><tbody>")

    for ts in term_summary:
        year_str = escape(str(ts.get("year", "") or ""))
        tdata = ts.get("data", {})

        out.append(
            f"<tr><td style='padding:8px;border:1px solid #ddd;text-align:center;vertical-align:top;"
            f"font-weight:bold;background:#f8f9fa;'>{year_str}</td>"
        )

        for t_key in ["SUM", "FALL", "WIN"]:
            td = tdata.get(t_key, {})
            cr = fmt_cr(td.get("cr", 0))
            courses = td.get("courses", [])
            coop_label = escape(str(td.get("coop_label", "") or ""))
            coop_kind = str(td.get("coop_kind", "") or "")

            if coop_kind == "work":
                coop_style = "background:#90caf9;color:#0d47a1;"
            elif coop_kind == "study":
                coop_style = "background:#e1f5fe;color:#0277bd;"
            else:
                coop_style = "background:#f5f5f5;color:#666;"

            header_html = ""
            if coop_label:
                header_html = (
                    f"<div style='display:inline-block;margin-left:8px;padding:2px 8px;"
                    f"border-radius:12px;font-size:11px;font-weight:800;{coop_style}'>"
                    f"{coop_label}</div>"
                )

            course_lines = []
            for c in courses:
                cname = escape(str(c.get("name", "") or ""))
                ccr = fmt_cr(c.get("credit", 0))
                is_wt = bool(c.get("is_wt"))
                grade = str(c.get("grade", "")).strip()
                
                # Build course text
                course_text = f"{cname} ({ccr}cr)"
                
                # Add grade only for power users AND only if include_grades is True
                if is_power and grade and include_grades:
                    course_text += f" --> {escape(grade)}"
                
                style = "color:#00c853;font-weight:800;" if is_wt else "color:#333;"
                course_lines.append(f"<div style='margin:0 0 4px 0;{style}'>{course_text}</div>")

            c_html = "".join(course_lines) if course_lines else "<div>&nbsp;</div>"

            out.append(
                f"<td style='padding:8px;border:1px solid #ddd;text-align:left;vertical-align:top;'>"
                f"<div style='font-weight:800;margin-bottom:10px;'>{cr}cr{header_html}</div>"
                f"<div style='line-height:1.55;'>{c_html}</div>"
                f"</td>"
            )

        out.append("</tr>")

    out.append("</tbody></table>")
    return "".join(out)

def render_sequence_email(mode, student_email, student_name, target_sid, program,
                          terms_html="", comments_html="", wt_html="", wt_status_msg="",
                          signer="Coordinator", notes_html=""):
    if mode == "PENDING":
        return f"""
        <div style="font-family:Arial,sans-serif;color:#333;max-width:750px;margin:0 auto;border:1px solid #e0e0e0;padding:20px;border-radius:8px;">
            <h2 style="color:#912338;border-bottom:2px solid #912338;padding-bottom:10px;">Sequence Submitted for Approval</h2>
            <p><b>Student Email:</b> {escape(student_email or '')}</p>
            <p><b>Student Name:</b> {escape(student_name or '')}</p>
            <p><b>Student ID:</b> {escape(target_sid or '')}</p>
            <p><b>Program:</b> {escape(program or '')}</p>

            <h3 style="margin-top:20px;">Submitted Sequence</h3>
            {terms_html}

            <div style="text-align:center;margin:25px 0;">
                <a href="https://concordia-sequence-planner.onrender.com/"
                   style="background:#912338;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;font-weight:bold;">
                    Open Planner to Review
                </a>
            </div>
        </div>
        """

    if mode == "APPROVED":
        notes_section = ""
        if notes_html:
            notes_section = f"""
                <p><b>Notes:</b></p>
                <div style="background:#fff8e1;border:1px solid #ffe082;border-left:4px solid #f39c12;padding:12px;border-radius:5px;line-height:1.6;font-size:13px;">
                    {notes_html}
                </div>
            """
        return f"""
        <div style="font-family:Arial,sans-serif;color:#333;max-width:750px;margin:0 auto;border:1px solid #e0e0e0;padding:20px;border-radius:8px;">
            <h2 style="color:#2c3e50;border-bottom:2px solid #3498db;padding-bottom:10px;">Approved Course Sequence</h2>
            {wt_status_msg}
            <p><b>Student Email:</b> {escape(student_email or '')}</p>
            <p><b>Student Name:</b> {escape(student_name or '')}</p>
            <p><b>Student ID:</b> {escape(target_sid or '')}</p>
            <p><b>Program:</b> {escape(program or '')}</p>

            <div style="background:#f0f7ff;border-left:4px solid #3498db;padding:10px;margin:15px 0;">
                {wt_html}
            </div>

            <p><b>Comments:</b></p>
            <div style="background:#e8f5e9;border:1px solid #c8e6c9;padding:12px;border-radius:5px;line-height:1.6;">
                {comments_html}
            </div>

            {notes_section}

            <h3>Approved Sequence</h3>
            {terms_html}

            <p style="margin-top:30px;">Best Regards,<br><b>{escape(signer or '')}</b></p>
        </div>
        """

    return ""


# =========================================================
# SECURITY: mask email (anti-F12)
# =========================================================

def mask_email(email: str) -> str:
    try:
        name, domain = email.split("@")
        masked_name = f"{name[0]}****{name[-1]}" if len(name) > 1 else f"{name}****"
        domain_parts = domain.split(".")
        domain_name = domain_parts[0]
        masked_domain_name = f"{domain_name[0]}****" if domain_name else "****"
        masked_domain = masked_domain_name + "." + ".".join(domain_parts[1:])
        return f"{masked_name}@{masked_domain}"
    except Exception:
        return "e****l@d****.***"


@app.route("/favicon.ico")
def favicon():
    return ("", 204)

@app.route("/health")
def health():
    return "ok", 200
# =========================================================
# AUTH ROUTES
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action", "check_email")

        # 1) Email recovery by Student ID
        if action == "recover_email":
            student_id = request.form.get("student_id", "").strip()
            try:
                with engine.connect() as conn:
                    query = text(
                        "SELECT `Primary Email` FROM `Sid_Email_Admission` "
                        "WHERE `Student ID` = :sid LIMIT 1"
                    )
                    res = conn.execute(query, {"sid": student_id}).fetchone()
                    if res and res[0]:
                        masked = mask_email(str(res[0]).strip())
                        return render_template("login.html", popup_message=f"Please use {masked}")
                    return render_template(
                        "login.html",
                        ask_student_id=True,
                        error="Nu există ID / ID does not exist.",
                    )
            except Exception as e:
                print(f"❌ DB Error Recovery: {e}")
                return render_template("login.html", error="An error occurred. Please try again.")

        # 2) Normal login via email + OTP
        email = request.form.get("email", "").strip().lower()
        try:
            with engine.begin() as conn:
                res = conn.execute(
                    text(
                        "SELECT `Student ID` FROM `Sid_Email_Admission` "
                        "WHERE LOWER(`Primary Email`) = :email LIMIT 1"
                    ),
                    {"email": email},
                ).fetchone()

                if not res:
                    return render_template("login.html", ask_student_id=True, error="Email not found.")

                sid = str(res[0]).strip()
                now = datetime.datetime.now()

                recent_res = conn.execute(
                    text(
                        "SELECT time FROM logins WHERE email = :email AND used < 2 "
                        "ORDER BY time DESC LIMIT 1"
                    ),
                    {"email": email},
                ).fetchone()

                if recent_res:
                    last_time = recent_res[0]
                    if isinstance(last_time, str):
                        try:
                            last_time = datetime.datetime.strptime(last_time, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            pass

                    if isinstance(last_time, datetime.datetime):
                        diff_seconds = (now - last_time).total_seconds()
                        if diff_seconds < 1800:
                            remaining_mins = int(30 - (diff_seconds // 60))
                            msg = (
                                f"An access code was already sent at {last_time.strftime('%H:%M')}. "
                                f"Please reuse it! It remains valid for the next {remaining_mins} minutes. "
                                f"(Server time is {now.strftime('%H:%M')})"
                            )
                            session["pre_auth_email"] = email
                            session["temp_sid"] = sid
                            session["attempts"] = 0
                            return render_template("verify.html", email=email, message=msg)

                # Generate new OTP
                otp = str(random.randint(100000, 999999))
                timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")

                conn.execute(text("UPDATE logins SET used = 1 WHERE email = :email"), {"email": email})
                conn.execute(
                    text("INSERT INTO logins (email, time, login_code, used) VALUES (:email, :t, :c, 0)"),
                    {"email": email, "t": timestamp_str, "c": otp},
                )

                if send_otp_email(email, otp):
                    session["pre_auth_email"] = email
                    session["temp_sid"] = sid
                    session["attempts"] = 0
                    return render_template("verify.html", email=email)

                return render_template("login.html", error="Email service failed. Try again.")

        except Exception as e:
            print(f"❌ DB Error Login: {e}")
            return render_template("login.html", error="An error occurred. Please try again.")

    return render_template("login.html")


@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get("pre_auth_email")
    if not email:
        return redirect(url_for("login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        try:
            with engine.begin() as conn:
                res = conn.execute(
                    text(
                        "SELECT login_code FROM logins WHERE email = :email AND used < 2 "
                        "ORDER BY time DESC LIMIT 1"
                    ),
                    {"email": email},
                ).fetchone()

                # correct code
                if res and str(res[0]).strip() == code:
                    conn.execute(
                        text("UPDATE logins SET used = 1 WHERE email = :email AND login_code = :c"),
                        {"email": email, "c": code},
                    )

                    sid = session.get("temp_sid")
                    name_res = conn.execute(
                        text("SELECT `Name` FROM `login vs id` WHERE `Student ID` = :sid LIMIT 1"),
                        {"sid": sid},
                    ).fetchone()

                    session.clear()
                    session["student_id"] = sid
                    session["student_name"] = str(name_res[0]) if name_res and name_res[0] else "Student"
                    session["is_guest"] = False
                    session["is_power_user"] = str(sid).startswith("9")
                    session["last_active"] = datetime.datetime.now().timestamp()
                    session.permanent = True
                    return redirect(url_for("planner_page"))

                # wrong code
                attempts = session.get("attempts", 0) + 1
                session["attempts"] = attempts

                if attempts >= 3:
                    conn.execute(text("UPDATE logins SET used = 2 WHERE email = :email AND used < 2"), {"email": email})
                    alert_html = """
                        <div style="font-family: sans-serif; padding: 20px; border: 1px solid #ffcccc; background-color: #fff5f5;">
                            <h2 style="color: #d9534f;">Security Alert - MIAE Planner</h2>
                            <p>Someone attempted to access your account and entered the wrong access code 3 times.</p>
                            <p>For your security, the last generated access code has been permanently invalidated.</p>
                        </div>
                    """
                    send_email(to=email, subject="Security Alert: Multiple Failed Login Attempts", content=alert_html, is_html=True)
                    session.clear()
                    return render_template(
                        "login.html",
                        error="Too many failed attempts. Code has been invalidated. A security alert was sent to your email.",
                    )

                return render_template("verify.html", email=email, error=f"Invalid code. Attempt {attempts}/3.")

        except Exception as e:
            print(f"❌ DB Error Verify: {e}")
            return render_template("verify.html", email=email, error="Verification error.")

    return render_template("verify.html", email=email)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================================================
# PLANNER PAGE
# =========================================================

@app.route("/")
@app.route("/planner")
def planner_page():
    if "student_id" not in session:
        return redirect(url_for("login"))

    cur_sid = _current_sid()
    is_guest = session.get("is_guest", False)
    is_power_user = _is_power_user()
    viewing_sid = _viewing_sid()

    # Build static data from Excel
    df_courses = load_data()
    courses_db = []
    all_programs, ugrd_programs, grad_programs = [], [], []
    if not df_courses.empty and "PROGRAM" in df_courses.columns:
        courses_db = df_courses.to_dict(orient="records")
        raw_programs = list(df_courses["PROGRAM"].unique())
        all_programs = sorted([str(p).strip() for p in raw_programs if str(p).strip()])
        ugrd_programs = [p for p in all_programs if "GRAD" not in p.upper()]
        grad_programs = [p for p in all_programs if "GRAD" in p.upper()]

    sequences_db = load_sequences()
    restrictions_db = load_restrictions()
    programs_requirements_db = load_programs_requirements()

    # Load GPA thresholds from DB table Program_names
    program_names_db = []
    try:
        with engine.connect() as conn:
            pn_df = pd.read_sql(text("SELECT Program, Credits_FT, GPA_2_terms FROM Program_names"), conn)
            program_names_db = pn_df.fillna("").to_dict(orient="records")
    except Exception as e:
        print(f"⚠️ Program_names load error: {e}")

    # Determine which SID to load transcript/coop data for
    target_sid = viewing_sid

    # Resolve displayed name (for header)
    viewing_name = session.get("student_name", "Student")
    if is_power_user and target_sid != cur_sid:
        nm = _get_student_name_db(target_sid)
        viewing_name = nm or ""

    # Student email for header display
    student_email = _get_student_email_db(target_sid) if not is_guest else ""
    # Admin's own email (for notes double-click)
    admin_email = _get_student_email_db(cur_sid) if is_power_user else ""

    # Load a specific saved sequence if ?load_seq_id= is provided
    load_seq_id = request.args.get("load_seq_id", "").strip()
    initial_plan = None
    initial_plan_id = None
    if load_seq_id:
        try:
            with engine.connect() as conn:
                r = conn.execute(
                    text(
                        """
                        SELECT JSON_Data, Term_Json_data, status, cos_reason, student_comments
                        FROM Saved_Sequences
                        WHERE student_id = :sid AND Date_Saved = :ts
                        LIMIT 1
                        """
                    ),
                    {"sid": target_sid, "ts": load_seq_id},
                ).fetchone()
                if r:
                    plan_obj = _safe_json_load(r[0]) or {}
                    plan_obj["reason_code"] = int(r[3] or 0)
                    plan_obj["justification"] = str(r[4] or "")
                    initial_plan = json.dumps(plan_obj)
                    initial_plan_id = json.dumps(load_seq_id)
        except Exception as e:
            print(f"❌ Load seq_id error: {e}")

    try:
        with engine.connect() as conn:
            ts_df = pd.read_sql(
                text("SELECT COURSE, `Academic Term`, CREDVAL, GRADE, PROG_LINK, DISCIPLINE1_DESCR FROM Transcripts WHERE `Student ID` = :sid"),
                conn,
                params={"sid": target_sid},
            )
            coop_df = pd.read_sql(
                text("SELECT Term, `Term number Sx or Wx`, `Term Details`, WS, `Jobs View No`, `Jobs Applied No` FROM coop WHERE `Student ID` = :sid"),
                conn,
                params={"sid": target_sid},
            )

        # utils.py does transcript parsing + program detection
        is_grad, student_courses, detected_program, coop_terms = process_student_data(ts_df, coop_df)
        cgpa_history = calculate_cgpa(ts_df)
        
        # Get DISCIPLINE1_DESCR from latest term (first when ordered desc)
        discipline_descr = ""
        if not ts_df.empty and 'DISCIPLINE1_DESCR' in ts_df.columns:
            # Sort by Academic Term descending to get latest
            ts_sorted = ts_df.sort_values('Academic Term', ascending=False)
            latest_discipline = ts_sorted['DISCIPLINE1_DESCR'].dropna().iloc[0] if not ts_sorted['DISCIPLINE1_DESCR'].dropna().empty else ""
            discipline_descr = str(latest_discipline).strip()

        return render_template(
            "planner.html",
            student_id=cur_sid,
            student_name=session.get("student_name", "Student"),
            viewing_sid=viewing_sid,
            viewing_name=viewing_name,
            is_power_user=is_power_user,
            is_guest=is_guest,
            is_grad=is_grad,
            detected_program=detected_program,
            discipline_descr=discipline_descr,
            ugrd_programs=json.dumps(ugrd_programs),
            grad_programs=json.dumps(grad_programs),
            all_programs=json.dumps(all_programs),
            courses_db=json.dumps(courses_db),
            student_courses=json.dumps(student_courses),
            coop_terms=json.dumps(coop_terms),
            cgpa_history=json.dumps(cgpa_history),
            sequences_db=json.dumps(sequences_db),
            restrictions_db=json.dumps(restrictions_db),
            programs_requirements_db=json.dumps(programs_requirements_db),
            program_names_db=json.dumps(program_names_db),
            student_email=student_email,
            admin_email=admin_email,
            initial_plan=initial_plan,
            initial_plan_id=initial_plan_id,
            is_debug=(debug_no_emails == "DEBUG"),
        )

    except Exception as e:
        print(f"❌ DB Error Planner: {e}")
        return f"Database error: {e}", 500


# =========================================================
# API: ADMIN VIEW SWITCH
# =========================================================

@app.route("/admin_change_sid", methods=["POST"])
def admin_change_sid():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    new_sid = str(data.get("target_sid", "")).strip()
    if not new_sid:
        return jsonify({"ok": False, "error": "Missing target_sid"}), 400

    session["admin_view_sid"] = new_sid
    return jsonify({"ok": True})


@app.route("/admin_checks")
def admin_checks_page():
    """Admin checks page - only accessible to power users"""
    if not _require_login():
        return redirect("/login")
    if not _is_power_user():
        return "Unauthorized", 403
    
    # Load checks data from ADMIN_checks table
    checks = []
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT idADMIN_checks, What, message, short_message FROM ADMIN_checks")).fetchall()
            for r in res:
                checks.append({
                    "id": r[0],
                    "what": r[1] if r[1] else "",
                    "msg": r[2] if r[2] else "",
                    "short": r[3] if r[3] else ""
                })
    except Exception as e:
        print(f"❌ Error loading ADMIN_checks: {e}")
    
    return render_template("admin_checks.html", checks=checks)


@app.route("/api/admin/view_sid", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_admin_view_sid():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    target = str(data.get("student_id") or data.get("target_sid") or "").strip()
    if not target:
        return jsonify({"ok": False, "error": "Missing target_sid"}), 400
    session["admin_view_sid"] = target
    return jsonify({"ok": True})


@app.route("/api/admin/reset_view", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_admin_reset_view():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    session["admin_view_sid"] = _current_sid()
    return jsonify({"ok": True})


# =========================================================
# API: COMMENTS (public/private)
# =========================================================

@app.route("/api/comments", methods=["GET", "POST"])
@limiter.limit("100 per 15 minutes")
def api_comments():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    is_admin = _is_power_user()
    target_sid = _viewing_sid() if is_admin else _current_sid()

    if request.method == "GET":
        try:
            with engine.connect() as conn:
                r = conn.execute(
                    text("SELECT Public_comments, PRIVATE_comments FROM S_id_comments WHERE S_id = :sid LIMIT 1"),
                    {"sid": target_sid},
                ).fetchone()

            pub = str(r[0]).strip() if (r and r[0] and str(r[0]).lower() != "none") else ""
            priv = str(r[1]).strip() if (r and r[1] and str(r[1]).lower() != "none") else ""
            return jsonify({"ok": True, "public_comment": pub, "private_comment": priv if is_admin else ""})
        except Exception as e:
            print(f"❌ Get comments error: {e}")
            return jsonify({"ok": False, "error": "An error occurred"}), 500

    if not is_admin:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    pub = str(data.get("public_comment", "") or "")
    priv = str(data.get("private_comment", "") or "")

    try:
        with engine.begin() as conn:
            chk = conn.execute(text("SELECT 1 FROM S_id_comments WHERE S_id = :sid"), {"sid": target_sid}).fetchone()
            if chk:
                conn.execute(
                    text(
                        "UPDATE S_id_comments SET Public_comments=:pub, PRIVATE_comments=:priv WHERE S_id=:sid"
                    ),
                    {"sid": target_sid, "pub": pub, "priv": priv},
                )
            else:
                conn.execute(
                    text(
                        "INSERT INTO S_id_comments (S_id, Public_comments, PRIVATE_comments) VALUES (:sid, :pub, :priv)"
                    ),
                    {"sid": target_sid, "pub": pub, "priv": priv},
                )
        return jsonify({"ok": True})
    except Exception as e:
        print(f"❌ Save comments error: {e}")
        return jsonify({"ok": False, "error": "An error occurred"}), 500


@app.route("/api/comments/append", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_comments_append():
    """Any authenticated student can prepend their own text to public notes (used on submission)."""
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    is_admin = _is_power_user()
    target_sid = _viewing_sid() if is_admin else _current_sid()

    data = request.get_json(silent=True) or {}
    new_text = str(data.get("text", "") or "").strip()
    if not new_text:
        return jsonify({"ok": False, "error": "Empty text"}), 400

    try:
        with engine.begin() as conn:
            r = conn.execute(
                text("SELECT Public_comments, PRIVATE_comments FROM S_id_comments WHERE S_id = :sid LIMIT 1"),
                {"sid": target_sid},
            ).fetchone()
            priv = str(r[1]).strip() if (r and r[1] and str(r[1]).lower() != "none") else "" if r else ""

            if r:
                conn.execute(
                    text("UPDATE S_id_comments SET Public_comments=:pub WHERE S_id=:sid"),
                    {"sid": target_sid, "pub": new_text},
                )
            else:
                conn.execute(
                    text("INSERT INTO S_id_comments (S_id, Public_comments, PRIVATE_comments) VALUES (:sid, :pub, :priv)"),
                    {"sid": target_sid, "pub": new_text, "priv": priv},
                )
        return jsonify({"ok": True})
    except Exception as e:
        print(f"❌ Append comments error: {e}")
        return jsonify({"ok": False, "error": "An error occurred"}), 500


# =========================================================
# API: SAVE / LIST / GET SEQUENCES
# Table expected: Saved_Sequences
# NOTE: No CREATE/ALTER here (DB user may not have permission).
# =========================================================

@app.route("/api/sequence/save", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_sequence_save():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    
    # JSON validation - check for required fields
    required_fields = ["plan", "term_summary"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({"ok": False, "error": f"Missing required fields: {', '.join(missing)}"}), 400
    
    is_admin = _is_power_user()
    cur_sid = _current_sid()
    viewing_sid = _viewing_sid()

    target_sid = str(data.get("student_id") or viewing_sid).strip()

    if (not is_admin) and target_sid != cur_sid:
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    if is_admin and target_sid not in (cur_sid, viewing_sid):
        return jsonify({"ok": False, "error": "Admin must switch view first"}), 400

    plan = data.get("plan") or {}
    issues = data.get("issues") or []
    term_summary = data.get("term_summary") or []
    reason_code = int(data.get("reason_code") or data.get("cos_reason") or 0)
    justification = str(data.get("justification") or "")

    status_in = str(data.get("status") or "DRAFT").strip().upper()
    if status_in == "DRAFT":
        status_db = STATUS_SAVED_DRAFT
    elif status_in in ("PENDING_APPROVAL", STATUS_PENDING_APPROVAL):
        status_db = STATUS_PENDING_APPROVAL
    else:
        status_db = status_in

    program = str(data.get("program") or plan.get("program") or "").strip()
    name = str(data.get("name") or "").strip()
    if not name:
        name = f"Submitted on {datetime.datetime.now().strftime('%Y-%m-%d')}" if status_db == STATUS_PENDING_APPROVAL else "Draft"

    # Email + name to store
    email_to_save = session.get("pre_auth_email") or session.get("user_email") or ""
    sid_name = session.get("student_name", "") or ""

    if is_admin and target_sid != cur_sid:
        e = _get_student_email_db(target_sid)
        if e:
            email_to_save = e
        nm = _get_student_name_db(target_sid)
        if nm:
            sid_name = nm

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO Saved_Sequences
                        (Student_Email, Sequence_Name, Program, JSON_Data, Date_Saved, Term_Json_data, sequence_Json_data,
                         status, student_comments, student_id, student_id_name, cos_reason)
                    VALUES
                        (:em, :name, :prog, :jdata, :ds, :tdata, :sdata, :stat, :comm, :sid, :sidname, :cosr)
                    """
                ),
                {
                    "em": email_to_save,
                    "name": name,
                    "prog": program,
                    "jdata": json.dumps(plan),
                    "ds": ts,
                    "tdata": json.dumps(issues),
                    "sdata": json.dumps({"planner_plan": plan}),
                    "stat": status_db,
                    "comm": justification,
                    "sid": target_sid,
                    "sidname": sid_name,
                    "cosr": reason_code,
                },
            )

        
        
        # Send notification email when submitting for approval
        if status_db == STATUS_PENDING_APPROVAL:
            try:
                student_email_addr = email_to_save or _get_student_email_db(target_sid)
                student_display_name = sid_name or _get_student_name_db(target_sid) or target_sid

                terms_html = build_terms_html(term_summary, include_grades=False)

                subject_line = f"Sequence submitted for approval - {student_display_name} ({target_sid}) - {program}"
                html_body = render_sequence_email(
                    mode="PENDING",
                    student_email=student_email_addr,
                    student_name=student_display_name,
                    target_sid=target_sid,
                    program=program,
                    terms_html=terms_html,
                )

                # Send to admin BCC, student gets a copy
                submitter_email = student_email_addr or ""
                priority1_email = _get_priority1_email_db(target_sid)

                recipients = get_email_recipients(
                    program=program,
                    target_sid=target_sid,
                    submitter_email=submitter_email,
                    priority1_email=priority1_email,
                    action_type="SUBMIT",
                    wts_changed=True,
                )

                send_email(
                    to=recipients["to"],
                    cc=recipients["cc"],
                    bcc=recipients["bcc"],
                    subject=subject_line,
                    content=html_body,
                    reply_to="coop_miae@concordia.ca",
                    is_html=True,
                )
            except Exception as em_err:
                print(f"❌ Submit email error: {em_err}")

        return jsonify({"ok": True, "sequence_id": ts})

    except Exception as e:
        print(f"❌ Save sequence error: {e}")
        return jsonify({"ok": False, "error": "An error occurred"}), 500


@app.route("/api/sequence/list", methods=["GET"])
@limiter.limit("100 per 15 minutes")
def api_sequence_list():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized", "sequences": []}), 401

    is_admin = _is_power_user()
    target_sid = _viewing_sid() if is_admin else _current_sid()

    try:
        rows = []
        with engine.connect() as conn:
            q = text(
                """
                SELECT Date_Saved, status, Sequence_Name, Program, cos_reason, student_comments
                FROM Saved_Sequences
                WHERE student_id = :sid
                ORDER BY Date_Saved DESC
                LIMIT 200
                """
            )
            for r in conn.execute(q, {"sid": target_sid}):
                ts = str(r[0])
                rows.append(
                    {
                        "id": ts,
                        "updated_at": ts,
                        "status": str(r[1] or ""),
                        "name": str(r[2] or ""),
                        "program": str(r[3] or ""),
                        "reason_code": int(r[4] or 0),
                        "justification": str(r[5] or ""),
                    }
                )
        return jsonify({"ok": True, "sequences": rows})
    except Exception as e:
        print(f"❌ List sequences error: {e}")
        return jsonify({"ok": False, "error": "An error occurred", "sequences": []}), 500


@app.route("/api/sequence/get/<path:seq_id>", methods=["GET"])
@limiter.limit("100 per 15 minutes")
def api_sequence_get(seq_id):
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    is_admin = _is_power_user()
    target_sid = _viewing_sid() if is_admin else _current_sid()

    ts = str(seq_id).strip()

    try:
        with engine.connect() as conn:
            r = conn.execute(
                text(
                    """
                    SELECT JSON_Data, Term_Json_data, status, cos_reason, student_comments
                    FROM Saved_Sequences
                    WHERE student_id = :sid AND Date_Saved = :ts
                    LIMIT 1
                    """
                ),
                {"sid": target_sid, "ts": ts},
            ).fetchone()

        if not r:
            return jsonify({"ok": False, "error": "Not found"}), 404

        plan = _safe_json_load(r[0]) or {}
        issues = _safe_json_load(r[1]) or []

        return jsonify(
            {
                "ok": True,
                "plan": plan,
                "issues": issues,
                "status": str(r[2] or ""),
                "reason_code": int(r[3] or 0),
                "justification": str(r[4] or ""),
            }
        )

    except Exception as e:
        print(f"❌ Get sequence error: {e}")
        return jsonify({"ok": False, "error": "An error occurred"}), 500


# =========================================================
# API: PENDING APPROVALS (admin)
# =========================================================

@app.route("/api/admin/pending", methods=["GET"])
@app.route("/api/pending_approvals", methods=["GET"])
@limiter.limit("100 per 15 minutes")
def api_admin_pending():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized", "pending": []}), 401
    if not _is_power_user():
        return jsonify({"ok": True, "pending": []})

    out = []
    try:
        with engine.connect() as conn:
            q = text(
                """
                SELECT student_id, student_id_name, Student_Email, Sequence_Name, Program,
                       Date_Saved, status, student_comments, cos_reason, JSON_Data
                FROM Saved_Sequences
                WHERE status = :status
                ORDER BY Date_Saved DESC
                """
            )
            for r in conn.execute(q, {"status": STATUS_PENDING_APPROVAL}):
                ts = str(r[5])
                out.append(
                    {
                        "id": ts,
                        "student_id": str(r[0] or "").strip(),
                        "student_name": str(r[1] or "").strip(),
                        "email": str(r[2] or "").strip(),
                        "name": str(r[3] or "").strip(),
                        "program": str(r[4] or "").strip(),
                        "updated_at": ts,
                        "status": str(r[6] or "").strip(),
                        "justification": str(r[7] or ""),
                        "reason_code": int(r[8] or 0),
                        "plan": _safe_json_load(r[9]) or {},
                    }
                )
        return jsonify({"ok": True, "pending": out})
    except Exception as e:
        print(f"❌ Pending approvals error: {e}")
        return jsonify({"ok": False, "error": "An error occurred", "pending": []}), 500


@app.route("/api/admin/send_student_email", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_admin_send_student_email():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    
    try:
        data = request.get_json(silent=True) or {}
        student_id = data.get("student_id")
        student_name = data.get("student_name")
        student_email = data.get("student_email")
        program = data.get("program")
        message = data.get("message")
        include_institute = data.get("include_institute", False)
        cc_list = data.get("cc_list", [])
        
        if not student_email or not message:
            return jsonify({"ok": False, "error": "Missing required fields"}), 400
        
        # Build email subject and body
        subject = f"MIAE CO-OP AD message for {student_name}, {student_id}"
        header_msg = "⚠️ WT IMPACTED - Operations Institute are cc-ed\n\n" if include_institute else "✅ Institute Operations not cc-ed - no restrictions on WT\n\n"
        admin_email = session.get("user_email", "")
        
        body = f"""{header_msg}Hello {student_name},

Please see the message below:

{message}

PS: Please use REPLY TO ALL

Regards,
{admin_email}"""
        
        # Send email
        send_email(
            to=[student_email],
            cc=cc_list,
            subject=subject,
            content=body,
            is_html=False
        )
        
        return jsonify({"ok": True, "message": "Email sent successfully"})
        
    except Exception as e:
        print(f"❌ Error sending student email: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/admin/search_students", methods=["GET"])
@limiter.limit("100 per 15 minutes")
def api_admin_search_students():
    """Search students by ID or name (min 4 characters)"""
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    
    try:
        query = request.args.get("q", "").strip()
        
        # Require minimum 4 characters for security
        if len(query) < 4:
            return jsonify({"ok": True, "results": []})
        
        # Search in database
        with engine.connect() as conn:
            # Search by Student ID or Name (first/last)
            sql = text("""
                SELECT `Student ID`, `Name`, `Email`
                FROM `login vs id`
                WHERE `Student ID` LIKE :query
                   OR `Name` LIKE :query
                ORDER BY `Student ID`
                LIMIT 10
            """)
            
            search_pattern = f"%{query}%"
            rows = conn.execute(sql, {"query": search_pattern}).fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "id": str(row[0]).strip() if row[0] else "",
                    "name": str(row[1]).strip() if row[1] else "",
                    "email": str(row[2]).strip() if row[2] else ""
                })
            
            return jsonify({"ok": True, "results": results})
            
    except Exception as e:
        print(f"❌ Error searching students: {e}")
        return jsonify({"ok": False, "error": "Search failed"}), 500


@app.route("/api/admin_run_check", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_admin_run_check():
    """Run admin check query and return matching students"""
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    
    try:
        data = request.get_json(silent=True) or {}
        check_id = data.get("check_id")
        
        if not check_id:
            return jsonify([])
        
        # Map check_id to view name
        view_mapping = {
            "1": "v_check_1_cgpa_low",
            "2": "v_check_2_gpa24_low",
            "3": "v_check_3_gpa24_borderline",
            "5": "v_check_5_wt_violation",
            "6": "v_check_6_no_sequence",
            "7": "v_check_7_sequence_deviations"
        }
        
        view_name = view_mapping.get(str(check_id))
        
        if not view_name:
            return jsonify([])
        
        # Query the view
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM {view_name}"))
            
            # Get column names from the result
            column_names = list(result.keys())
            
            rows = result.fetchall()
            
            if not rows:
                return jsonify([])
            
            # Extract all student IDs from the view results
            student_ids = []
            for row in rows:
                row_dict = dict(zip(column_names, row))
                student_id = row_dict.get('Student ID') or row_dict.get('StudentID') or row_dict.get('student_id') or ""
                if student_id:
                    student_ids.append(str(student_id).strip())
            
            # Batch query 1: Get all names at once
            names_map = {}
            if student_ids:
                placeholders = ','.join([f':sid{i}' for i in range(len(student_ids))])
                params = {f'sid{i}': sid for i, sid in enumerate(student_ids)}
                names_result = conn.execute(
                    text(f"SELECT `Student ID`, `Name` FROM `login vs id` WHERE `Student ID` IN ({placeholders})"),
                    params
                ).fetchall()
                for name_row in names_result:
                    names_map[str(name_row[0]).strip()] = str(name_row[1]).strip() if name_row[1] else ""
            
            # Batch query 2: Get all notes at once
            notes_map = {}
            if student_ids:
                placeholders = ','.join([f':sid{i}' for i in range(len(student_ids))])
                params = {f'sid{i}': sid for i, sid in enumerate(student_ids)}
                notes_result = conn.execute(
                    text(f"SELECT S_id, Public_comments, PRIVATE_comments FROM S_id_comments WHERE S_id IN ({placeholders})"),
                    params
                ).fetchall()
                for notes_row in notes_result:
                    sid = str(notes_row[0]).strip()
                    notes_map[sid] = {
                        'visible': str(notes_row[1]).strip() if notes_row[1] else "",
                        'invisible': str(notes_row[2]).strip() if notes_row[2] else ""
                    }
            
            # Batch query 3: Get scheduled WTs from coop table
            wts_map = {}
            if student_ids:
                from datetime import datetime
                current_year = datetime.now().year
                current_month = datetime.now().month
                
                # Determine current academic year and season (same logic as planner yellow term)
                if current_month >= 9:  # Sep-Dec: Fall of current academic year
                    current_academic_year = current_year
                    current_season = 'Fall'
                elif current_month >= 5:  # May-Aug: Summer of previous academic year
                    current_academic_year = current_year - 1
                    current_season = 'Summer'
                else:  # Jan-Apr: Winter of previous academic year
                    current_academic_year = current_year - 1
                    current_season = 'Winter'
                
                # Calculate current term sort key
                current_sort_key = current_academic_year * 3 + {'Summer': 1, 'Fall': 2, 'Winter': 3}.get(current_season, 0)
                
                placeholders = ','.join([f':sid{i}' for i in range(len(student_ids))])
                params = {f'sid{i}': sid for i, sid in enumerate(student_ids)}
                
                # Get all coop terms for these students
                coop_result = conn.execute(
                    text(f"SELECT `Student ID`, `Term`, `Term number Sx or Wx` FROM `coop` WHERE `Student ID` IN ({placeholders})"),
                    params
                ).fetchall()
                
                for coop_row in coop_result:
                    sid = str(coop_row[0]).strip()
                    term_raw = str(coop_row[1]).strip() if coop_row[1] else ""
                    term_type = str(coop_row[2]).strip() if coop_row[2] else ""
                    
                    # Only include W-x terms (work terms)
                    if not term_type or not term_type.upper().startswith('W-'):
                        continue
                    
                    # Use parse_term from utils.py to normalize the term (same as when loading coop for a student)
                    year_range, season = parse_term(term_raw)
                    
                    # Skip if parsing failed
                    if year_range == "UNKNOWN" or season == "UNKNOWN":
                        continue
                    
                    try:
                        term_start_year = int(year_range.split('-')[0])
                    except:
                        continue
                    
                    # Determine display year based on season
                    # Summer/Fall: use first year (e.g., 2026-2027 Summer → 2026 Summer)
                    # Winter: use second year (e.g., 2025-2026 Winter → 2026 Winter)
                    if season == 'Winter':
                        display_year = term_start_year + 1
                    else:
                        display_year = term_start_year
                    
                    # Create sort key using same logic as planner.js getTermOrdFromZoneId
                    # year * 3 + season_order (Summer=1, Fall=2, Winter=3)
                    season_order = {'Summer': 1, 'Fall': 2, 'Winter': 3}[season]
                    term_sort_key = term_start_year * 3 + season_order
                    
                    # Only include future terms (after current yellow term)
                    if term_sort_key > current_sort_key:
                        if sid not in wts_map:
                            wts_map[sid] = []
                        wts_map[sid].append({
                            'label': f"{display_year} {season}",
                            'sort_key': term_sort_key
                        })
                
                # Sort and format WTs for each student (one per line with <br>)
                for sid in wts_map:
                    wts_map[sid] = sorted(wts_map[sid], key=lambda x: x['sort_key'])
                    wts_map[sid] = "<br>".join([wt['label'] for wt in wts_map[sid]])
            
            # Format results for frontend - map by column name
            students = []
            for row in rows:
                row_dict = dict(zip(column_names, row))
                
                # Map columns to expected format (handle different column names)
                student_id = row_dict.get('Student ID') or row_dict.get('StudentID') or row_dict.get('student_id') or ""
                student_id = str(student_id).strip()
                
                # Get name from the batch query results
                name = names_map.get(student_id, "")
                
                email = row_dict.get('Primary Email') or row_dict.get('Email') or row_dict.get('email') or ""
                program = row_dict.get('PROG_LINK') or row_dict.get('Program') or row_dict.get('program') or ""
                
                # Get notes from the batch query results
                notes = notes_map.get(student_id, {'visible': '', 'invisible': ''})
                notes_vis = notes['visible']
                notes_invis = notes['invisible']
                
                # Get scheduled WTs from the batch query results
                scheduled_wts = wts_map.get(student_id, "")
                
                # Get deviated courses if present (for check 7)
                deviated_courses = row_dict.get('Deviated_Courses') or row_dict.get('Deviated Courses') or ""
                deviated_courses = str(deviated_courses).strip() if deviated_courses else ""
                
                students.append({
                    "id": student_id,
                    "name": name,
                    "program": str(program).strip(),
                    "email": str(email).strip(),
                    "cgpa": str(row_dict.get('CGPA') or row_dict.get('GPA_X_CR') or "").strip(),
                    "cgpa_cr": str(row_dict.get('CGPA_Total_Credits') or row_dict.get('GPA_X_CR_Actual_Credits') or "").strip(),
                    "gpa24": str(row_dict.get('GPA24') or row_dict.get('GPA_X_CR') or "").strip(),
                    "gpa24_cr": str(row_dict.get('GPA24_Credits') or row_dict.get('GPA_X_CR_Actual_Credits') or "").strip(),
                    "wts": scheduled_wts,
                    "deviated_courses": deviated_courses,
                    "notes_vis": notes_vis,
                    "notes_invis": notes_invis
                })
            
            return jsonify(students)
            
    except Exception as e:
        print(f"❌ Error running admin check: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 500  # Return empty array on error


@app.route("/api/admin_bulk_email", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_admin_bulk_email():
    """Send bulk emails to selected students"""
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403
    
    try:
        data = request.get_json(silent=True) or {}
        student_ids = data.get("student_ids", [])
        message = data.get("message", "")
        short_msg = data.get("short_msg", "")
        subject = data.get("subject", "")
        include_institute = data.get("include_institute", False)
        
        if not student_ids or not message:
            return jsonify({"ok": False, "error": "Missing required fields"}), 400
        
        admin_email = session.get("user_email", "")
        
        # Process each student
        with engine.connect() as conn:
            for sid in student_ids:
                # Get student info
                student_row = conn.execute(
                    text("SELECT `Name`, `Email`, `Program` FROM `login vs id` WHERE `Student ID` = :sid"),
                    {"sid": sid}
                ).fetchone()
                
                if not student_row:
                    continue
                
                student_name = str(student_row[0]).strip() if student_row[0] else ""
                student_email = str(student_row[1]).strip() if student_row[1] else ""
                program = str(student_row[2]).strip() if student_row[2] else ""
                
                # Determine coordinator
                coord_email = 'frederick.francis@concordia.ca'
                if program and 'INDU' in program.upper():
                    try:
                        last_digit = int(str(sid)[-1])
                        if last_digit >= 5:
                            coord_email = 'nathalie.steverman@concordia.ca'
                    except:
                        pass
                
                # Build CC list
                cc_list = ['coop_miae@concordia.ca', 'sabrina.poirier@concordia.ca', coord_email]
                if include_institute:
                    cc_list.append('instituteoperations@concordia.ca')
                cc_list = list(set(cc_list))  # Remove duplicates
                
                # Build email body
                header_msg = "⚠️ WT IMPACTED - Operations Institute are cc-ed\n\n" if include_institute else "✅ Institute Operations not cc-ed - no restrictions on WT\n\n"
                body = f"""{header_msg}Hello {student_name},

{message}

PS: Please use REPLY TO ALL

Regards,
{admin_email}"""
                
                # Send email
                send_email(
                    to=[student_email],
                    cc=cc_list,
                    subject=subject,
                    content=body,
                    is_html=False
                )
                
                # Save short message to database if provided
                if short_msg:
                    # Update S_id_comments table
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    comment_text = f"[{now}, {admin_email}]: {short_msg}"
                    
                    # Check if record exists
                    existing = conn.execute(
                        text("SELECT public_notes FROM S_id_comments WHERE S_id = :sid"),
                        {"sid": sid}
                    ).fetchone()
                    
                    if existing:
                        # Append to existing notes
                        old_notes = str(existing[0]) if existing[0] else ""
                        new_notes = comment_text + "\n\n" + old_notes if old_notes else comment_text
                        conn.execute(
                            text("UPDATE S_id_comments SET public_notes = :notes WHERE S_id = :sid"),
                            {"notes": new_notes, "sid": sid}
                        )
                    else:
                        # Insert new record
                        conn.execute(
                            text("INSERT INTO S_id_comments (S_id, public_notes) VALUES (:sid, :notes)"),
                            {"sid": sid, "notes": comment_text}
                        )
                    conn.commit()
        
        return jsonify({"ok": True, "message": "Emails sent successfully"})
        
    except Exception as e:
        print(f"❌ Error sending bulk emails: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/admin/approve", methods=["POST"])
@limiter.limit("100 per 15 minutes")
def api_admin_approve():
    if not _require_login():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    if not _is_power_user():
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()  # APPROVED or REWORK
    target_sid = str(data.get("student_id") or _viewing_sid()).strip()
    timestamp = str(data.get("timestamp", "")).strip()
    pub_comment = str(data.get("public_comments", "") or "")
    priv_comment = str(data.get("private_comments", "") or "")
    student_name = str(data.get("student_name", "Student"))
    program = str(data.get("program", ""))
    wt_summary = data.get("wt_summary") or {}
    term_summary = data.get("term_summary") or []
    justification = str(data.get("justification", "") or "")

    if status not in (STATUS_APPROVED, STATUS_REWORK):
        return jsonify({"ok": False, "error": "Invalid status"}), 400

    try:
        # 1. Update comments
        with engine.begin() as conn:
            chk = conn.execute(text("SELECT 1 FROM S_id_comments WHERE S_id = :sid"), {"sid": target_sid}).fetchone()
            if chk:
                conn.execute(
                    text("UPDATE S_id_comments SET Public_comments=:pub, PRIVATE_comments=:priv WHERE S_id=:sid"),
                    {"sid": target_sid, "pub": pub_comment, "priv": priv_comment},
                )
            else:
                conn.execute(
                    text("INSERT INTO S_id_comments (S_id, Public_comments, PRIVATE_comments) VALUES (:sid, :pub, :priv)"),
                    {"sid": target_sid, "pub": pub_comment, "priv": priv_comment},
                )

        # 2. Update sequence status
        with engine.begin() as conn:
            if status == STATUS_APPROVED:
                status_to_save = f"{STATUS_APPROVED} on {datetime.datetime.now().strftime('%Y-%m-%d')}"
                conn.execute(
                    text("UPDATE Saved_Sequences SET status = :stat WHERE student_id = :sid AND Date_Saved = :ts"),
                    {"stat": status_to_save, "sid": target_sid, "ts": timestamp},
                )
                # Mark other pending as IGNORED
                conn.execute(
                    text("UPDATE Saved_Sequences SET status = :ignored WHERE student_id = :sid AND status = :pending"),
                    {"ignored": STATUS_IGNORED, "sid": target_sid, "pending": STATUS_PENDING_APPROVAL},
                )
            else:
                conn.execute(
                    text("UPDATE Saved_Sequences SET status = :stat WHERE student_id = :sid AND Date_Saved = :ts"),
                    {"stat": status, "sid": target_sid, "ts": timestamp},
                )

        # 3. Save course deviations (only on APPROVED)
        if status == STATUS_APPROVED:
            course_deviations = data.get("course_deviations") or []
            if course_deviations:
                try:
                    with engine.begin() as conn:
                        # Delete existing records for this student
                        conn.execute(
                            text("DELETE FROM course_deviation WHERE student_id = :sid"),
                            {"sid": target_sid},
                        )
                        # Insert new deviation records
                        for dev in course_deviations:
                            course_num = str(dev.get("course", "")).strip()
                            orig_term = str(dev.get("original_term", "")).strip()
                            new_term = str(dev.get("new_term", "")).strip()
                            delta = int(dev.get("delta", 0))
                            if not course_num:
                                continue
                            conn.execute(
                                text(
                                    "INSERT INTO course_deviation "
                                    "(student_id, course, original_term, new_term, delta) "
                                    "VALUES (:sid, :course, :orig, :new, :delta)"
                                ),
                                {
                                    "sid": target_sid,
                                    "course": course_num,
                                    "orig": orig_term,
                                    "new": new_term,
                                    "delta": delta,
                                },
                            )
                except Exception as e:
                    print(f"⚠ course_deviation save error (non-fatal): {e}")

        # 4. Send email
        student_email = _get_student_email_db(target_sid)
        power_user_email = session.get("pre_auth_email") or session.get("user_email") or ""
        power_user_name = power_user_email.split("@")[0] if power_user_email else "Coordinator"

        val_errors = data.get("validation_errors") or []
        val_errors_html = "<ul style='margin:0;padding-left:20px;font-size:14px;'>"
        if not val_errors:
            val_errors_html += "<li style='color:#27ae60;font-weight:bold;'>✅ No validation errors.</li>"
        else:
            for err in val_errors:
                val_errors_html += f"<li style='margin-bottom:4px;'>{err}</li>"
        val_errors_html += "</ul>"

        def nl2html(txt, fallback=""):
            s = str(txt or "").strip()
            if not s:
                s = fallback
            return escape(s).replace("\n", "<br>")

        wt_html = ""
        wts_changed = False
        wt_status_msg = ""

        for wt in ["WT1", "WT2", "WT3"]:
            if wt in wt_summary:
                info = wt_summary[wt]
                ct = str(info.get("change_text", "") or "").strip()
                is_changed = bool(ct)

                if is_changed:
                    wts_changed = True

                wt_color = "#ff0000" if is_changed else "#f8071b"   # bright green if changed, normal green if no change
                wt_label = f"<span style='color:{wt_color};font-weight:800;'>{wt}</span>"
                term_txt = escape(str(info.get("new_term", "") or ""))

                change_span = (
                    f"<span style='color:#00c853;font-weight:800;'> — {escape(ct)}</span>"
                    if is_changed else
                    "<span style='color:#27ae60;font-weight:800;'> — NO CHANGE</span>"
                )

                wt_html += f"<p style='margin:6px 0;font-size:14px;line-height:1.5;'>{wt_label}: {term_txt}{change_span}</p>"

            terms_html = build_terms_html(term_summary, include_grades=False)
            comments_html = nl2html(pub_comment, "No comments.")
            wt_status_msg = (
                "<p style='color:#e67e22;font-weight:bold;'>⚠️ Work term placements were modified during approval.</p>"
                if wts_changed else
                "<p style='color:#27ae60;font-weight:bold;'>✅ Work term placements are unchanged.</p>"
            )

        if status == STATUS_APPROVED:
            # Fetch public_notes from DB to include in email
            notes_html = ""
            try:
                with engine.connect() as conn:
                    nr = conn.execute(
                        text("SELECT public_notes FROM S_id_comments WHERE S_id = :sid LIMIT 1"),
                        {"sid": target_sid},
                    ).fetchone()
                    if nr and nr[0] and str(nr[0]).strip():
                        notes_html = nl2html(str(nr[0]).strip())
            except Exception as ne:
                print(f"⚠ Could not fetch public_notes for email: {ne}")

            subject = f"Approved sequence for {student_name} {target_sid} {program}"
            html_body = render_sequence_email(
                mode="APPROVED",
                student_email=student_email,
                student_name=student_name,
                target_sid=target_sid,
                program=program,
                terms_html=terms_html,
                comments_html=comments_html,
                wt_html=wt_html,
                wt_status_msg=wt_status_msg,
                signer=power_user_name,
                notes_html=notes_html,
            )

            # Clear public_notes after approval
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE S_id_comments SET public_notes = NULL WHERE S_id = :sid"),
                        {"sid": target_sid},
                    )
            except Exception as ne:
                print(f"⚠ Could not clear public_notes after approval: {ne}")
        else:  # REWORK
            subject = f"REWORK for {student_name} ({target_sid}) - {program}"
            html_body = f"""
            <div style="font-family:Arial,sans-serif;color:#333;max-width:750px;margin:0 auto;border:1px solid #e0e0e0;padding:20px;border-radius:8px;">
                <h2 style="color:#c0392b;border-bottom:2px solid #e74c3c;padding-bottom:10px;">Action Required: Sequence Rework</h2>
                <p><b>Student:</b> {student_name} ({target_sid})</p>
                <p><b>Program:</b> {program}</p>
                <p>Please review the comments and update your sequence.</p>
                <p><b>Comments:</b></p>
                <div style="background:#fff8e1;border-left:4px solid #f39c12;padding:10px;line-height:1.6;">
                    {nl2html(pub_comment, "Please review.")}
                </div>
                <h3>System Check:</h3>
                
                <div style="text-align:center;margin:35px 0;">
                    <a href="https://concordia-sequence-planner.onrender.com/" style="background:#e74c3c;color:#fff;padding:14px 28px;text-decoration:none;border-radius:6px;font-weight:bold;">Log in to Update Sequence</a>
                </div>
                <p>Best Regards,<br><b>{power_user_name}</b></p>
            </div>
            """

        submitter_email = student_email or _get_student_email_db(target_sid)
        priority1_email = _get_priority1_email_db(target_sid)

        recipients = get_email_recipients(
            program=program,
            target_sid=target_sid,
            submitter_email=submitter_email,
            priority1_email=priority1_email,
            action_type=status,   # "APPROVED" sau "REWORK"
            wts_changed=wts_changed,
        )

        send_email(
            to=recipients["to"],
            cc=recipients["cc"],
            bcc=recipients["bcc"],
            subject=subject,
            content=html_body,
            reply_to="coop_miae@concordia.ca",
            is_html=True,
        )

        return jsonify({"ok": True})
    except Exception as e:
        print(f"❌ Approve route error: {e}")
        return jsonify({"ok": False, "error": "An error occurred"}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)

