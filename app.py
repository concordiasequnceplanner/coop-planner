import os
import random
import re
import json
import datetime
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pandas as pd
import resend
from sqlalchemy import create_engine, text
import pymysql

app = Flask(__name__)
app.secret_key = "SVsecretKEY"
resend.api_key = os.environ.get("RESEND_API_KEY")

#debug_no_emails = "DEBUG" # debug
debug_no_emails =  "SITE_ACTIVE" # then it works
debug_email="sorin.voiculescu@concordia.ca"

# =========================================================
# 1. CONFIGURARE BAZĂ DE DATE (MySQL GoDaddy)
# =========================================================
DB_USER = os.environ.get("planner_db_USER")
DB_PASS = os.environ.get("planner_db_password")
DB_HOST = os.environ.get("planner_db_HOST")
DB_NAME = os.environ.get("planner_db_NAME")

if DB_PASS:
    DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}"
    engine = create_engine(
    DATABASE_URI,
    pool_pre_ping=True,  
    pool_recycle=280,
    connect_args={'ssl': {}}  # <--- AICI e modificarea (dicționar SSL gol pentru a forța criptarea standard)
        )
    print("🟢 App connected to MySQL Database successfully.")
else:
    engine = None
    print("❌ WARNING: Environment variable planner_db_password not set!")

STANDARD_SEQUENCES = {
    "INDUSTRIAL": {
        "ACCO220": "Y1_FALL", "ENGR213": "Y1_FALL", "INDU211": "Y1_FALL", "MIAE211": "Y1_FALL", "ENGR245": "Y1_FALL",
        "ENCS282": "Y1_WIN", "ENGR201": "Y1_WIN", "MIAE215": "Y1_WIN", "MIAE221": "Y1_WIN", "MIAE313": "Y1_WIN",
        "ENGR202": "Y2_SUM1", "INDU323": "Y2_SUM1", "ENGR233": "Y2_SUM1", "ENGR251": "Y2_SUM1", "ENGR371": "Y2_SUM1",
        "INDU371": "Y2_FALL", "INDU372": "Y2_FALL", "MIAE380": "Y2_FALL", "MIAE311": "Y2_FALL", "MIAE312": "Y2_FALL", "ENGR301": "Y2_FALL",
        "WT1": "Y2_WIN",
        "INDU311": "Y3_SUM1", "ENGR311": "Y3_SUM1", "INDU320": "Y3_SUM1", "ENGR391": "Y3_SUM1", "ENGR392": "Y3_SUM1",
        "WT2": "Y3_FALL",
        "INDU324": "Y3_WIN", "INDU330": "Y3_WIN", "INDU412": "Y3_WIN", "INDU321": "Y3_WIN", "INDU421": "Y3_WIN",
        "WT3": "Y4_SUM1",
        "INDU342": "Y4_FALL", "INDU423": "Y4_FALL", "INDU490A": "Y4_FALL",
        "INDU490B": "Y4_WIN"
    },
    "MECHANICAL": {
        "ENCS282": "Y1_FALL", "ENGR213": "Y1_FALL", "ENGR242": "Y1_FALL", "MIAE211": "Y1_FALL", "MIAE215": "Y1_FALL",
        "ENGR233": "Y1_WIN", "ENGR243": "Y1_WIN", "ENGR244": "Y1_WIN", "MIAE313": "Y1_WIN", "MIAE221": "Y1_WIN",
        "ENGR201": "Y2_SUM1", "ENGR202": "Y2_SUM1", "ENGR251": "Y2_SUM1", "ENGR311": "Y2_SUM1", "MIAE311": "Y2_SUM1", "MIAE312": "Y2_SUM1",
        "MECH321": "Y2_FALL", "MECH343": "Y2_FALL", "MECH351": "Y2_FALL", "MIAE380": "Y2_FALL", "ENGR361": "Y2_FALL",
        "WT1": "Y2_WIN",
        "ENGR371": "Y3_SUM1", "MECH352": "Y3_SUM1", "MECH361": "Y3_SUM1", "ENGR391": "Y3_SUM1", "MECH390": "Y3_SUM1",
        "WT2": "Y3_FALL",
        "MECH371": "Y3_WIN", "MIAE383": "Y3_WIN", "MECH373": "Y3_WIN", "MECH375": "Y3_WIN", "ENGR392": "Y3_WIN",
        "WT3": "Y4_SUM1",
        "MECH368": "Y4_FALL", "ENGR301": "Y4_FALL", "MECH344": "Y4_FALL", "MECH490A": "Y4_FALL",
        "MECH490B": "Y4_WIN"
    },
    "AERO_A": {
        "ENCS282": "Y1_FALL", "ENGR213": "Y1_FALL", "ENGR242": "Y1_FALL", "MIAE215": "Y1_FALL", "AERO201": "Y1_FALL",
        "ENGR233": "Y1_WIN", "ENGR201": "Y1_WIN", "ENGR243": "Y1_WIN", "ENGR244": "Y1_WIN", "ENGR251": "Y1_WIN", "ENGR202": "Y1_WIN",
        "AERO290": "Y2_SUM1", "ENGR311": "Y2_SUM1", "ENGR361": "Y2_SUM1", "ENGR371": "Y2_SUM1", "MIAE211": "Y2_SUM1",
        "AERO371": "Y2_FALL", "MECH343": "Y2_FALL", "MECH352": "Y2_FALL", "MIAE221": "Y2_FALL",
        "WT1": "Y2_WIN",
        "ENGR301": "Y3_SUM1", "AERO390": "Y3_SUM1", "ENGR391": "Y3_SUM1", "AERO417": "Y3_SUM1", "ENGR392": "Y3_SUM1",
        "WT2": "Y3_FALL",
        "AERO481": "Y3_WIN", "MECH361": "Y3_WIN", "MECH351": "Y3_WIN", "MIAE383": "Y3_WIN",
        "WT3": "Y4_SUM1",
        "AERO462": "Y4_FALL", "AERO464": "Y4_FALL", "MECH461": "Y4_FALL", "AERO455": "Y4_FALL", "AERO490A": "Y4_FALL",
        "AERO465": "Y4_WIN", "AERO490B": "Y4_WIN"
    },
    "AERO_B": {
        "AERO201": "Y1_FALL", "ENCS282": "Y1_FALL", "ENGR213": "Y1_FALL", "ENGR242": "Y1_FALL", "MIAE215": "Y1_FALL",
        "AERO253": "Y1_WIN", "ENGR201": "Y1_WIN", "ENGR233": "Y1_WIN", "ENGR243": "Y1_WIN", "ENGR244": "Y1_WIN", "ENGR202": "Y1_WIN",
        "AERO290": "Y2_SUM1", "ENGR311": "Y2_SUM1", "ENGR361": "Y2_SUM1", "ENGR371": "Y2_SUM1", "MIAE211": "Y2_SUM1",
        "AERO371": "Y2_FALL", "MECH343": "Y2_FALL", "MIAE221": "Y2_FALL", "MIAE313": "Y2_FALL",
        "WT1": "Y2_WIN",
        "ENGR301": "Y3_SUM1", "AERO390": "Y3_SUM1", "ENGR391": "Y3_SUM1", "ENGR392": "Y3_SUM1", "MECH375": "Y3_SUM1",
        "WT2": "Y3_FALL",
        "AERO481": "Y3_WIN", "MECH373": "Y3_WIN", "MIAE311": "Y3_WIN", "MIAE312": "Y3_WIN", "MIAE383": "Y3_WIN",
        "WT3": "Y4_SUM1",
        "AERO431": "Y4_FALL", "AERO417": "Y4_FALL", "AERO486": "Y4_FALL", "MECH460": "Y4_FALL", "MECH412": "Y4_FALL", "AERO490A": "Y4_FALL",
        "AERO487": "Y4_WIN", "AERO490B": "Y4_WIN"
    },
    "AERO_C": {
        "AERO201": "Y1_FALL", "ENCS282": "Y1_FALL", "ENGR213": "Y1_FALL", "ENGR242": "Y1_FALL", "COEN243": "Y1_FALL",
        "ELEC273": "Y1_WIN", "ENGR233": "Y1_WIN", "ENGR243": "Y1_WIN", "ENGR244": "Y1_WIN", "ENGR201": "Y1_WIN",
        "COEN212": "Y2_SUM1", "COEN231": "Y2_SUM1", "ELEC242": "Y2_SUM1", "ENGR202": "Y2_SUM1", "ENGR361": "Y2_SUM1",
        "AERO290": "Y2_FALL", "AERO371": "Y2_FALL", "COEN244": "Y2_FALL", "ELEC342": "Y2_FALL", "AERO253": "Y2_FALL", "ENGR371": "Y2_FALL",
        "WT1": "Y2_WIN",
        "ENGR301": "Y3_SUM1", "AERO390": "Y3_SUM1", "ENGR391": "Y3_SUM1", "ENGR392": "Y3_SUM1", "COEN311": "Y3_SUM1",
        "WT2": "Y3_FALL",
        "COEN352": "Y3_WIN", "ELEC481": "Y3_WIN", "MIAE383": "Y3_WIN", "AERO482": "Y3_WIN",
        "WT3": "Y4_SUM1",
        "AERO417": "Y4_FALL", "ELEC483": "Y4_FALL", "SOEN341": "Y4_FALL", "AERO483": "Y4_FALL", "AERO490A": "Y4_FALL",
        "AERO490B": "Y4_WIN"
    }
}

def verify_email_in_sheets(email):
    try:
        with engine.connect() as conn:
            query = text("SELECT `Student ID` FROM `Sid_Email_Admission` WHERE LOWER(`Primary Email`) = :email LIMIT 1")
            result = conn.execute(query, {"email": email.strip().lower()}).fetchone()
            if result:
                return True, str(result[0]).strip()
    except Exception as e:
        print(f"DB Error verify_email: {e}")
    return False, ""

def get_student_email(target_sid, fallback_email="student@concordia.ca"):
    try:
        with engine.connect() as conn:
            query = text("SELECT `Primary Email` FROM `Sid_Email_Admission` WHERE `Student ID` = :sid ORDER BY `email_priority` ASC LIMIT 1")
            result = conn.execute(query, {"sid": str(target_sid).strip()}).fetchone()
            if result and result[0]:
                return str(result[0]).strip()
    except Exception as e:
        print(f"DB Error get_student_email: {e}")
    return fallback_email

def get_priority1_email(target_sid):
    try:
        with engine.connect() as conn:
            query = text("SELECT `Primary Email` FROM `Sid_Email_Admission` WHERE `Student ID` = :sid AND `email_priority` = 1 LIMIT 1")
            result = conn.execute(query, {"sid": str(target_sid).strip()}).fetchone()
            if result and result[0]:
                return str(result[0]).strip()
    except Exception as e:
        print(f"DB Error get_prio1_email: {e}")
    return ""

def send_otp_email(recipient, otp):
    try:
        resend.Emails.send({
            "from": "MIAE Planner <auth@concordiasequenceplanner.ca>",
            "to": [recipient],
            "bcc": ["concordia.sequence.planner@gmail.com"],
            "subject": "Access Code - COOP Academic Planner",
            "html": f"<h2>Concordia MIAE</h2><p>Your login access code is: <strong style='font-size: 24px;'>{otp}</strong></p><p>This code is valid for 30 minutes.</p>",
            "reply_to": "coop_miae@concordia.ca"
        })
        return True, "The email has been sent"
    except Exception as e:
        print(f"Resend Error: {e}")
        return False, str(e)


def get_email_recipients(program, target_sid, submitter_email, priority1_email, action_type):
    coop_ad_email = "coop_miae@concordia.ca"
    submit_notification = "sorin.voiculescu@concordia.ca"

    if debug_no_emails == "SITE_ACTIVE" : 
        miae_program_assistant = "sabrina.poirier@concordia.ca"
        email_coop_approval = "coopresequence@concordia.ca"
    else:
        miae_program_assistant = debug_email
        email_coop_approval = debug_email
        priority1_email = "vosorin@gmail.com"
        submitter_email = "vosorin@gmail.com"

    coord_email = "frederick.francis@concordia.ca" 
    if program and "INDU" in str(program).upper():
        if debug_no_emails == "SITE_ACTIVE" : coord_email = "nadia.mazzaferro@concordia.ca"
        else: coord_email = debug_email
    elif target_sid:
        try:
            last_digit = int(str(target_sid)[-1])
            if 0 <= last_digit <= 4:
                if debug_no_emails == "SITE_ACTIVE" : coord_email = "frederick.francis@concordia.ca"
                else: coord_email = debug_email
            elif 5 <= last_digit <= 9:
                if debug_no_emails == "SITE_ACTIVE" : coord_email = "nathalie.steverman@concordia.ca" 
                else: coord_email = debug_email
        except ValueError: pass
            
    recipients = {"to": [], "cc": [], "bcc": []}

    if action_type == "SUBMIT":
        recipients["to"].append(coop_ad_email)
        recipients["cc"].extend([miae_program_assistant, coord_email, submitter_email])
        recipients["bcc"].append(submit_notification)
        if priority1_email and priority1_email.strip().lower() != submitter_email.strip().lower():
            recipients["bcc"].append(priority1_email)
        
    elif action_type == "REWORK":
        recipients["to"].append(submitter_email)
        recipients["cc"].extend([coop_ad_email, miae_program_assistant, coord_email])
        if priority1_email and priority1_email.strip().lower() != submitter_email.strip().lower():
            recipients["bcc"].append(priority1_email)
        
    elif action_type == "APPROVED":
        recipients["to"].append(email_coop_approval)
        recipients["cc"].extend([coop_ad_email, miae_program_assistant, coord_email, submitter_email])
        if priority1_email and priority1_email.strip().lower() != submitter_email.strip().lower():
            recipients["bcc"].append(priority1_email)

    recipients["to"] = list(set(filter(None, recipients["to"])))
    recipients["cc"] = list(set(filter(None, recipients["cc"])))
    recipients["bcc"] = list(set(filter(None, recipients["bcc"])))

    return recipients

_CORE_TE_DF = None

def load_data():
    global _CORE_TE_DF
    if _CORE_TE_DF is not None:
        return _CORE_TE_DF.copy()
    try:
        df = pd.read_excel(os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx"))
        df.columns = [str(c).strip() for c in df.columns] 
        _CORE_TE_DF = df.fillna("")
        return _CORE_TE_DF.copy()
    except Exception as e: 
        print(f"Error loading Excel: {e}")
        return pd.DataFrame()
    
def extract_course_code(course_name):
    if not course_name: return ""
    match = re.search(r'(?:REP_)?[A-Z]{3,4}\s?\d{3}[A-Z]?|WT\d', str(course_name).upper())
    return match.group(0).replace(" ", "") if match else str(course_name).strip().upper()

def get_level(course_name):
    match = re.search(r'(\d)\d{2}', str(course_name))
    return int(match.group(1)) if match else 9

def parse_requirements(req_str):
    if not req_str or str(req_str).lower() in ['n/a', 'none', '']: return []
    reqs = []
    for group in re.split(r'[;,]', str(req_str)):
        opts = [m.group(0).replace(" ", "") for o in re.split(r'\bor\b', group, flags=re.IGNORECASE) if (m := re.search(r'(?:REP_)?[A-Z]{3,4}\s?\d{3}[A-Z]?|WT\d', o.upper()))]
        if opts: reqs.append(opts)
    return reqs

def parse_coop_term_string(term_str):
    s = str(term_str).strip().upper()
    if not s or s == 'NAN': return None, None
    year_match = re.search(r'(\d{4})', s)
    if not year_match: return None, None
    year = int(year_match.group(1))
    season = ""
    if 'FALL' in s or 'FA ' in s or s.endswith('FA'): season = 'FALL'
    elif 'WIN' in s or 'WI' in s: season = 'WIN'
    elif 'SUM' in s or 'SU' in s: season = 'SUM'
    if season == 'WIN' and '-' in s: year += 1
    return str(year), season

def get_program_ft_credits():
    ft_dict = {}
    try:
        with engine.connect() as conn:
            query = text("SELECT Program, Credits_FT FROM Program_names")
            for row in conn.execute(query):
                prog = str(row[0]).strip().upper()
                prog = " ".join(prog.split()) 
                try: cr = float(row[1]) if row[1] else 99
                except: cr = 99
                ft_dict[prog] = cr if cr != 0 else 99
    except Exception as e:
        print(f"DB Error Program_names FT: {e}")
    return ft_dict

def get_program_gpa_thresholds():
    gpa_dict = {}
    try:
        with engine.connect() as conn:
            query = text("SELECT Program, GPA_2_terms FROM Program_names")
            for row in conn.execute(query):
                prog = str(row[0]).strip().upper()
                prog = " ".join(prog.split()) 
                try: gpa = float(row[1]) if row[1] else 2.0
                except: gpa = 2.0 
                gpa_dict[prog] = gpa
    except Exception as e:
        print(f"DB Error Program_names GPA: {e}")
    return gpa_dict

# --- ROUTES ---

def get_restrictions():
    try:
        # Citim noul sheet "restrictions"
        df = pd.read_excel(os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx"), sheet_name="restrictions")
        df.columns = [str(c).strip() for c in df.columns]
        
        # Formatăm coloanele de tip dată într-un format text predictibil
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime('%Y-%m-%d')
                
        df = df.fillna("")
        return df.to_dict('records')
    except Exception as e:
        print(f"Error loading Restrictions: {e}")
        return []
    

@app.route("/api/get_cgpa_timeline", methods=["POST"])
def api_get_cgpa_timeline():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    if session.get('is_guest'): return jsonify({})
    
    target_sid = str(request.json.get("student_id", "")).strip()
    if not target_sid: return jsonify({})

    try:
        query = text("SELECT * FROM `CGPA_Timeline` WHERE `Student ID` = :sid")
        df = pd.read_sql(query, engine, params={"sid": target_sid})
        
        cgpa_data = {}
        for _, row in df.iterrows():
            term_str = str(row.get('Academic Term', '')).strip()
            gpa_val = str(row.get('GPA_X_CR', '')).strip()
            cr_val = str(row.get('GPA_X_CR_Actual_Credits', '')).strip()

            if gpa_val and gpa_val.lower() != 'nan':
                try:
                    c_val = row.get('CGPA', 0.0)
                    t_cr = row.get('CGPA_Total_Credits', 0.0)

                    cgpa_data[term_str] = {
                        "gpa_val": float(gpa_val),
                        "credits_val": float(cr_val) if cr_val else 0.0,
                        "cgpa": float(c_val) if pd.notna(c_val) else 0.0,
                        "tot_cr": float(t_cr) if pd.notna(t_cr) else 0.0
                    }
                except ValueError: pass
        return jsonify(cgpa_data)
    except Exception as e:
        print(f"DB Error CGPA: {e}")
        return jsonify({})


def get_student_coop_data(target_sid):
    if not target_sid: return {"found": False}
    target_sid = str(target_sid).strip().replace('.0', '')
    
    try:
        query = text("SELECT * FROM `coop` WHERE `Student ID` = :sid")
        df = pd.read_sql(query, engine, params={"sid": target_sid})
        if df.empty: return {"found": False}
        
        student_records = df.to_dict('records')
        admission_info = None
        cutoff_score = float('inf') 
        parsed_records = []

        for row in student_records:
            raw_term = str(row.get('Term', ''))
            year, season = parse_coop_term_string(raw_term)
            
            adm_val = str(row.get('Admission Term', ''))
            if not admission_info and adm_val and adm_val.lower() != 'nan':
                 adm_year, adm_season = parse_coop_term_string(adm_val)
                 if adm_year and adm_season: admission_info = {"year": adm_year, "term": adm_season}

            if year and season:
                score = 0
                y_int = int(year)
                if season == 'WIN': score = y_int * 10 + 1
                elif season == 'SUM': score = y_int * 10 + 2
                elif season == 'FALL': score = y_int * 10 + 3

                tw_ok = str(row.get('Transferred Withdrawn OK', '')).strip()
                tw_lower = tw_ok.lower()
                is_cutoff = False
                
                if tw_lower and tw_lower != 'nan' and tw_lower != 'ok' and tw_lower != 'none':
                    is_cutoff = True
                    if score < cutoff_score: cutoff_score = score 

                ws_raw = str(row.get('WS', '')).replace('_NF', ' not found')
                if ws_raw.lower() == 'nan': ws_raw = ""
                
                views, applied = 0, 0
                try: views = int(float(row.get('Jobs View no', 0)))
                except: pass
                try: applied = int(float(row.get('Jobs Applied no', 0)))
                except: pass
                
                details = str(row.get('Term Details', '')).strip()
                if details.lower() == 'nan' or details.lower() == 'none': details = ""

                parsed_records.append({
                    "score": score, "key": f"{year}_{season}", "label": str(row.get('Term number Sx or Wx', '')),
                    "ws": ws_raw, "views": views, "applied": applied, "details": details,
                    "tw_ok": tw_ok if is_cutoff else "" 
                })
        
        coop_data = {}
        for rec in parsed_records:
            if rec["score"] <= cutoff_score:
                coop_data[rec["key"]] = {
                    "label": rec["label"], "ws": rec["ws"], "views": rec["views"],
                    "applied": rec["applied"], "details": rec["details"], "tw_ok": rec["tw_ok"]
                }

        return {"found": True, "admission": admission_info, "terms": coop_data}
    except Exception as e:
        print(f"DB Error COOP: {e}")
        return {"found": False}


@app.route("/save_comments", methods=["POST"])
def save_comments():
    if not str(session.get('student_id', '')).startswith('9'): 
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    target_sid = str(data.get("student_id", "")).strip()
    pub_comment = data.get("public_comments", "")
    priv_comment = data.get("private_comments", "")
    
    if not target_sid: return jsonify({"error": "No ID"}), 400
    
    try:
        with engine.begin() as conn:
            check = conn.execute(text("SELECT 1 FROM S_id_comments WHERE S_id = :sid"), {"sid": target_sid}).fetchone()
            if check:
                conn.execute(text("UPDATE S_id_comments SET Public_comments=:pub, PRIVATE_comments=:priv WHERE S_id=:sid"), 
                             {"sid": target_sid, "pub": pub_comment, "priv": priv_comment})
            else:
                conn.execute(text("INSERT INTO S_id_comments (S_id, Public_comments, PRIVATE_comments) VALUES (:sid, :pub, :priv)"), 
                             {"sid": target_sid, "pub": pub_comment, "priv": priv_comment})
        return jsonify({"success": True})
    except Exception as e:
        print(f"DB Error save_comments: {e}")
        return jsonify({"error": str(e)}), 500
    

@app.route("/get_comments", methods=["POST"])
def get_comments():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    sid = str(request.json.get("student_id", "")).strip()
    if not sid: return jsonify({"public": "", "private": ""})
    
    try:
        with engine.connect() as conn:
            query = text("SELECT Public_comments, PRIVATE_comments FROM S_id_comments WHERE S_id = :sid LIMIT 1")
            result = conn.execute(query, {"sid": sid}).fetchone()
            if result:
                return jsonify({
                    "public": str(result[0]).strip() if result[0] and str(result[0]).lower() != 'none' else "",
                    "private": str(result[1]).strip() if result[1] and str(result[1]).lower() != 'none' else ""
                })
    except Exception as e:
        print(f"DB Error get_comments: {e}")
    return jsonify({"public": "", "private": ""})



@app.route("/update_status", methods=["POST"])
def update_status():
    if not str(session.get('student_id', '')).startswith('9'): 
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    status = data.get("status") # 'APPROVED' or 'REWORK'
    target_sid = str(data.get("student_id", ""))
    timestamp = data.get("timestamp", "")
    pub_comment = data.get("public_comments", "")
    priv_comment = data.get("private_comments", "")
    student_name = data.get("student_name", "Student")
    program = data.get("program", "")
    wt_summary = data.get("wt_summary", {})
    term_summary = data.get("term_summary", [])
    original_timestamp_title = data.get("original_title", "Untitled")
    
    try:
        # 1. Update Comments
        with engine.begin() as conn:
            check = conn.execute(text("SELECT 1 FROM S_id_comments WHERE S_id = :sid"), {"sid": target_sid}).fetchone()
            if check:
                conn.execute(text("UPDATE S_id_comments SET Public_comments=:pub, PRIVATE_comments=:priv WHERE S_id=:sid"), 
                             {"sid": target_sid, "pub": pub_comment, "priv": priv_comment})
            else:
                conn.execute(text("INSERT INTO S_id_comments (S_id, Public_comments, PRIVATE_comments) VALUES (:sid, :pub, :priv)"), 
                             {"sid": target_sid, "pub": pub_comment, "priv": priv_comment})
                             
        # 2. Update Sequence Status
        justification = ""
        with engine.begin() as conn:
            query = text("SELECT student_comments FROM Saved_Sequences WHERE student_id = :sid AND Date_Saved = :ts LIMIT 1")
            res = conn.execute(query, {"sid": target_sid, "ts": timestamp}).fetchone()
            justification = res[0] if (res and res[0] and str(res[0]).lower() != 'none') else ""

            if status == "APPROVED":
                status_to_save = f"APPROVED on {datetime.datetime.now().strftime('%Y-%m-%d')}"
                conn.execute(text("UPDATE Saved_Sequences SET status = :stat WHERE student_id = :sid AND Date_Saved = :ts"), 
                             {"stat": status_to_save, "sid": target_sid, "ts": timestamp})
                conn.execute(text("UPDATE Saved_Sequences SET status = 'IGNORED' WHERE student_id = :sid AND status = 'PENDING APPROVAL'"), 
                             {"sid": target_sid})
            else:
                conn.execute(text("UPDATE Saved_Sequences SET status = :stat WHERE student_id = :sid AND Date_Saved = :ts"), 
                             {"stat": status, "sid": target_sid, "ts": timestamp})
                
        # 3. Handle Emails
        submitter_email = data.get("submitter_email", "") 
        if not submitter_email: 
            submitter_email = get_student_email(target_sid)
            
        priority1_email = get_priority1_email(target_sid)
        power_user_name = session.get('guest_name', 'Coordinator') if session.get('is_guest') else session.get('user_email').split('@')[0]

        val_errors = data.get('validation_errors', [])
        val_errors_html = "<ul style='margin: 0; padding-left: 20px; font-size: 14px;'>"
        if not val_errors:
            val_errors_html += "<li style='color: #27ae60; font-weight: bold;'>✅ No validation errors.</li>"
        else:
            for err_html in val_errors:
                val_errors_html += f"<li style='margin-bottom: 4px;'>{err_html}</li>"
        val_errors_html += "</ul>"

        if status == "APPROVED":
            subject = f"Approved sequence for {student_name} {target_sid} {program}"
            
            wt_html = ""
            for wt in ["WT1", "WT2", "WT3"]:
                if wt in wt_summary:
                    info = wt_summary[wt]
                    change_text = f"<span style='color:#e74c3c; font-weight:bold;'>- {info.get('change_text')}</span>" if info.get('change_text') else "<span style='font-weight:bold; color:#27ae60;'>- NO CHANGE</span>"
                    wt_html += f"<p style='margin: 4px 0; font-size: 14px;'><b>{wt}:</b> {info.get('new_term')} {change_text}</p>"
            
            terms_html = ""
            if term_summary:
                terms_html += "<table style='width: 100%; border-collapse: collapse; margin-top: 15px; font-family: Arial, sans-serif; font-size: 13px;'>"
                terms_html += "<thead><tr style='color: white;'>"
                terms_html += "<th style='background-color: #34495e; padding: 10px; border: 1px solid #ddd; text-align: center; width: 16%;'>Year</th>"
                terms_html += "<th style='background-color: #27ae60; padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Summer</th>"
                terms_html += "<th style='background-color: #f39c12; padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Fall</th>"
                terms_html += "<th style='background-color: #3498db; padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Winter</th>"
                terms_html += "</tr></thead><tbody>"
                
                for ts in term_summary:
                    year_str = ts.get('year', '')
                    data_term = ts.get('data', {})
                    
                    terms_html += "<tr>"
                    terms_html += f"<td rowspan='2' style='padding: 10px; border: 1px solid #ddd; vertical-align: middle; background-color: #f8f9fa; text-align: center; font-weight: bold; color: #333;'>{year_str}</td>"
                    
                    for t in ["SUM", "FALL", "WIN"]:
                        t_data = data_term.get(t, {})
                        cr = t_data.get('cr', 0)
                        wt_change = t_data.get('wt_change', '')
                        wt_note_html = f"<br><span style='color: #c0392b; font-size: 10px; font-weight: bold;'>{wt_change}</span>" if wt_change else ""
                        
                        is_curr = t_data.get('is_current_term')
                        is_inst = t_data.get('is_institute_wt')
                        is_coop = t_data.get('is_coop')
                        
                        bg_col = "#fcfcfc"
                        text_col = "#333333"
                        border_col = "#ddd"
                        
                        if is_curr:
                            bg_col = "#fff9c4"
                            border_col = "#fbc02d"
                        elif is_inst:
                            bg_col = "#5DADE2" 
                            text_col = "#ffffff"
                        elif is_coop:
                            bg_col = "#b3e5fc"
                            
                        gpa_info = t_data.get('gpa_info')
                        gpa_html = ""
                        if gpa_info:
                            gpa_val = gpa_info.get('val', 0)
                            gpa_cr = gpa_info.get('credits', 0)
                            cgpa_val = gpa_info.get('cgpa', 0)
                            tot_cr = gpa_info.get('tot_cr', 0)
                            gpa_threshold = gpa_info.get('threshold', 2.0)
                            
                            gpa_cr_str = str(gpa_cr).replace('.0', '') if str(gpa_cr).endswith('.0') else str(gpa_cr)
                            tot_cr_str = str(tot_cr).replace('.0', '') if str(tot_cr).endswith('.0') else str(tot_cr)
                            
                            if gpa_val == -1:
                                gpa_bg = "transparent"
                                gpa_col = text_col
                                display_text = f"GPA past {gpa_cr_str}CR : N/A <br> CGPA {cgpa_val} / {tot_cr_str}CR total"
                            else:
                                if gpa_val <= gpa_threshold:
                                    gpa_bg = "#c0392b"
                                    gpa_col = "#ffffff"
                                elif gpa_val <= gpa_threshold + 0.2:
                                    gpa_bg = "#e67e22"
                                    gpa_col = "#ffffff"
                                else:
                                    gpa_bg = "transparent"
                                    gpa_col = text_col 
                                display_text = f"GPA past {gpa_cr_str}CR : {gpa_val} <br> CGPA {cgpa_val} / {tot_cr_str}CR total"

                            gpa_html = f"<div style='background-color: {gpa_bg}; color: {gpa_col}; font-size: 10px; padding: 4px; margin-top: 4px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1); font-weight: normal;'>{display_text}</div>"

                        terms_html += f"<td style='padding: 5px; border: 1px solid {border_col}; text-align: center; font-weight: bold; background-color: {bg_col}; color: {text_col};'>{cr} CR{wt_note_html}{gpa_html}</td>"
                    
                    terms_html += "</tr><tr>"
                    
                    for t in ["SUM", "FALL", "WIN"]:
                        t_data = data_term.get(t, {})
                        courses = t_data.get('courses', [])
                        
                        is_curr = t_data.get('is_current_term')
                        is_inst = t_data.get('is_institute_wt')
                        is_coop = t_data.get('is_coop')
                        
                        bg_col = "#ffffff"
                        border_col = "#ddd"
                        
                        if is_curr:
                            bg_col = "#fffde7"
                            border_col = "#fbc02d"
                        elif is_inst:
                            bg_col = "#AED6F1" 
                        elif is_coop:
                            bg_col = "#e1f5fe"
                            
                        courses_html = ""
                        for c in courses:
                            if c.get('is_wt'):
                                courses_html += f"<div style='background-color: #d5f5e3; font-weight: bold; padding: 4px; border-radius: 4px; color: #27ae60; border: 1px solid #abebc6; margin-bottom: 3px; text-align: center;'>{c.get('name')}</div>"
                            else:
                                c_text_col = "#154360" if is_inst else "#333333"
                                c_sub_col = "#2980B9" if is_inst else "#7f8c8d"
                                courses_html += f"<div style='margin-bottom: 2px; text-align: center; color: {c_text_col};'>{c.get('name')} <span style='font-size: 11px; color: {c_sub_col};'>({c.get('credit')} cr)</span></div>"
                                
                        terms_html += f"<td style='padding: 10px; border: 1px solid {border_col}; vertical-align: top; background-color: {bg_col};'>{courses_html}</td>"
                    terms_html += "</tr>"
                    
                terms_html += "</tbody></table>"

            html_body = f"""
            <div style="font-family: Arial, sans-serif; color: #333; max-width: 750px; margin: 0 auto; border: 1px solid #e0e0e0; padding: 20px; border-radius: 8px;">
                <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">Approved Course Sequence</h2>
                <p><b>Student Email:</b> {submitter_email}</p>
                <p><b>Student Name:</b> {student_name}</p>
                <p><b>Student ID:</b> {target_sid}</p>
                <p><b>Program:</b> {program}</p>
                
                <div style="background-color: #f0f7ff; border-left: 4px solid #3498db; padding: 10px; margin: 15px 0;">
                    {wt_html}
                </div>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                
                <p><b>MIAE COOP AD/PA Comments:</b></p>
                <div style="background-color: #e8f5e9; border: 1px solid #c8e6c9; padding: 12px; border-radius: 5px; white-space: pre-wrap; font-style: italic; margin-bottom: 15px;">{pub_comment if pub_comment else 'No additional comments.'}</div>
                
                <h3 style="color: #2c3e50; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Automated System Check:</h3>
                <div style="background-color: #fcfcfc; border: 1px solid #eee; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                    {val_errors_html}
                </div>

                <p><b>Student's Justification / Comments:</b></p>
                <div style="background-color: #f9f9f9; border: 1px solid #ddd; padding: 12px; border-radius: 5px; white-space: pre-wrap; font-style: italic; margin-bottom: 25px;">{justification if justification else 'No comments provided.'}</div>

                <h3 style="color: #2c3e50; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Approved Sequence Breakdown</h3>
                {terms_html}
                
                <p style="margin-top: 30px;">Best Regards,<br><b>{power_user_name}</b></p>
            </div>
            """
            
        else: # REWORK
            subject = f"REWORK for {student_name} ({target_sid}) - sequence submitted on {original_timestamp_title}"
            html_body = f"""
            <div style="font-family: Arial, sans-serif; color: #333; max-width: 750px; margin: 0 auto; border: 1px solid #e0e0e0; padding: 20px; border-radius: 8px;">
                <h2 style="color: #c0392b; border-bottom: 2px solid #e74c3c; padding-bottom: 10px;">Action Required: Course Sequence Rework</h2>
                <p><b>Student Email:</b> {submitter_email}</p>
                <p><b>Student Name:</b> {student_name}</p>
                <p><b>Student ID:</b> {target_sid}</p>
                <p><b>Program:</b> {program}</p>
                
                <p style="margin-top: 20px;">Hello {student_name},</p>
                <p>Please consider the comments and the validation errors below to update your sequence.</p>
                
                <p><b>MIAE COOP AD/PA Comments:</b></p>
                <div style="background-color: #fff8e1; border-left: 4px solid #f39c12; padding: 10px; border-radius: 5px; white-space: pre-wrap; margin: 15px 0;">{pub_comment if pub_comment else 'Please review your sequence rules.'}</div>
                
                <h3 style="color: #2c3e50; margin-top: 20px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Automated System Check:</h3>
                <div style="background-color: #fdf2f2; border: 1px solid #fadbd8; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                    {val_errors_html}
                </div>

                <p><b>Student's Justification / Comments:</b></p>
                <div style="background-color: #f9f9f9; border: 1px solid #ddd; padding: 12px; border-radius: 5px; white-space: pre-wrap; font-style: italic; margin-bottom: 25px;">{justification if justification else 'No comments provided.'}</div>
                
                <div style="text-align: center; margin: 35px 0;">
                    <a href="https://concordia-sequence-planner.onrender.com/" style="background-color: #e74c3c; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">Log in to Update Sequence</a>
                </div>
                
                <br>
                <p>Best Regards,<br><b>{power_user_name}</b></p>
            </div>
            """
                    
        email_data = get_email_recipients(program, target_sid, submitter_email, priority1_email, status)

        try:
            resend.Emails.send({
                "from": "MIAE Planner <auth@concordiasequenceplanner.ca>",
                "to": email_data["to"],
                "cc": email_data["cc"],
                "bcc": email_data["bcc"], 
                "reply_to": "coop_miae@concordia.ca",
                "subject": subject,      
                "html": html_body         
            })
        except Exception as e:
            print(f"Eroare la trimitere email: {e}")
            
        return jsonify({"success": True})
    except Exception as e:
        print(f"Status Update DB Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200


@app.route("/", methods=["GET"])
def index():
    if 'user_email' not in session: return redirect(url_for('login'))
    
    df = load_data()
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    programs = []
    if not df.empty and 'PROGRAM' in df.columns:
        df['PROGRAM'] = df['PROGRAM'].astype(str).replace(r'\s+', ' ', regex=True).str.strip()
        programs = sorted(df['PROGRAM'].unique().tolist())
        programs = [p for p in programs if p and p.lower() != 'nan']
    else:
        programs = ["Mechanical Engineering", "Industrial Engineering"]
        
    current_sid = str(session.get('student_id', ''))
    is_guest = session.get('is_guest', False)
    is_power_user = current_sid.startswith('9') and not is_guest
    viewing_sid = session.get('admin_view_sid', current_sid) if not is_guest else f"{current_sid} - GUEST"
    coop_data = get_student_coop_data(viewing_sid) if not is_guest else {"found": False}
    
    pending_list = []
    if is_power_user:
        try:
            with engine.connect() as conn:
                query = text("SELECT * FROM Saved_Sequences WHERE status = 'PENDING APPROVAL' ORDER BY Date_Saved DESC")
                df_pending = pd.read_sql(query, conn)
                for _, r in df_pending.iterrows():
                    def safe_json(val):
                        if pd.notna(val) and str(val).strip() and str(val).lower() != 'none':
                            try: return json.loads(str(val))
                            except: return {}
                        return {}
                        
                    pending_list.append({
                        "email": r.get('Student_Email', 'N/A'),
                        "name": r.get('Sequence_Name', 'Untitled'),
                        "program": r.get('Program', ''),
                        "sequence_data": safe_json(r.get('JSON_Data')),
                        "timestamp": str(r.get('Date_Saved', '')),
                        "term_data": safe_json(r.get('Term_Json_data')),
                        "settings_data": safe_json(r.get('sequence_Json_data')),
                        "status": r.get('status', ''),
                        "justification": r.get('student_comments', ''),
                        "student_id": str(r.get('student_id', '')),
                        "student_name": r.get('student_id_name', '')
                    })
        except Exception as e:
            print(f"Pending List DB Error: {e}")
            
    ft_credits_dict = get_program_ft_credits()
    gpa_thresholds_dict = get_program_gpa_thresholds() 

    restrictions_list = get_restrictions()

    return render_template("planner.html", programe=programs, coop_data_json=json.dumps(coop_data),
                           is_power_user=is_power_user, viewing_sid=viewing_sid, pending_list=pending_list,
                           program_ft_credits_json=json.dumps(ft_credits_dict),
                           program_gpa_thresholds_json=json.dumps(gpa_thresholds_dict),
                           restrictions_json=json.dumps(restrictions_list))



@app.route("/admin_change_sid", methods=["POST"])
def admin_change_sid():
    if not str(session.get('student_id', '')).startswith('9'):
        return jsonify({"error": "Unauthorized"}), 403
    
    new_sid = request.json.get('target_sid')
    if new_sid:
        session['admin_view_sid'] = str(new_sid).strip()
        return jsonify({"success": True})
    return jsonify({"error": "Invalid ID"}), 400


def handle_otp_logic(email, sid, is_guest=False, guest_name=''):
    now = datetime.datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"
    
    try:
        with engine.begin() as conn:
            query = text("SELECT time, login_code FROM logins WHERE email = :email AND used = 0 ORDER BY time DESC LIMIT 1")
            recent = conn.execute(query, {"email": email}).fetchone()
            
            if recent:
                req_time = recent[0]
                if isinstance(req_time, str):
                    try: req_time = datetime.datetime.strptime(req_time, fmt)
                    except ValueError: pass
                    
                if isinstance(req_time, datetime.datetime) and (now - req_time).total_seconds() < 1800:
                    time_str = req_time.strftime('%H:%M:%S')
                    remaining_seconds = 1800 - (now - req_time).total_seconds()
                    rem_min = int(remaining_seconds // 60)
                    time_left_text = f"{rem_min} minute(s)" if rem_min > 0 else f"{int(remaining_seconds)} second(s)"
                    
                    session['otp_message'] = f"⚠️ A code was already sent at {time_str} (server's time). Please check your spam folder. That code is still valid for {time_left_text}."
                    session['pre_auth_email'] = email
                    session['temp_sid'] = sid
                    session['temp_is_guest'] = is_guest
                    session['temp_guest_name'] = guest_name
                    return
                    
            conn.execute(text("UPDATE logins SET used = 1 WHERE email = :email"), {"email": email})
            
            otp = str(random.randint(100000, 999999))
            is_sent, resend_msg = send_otp_email(email, otp)
            
            conn.execute(text("INSERT INTO logins (email, time, login_code, used) VALUES (:email, :time, :code, 0)"), 
                         {"email": email, "time": now.strftime(fmt), "code": otp})
            
            valid_until = (now + datetime.timedelta(minutes=30)).strftime('%H:%M:%S')
            nowtime = now.strftime('%H:%M:%S')
            
            if is_sent:
                session['otp_message'] = f"✅ {resend_msg} to {email}! Please enter the access code below. The code is valid until {valid_until}. FYI, server's time is now {nowtime}."
            else:
                session['otp_message'] = f"❌ Error sending email via Resend API: {resend_msg}"
            
            session['pre_auth_email'] = email
            session['temp_sid'] = sid
            session['temp_is_guest'] = is_guest
            session['temp_guest_name'] = guest_name
    except Exception as e:
        print(f"DB Error OTP: {e}")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action", "check_email")
        email = request.form.get("email", "").strip().lower()

        if action == "check_email":
            is_valid, sid = verify_email_in_sheets(email)
            if is_valid:
                handle_otp_logic(email, sid, is_guest=False)
                return redirect(url_for('verify'))
            else:
                return render_template("login.html", ask_guest_info=True, email=email)
        
        elif action == "guest_login":
            guest_name = request.form.get("guest_name", "Unknown").strip()
            guest_sid = request.form.get("guest_sid", "00000000").strip()
            
            if guest_sid and guest_sid != "00000000":
                priority1_email = get_priority1_email(guest_sid)
                
                if priority1_email:
                    try:
                        www = "https://concordia-sequence-planner.onrender.com/"
                        resend.Emails.send({
                            "from": "MIAE Planner <auth@concordiasequenceplanner.ca>",
                            "to": [priority1_email],
                            "subject": "Security Alert: Unauthorized Login Attempt",
                            "html": f"""
                            <div style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px;">
                                <h2 style="color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 10px;">Security Alert</h2>
                                <p>Hello,</p>
                                <p>There was a login attempt to the Concordia MIAE Academic Planner using your Student ID (<strong>{guest_sid}</strong>).</p>
                                <p>The email address used for this attempt was: <strong>{email}</strong></p>
                                <div style="background-color: #f9f9f9; border-left: 4px solid #f39c12; padding: 10px; margin: 15px 0;">
                                    <strong>If this was you:</strong> Please return to <a href="{www}" style="color: #3498db; text-decoration: none; font-weight: bold;">the Planner</a> and log in using this official email address ({priority1_email}) instead of choosing the Guest option.
                                </div>
                                <p>If you did not make this request, no further action is required. The login request was denied.</p>
                            </div>
                            """,
                            "reply_to": "coop_miae@concordia.ca"
                        })
                    except Exception as mail_err:
                        print(f"Failed to send security alert email: {mail_err}")

                    parts = priority1_email.split('@')
                    if len(parts) == 2:
                        name_part = parts[0]
                        domain_parts = parts[1].split('.')
                        tld = domain_parts.pop()
                        host_part = ".".join(domain_parts)
                        masked_name = name_part[0] + "******" if len(name_part) > 0 else "******"
                        masked_host = host_part[0] + "***" if len(host_part) > 0 else "***"
                        masked_email = f"{masked_name}@{masked_host}.{tld}"
                    else:
                        masked_email = priority1_email

                    error_msg = f"⛔ For this student ID please use the email registered with the CO-OP Institue / Concordia University {masked_email}. For help, contact coop_miae@concordia.ca ."
                    
                    return render_template("login.html", ask_guest_info=True, email=email, error=error_msg)

            session['user_email'] = email
            session['student_id'] = guest_sid
            session['is_guest'] = True
            session['guest_name'] = guest_name
            
            return redirect(url_for('index'))

    return render_template("login.html")


@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get('pre_auth_email')
    if not email: return redirect(url_for('login'))
    
    msg = session.get('otp_message', "Please enter your access code.")

    if request.method == "POST":
        user_otp = request.form.get("otp").strip()
        now = datetime.datetime.now()
        fmt = "%Y-%m-%d %H:%M:%S"
        
        try:
            with engine.begin() as conn:
                query = text("SELECT time, login_code FROM logins WHERE email = :email AND used = 0 ORDER BY time DESC LIMIT 1")
                record = conn.execute(query, {"email": email}).fetchone()
                
                if not record:
                    return render_template("verify.html", error="No valid code found or code expired. Please request a new one.", message=msg)
                    
                req_time = record[0]
                stored_otp = str(record[1]).strip()
                
                if isinstance(req_time, str):
                    try: req_time = datetime.datetime.strptime(req_time, fmt)
                    except ValueError: pass
                    
                if isinstance(req_time, datetime.datetime) and (now - req_time).total_seconds() > 1800:
                    conn.execute(text("UPDATE logins SET used = 1 WHERE email = :email AND login_code = :code"), {"email": email, "code": stored_otp})
                    return render_template("verify.html", error="Code expired! Please request a new one.", message=msg)
                
                if user_otp == stored_otp:
                    conn.execute(text("UPDATE logins SET used = 1 WHERE email = :email AND login_code = :code"), {"email": email, "code": stored_otp})
                    session['user_email'] = email
                    session['student_id'] = session.get('temp_sid', '')
                    session['is_guest'] = session.get('temp_is_guest', False)
                    session['guest_name'] = session.get('temp_guest_name', '')
                    session.pop('otp_message', None) 
                    return redirect(url_for('index'))
                else:
                    return render_template("verify.html", error="Incorrect code!", message=msg)
        except Exception as e:
            print(f"DB Error verify: {e}")
            return render_template("verify.html", error="Database error occurred.", message=msg)

    return render_template("verify.html", message=msg)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route("/api/get_coop_data", methods=["POST"])
def api_get_coop_data():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    if session.get('is_guest'): 
        return jsonify({"found": False})
        
    target_sid = str(request.json.get("student_id", "")).strip()
    coop_data = get_student_coop_data(target_sid)
    return jsonify(coop_data)


@app.route("/api/pending_approvals", methods=["GET"])
def get_pending_approvals():
    current_sid = str(session.get('student_id', ''))
    is_guest = session.get('is_guest', False)
    if not (current_sid.startswith('9') and not is_guest):
        return jsonify([]) 
        
    pending_list = []
    try:
        with engine.connect() as conn:
            query = text("SELECT * FROM Saved_Sequences WHERE status = 'PENDING APPROVAL' ORDER BY Date_Saved DESC")
            df = pd.read_sql(query, conn)
            
            for _, r in df.iterrows():
                def safe_json(val):
                    if pd.notna(val) and str(val).strip() and str(val).lower() != 'none':
                        try: return json.loads(str(val))
                        except: return {}
                    return {}

                pending_list.append({
                    "email": r.get('Student_Email', 'N/A'),
                    "name": r.get('Sequence_Name', 'Untitled'),
                    "program": r.get('Program', ''),
                    "sequence_data": safe_json(r.get('JSON_Data')),
                    "timestamp": str(r.get('Date_Saved', '')),
                    "term_data": safe_json(r.get('Term_Json_data')),
                    "settings_data": safe_json(r.get('sequence_Json_data')),
                    "student_id": str(r.get('student_id', '')),
                    "student_name": r.get('student_id_name', ''),
                    "status": r.get('status', ''),
                    "justification": r.get('student_comments', '')
                })
    except Exception as e:
        print(f"Pending List DB Error: {e}")
        
    return jsonify(pending_list)


@app.route("/save_sequence", methods=["POST"])
def save_sequence():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json
        name = data.get('name', 'Untitled')
        program = data.get('program', '')
        target_id = str(data.get('student_id', session.get('student_id', '')))
        seq_json = json.dumps(data.get('sequence_data', {}))
        term_json = json.dumps(data.get('term_data', {}))
        settings_json = json.dumps(data.get('settings_data', {}))
        
        status = data.get('status', 'SAVED DRAFT') 
        justification = data.get('justification', '')
        
        current_user_id = str(session.get('student_id', ''))
        is_guest = session.get('is_guest', False)
        is_power_user = current_user_id.startswith('9') and not is_guest
        student_name_ui = data.get('student_name', '').strip()
        
        if is_guest:
            current_name = f"GUEST - {session.get('guest_name', '')}"
        else:
            current_name = student_name_ui if student_name_ui else "Official Student"
        
        email_to_save = session['user_email']
        
        if is_power_user and target_id != current_user_id:
            email_to_save = get_student_email(target_id, fallback_email=session['user_email'])
            power_user_name = session.get('guest_name', 'Coordinator') if is_guest else session.get('user_email').split('@')[0]
            name = f"Submitted on {datetime.datetime.now().strftime('%Y-%m-%d')} by {power_user_name}"
            current_name = "ADMIN (PowerUser)"
        
        timestamp = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        with engine.begin() as conn:
            query = text("""
                INSERT INTO Saved_Sequences 
                (Student_Email, Sequence_Name, Program, JSON_Data, Date_Saved, Term_Json_data, sequence_Json_data, status, student_comments, student_id, student_id_name)
                VALUES (:em, :name, :prog, :jdata, :dsaved, :tdata, :sdata, :stat, :scomm, :sid, :sidname)
            """)
            conn.execute(query, {
                "em": email_to_save, "name": name, "prog": program, "jdata": seq_json, "dsaved": timestamp, 
                "tdata": term_json, "sdata": settings_json, "stat": status, "scomm": justification, 
                "sid": target_id, "sidname": current_name
            })
        
        if status == "PENDING APPROVAL":
            if justification:
                try:
                    with engine.begin() as conn:
                        check = conn.execute(text("SELECT Public_comments, PRIVATE_comments FROM S_id_comments WHERE S_id = :sid"), {"sid": target_id}).fetchone()
                        timestamp_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
                        new_addition = f"[{timestamp_str}] Student_answer: {justification}"
                        
                        if check:
                            existing_pub = str(check[0]).strip() if check[0] and str(check[0]).lower() != 'none' else ""
                            new_pub = (existing_pub + "\n\n" + new_addition).strip() if existing_pub else new_addition
                            conn.execute(text("UPDATE S_id_comments SET Public_comments=:pub WHERE S_id=:sid"), {"sid": target_id, "pub": new_pub})
                        else:
                            conn.execute(text("INSERT INTO S_id_comments (S_id, Public_comments, PRIVATE_comments) VALUES (:sid, :pub, '')"), {"sid": target_id, "pub": new_addition})
                except Exception as e:
                    print(f"DB Error save justification: {e}")
                    
            try:
                priority1_email = get_priority1_email(target_id)
                recipients = get_email_recipients(program, target_id, email_to_save, priority1_email, "SUBMIT")
                
                wt_summary = data.get('wt_summary', {})
                term_summary = data.get('term_summary', [])
                
                wt_html = ""
                for wt in ["WT1", "WT2", "WT3"]:
                    if wt in wt_summary:
                        info = wt_summary[wt]
                        change_text = f"<span style='color:#e74c3c; font-weight:bold;'>- {info.get('change_text')}</span>" if info.get('change_text') else "<span style='font-weight:bold; color:#27ae60;'>- NO CHANGE</span>"
                        wt_html += f"<p style='margin: 4px 0; font-size: 14px;'><b>{wt}:</b> {info.get('new_term')} {change_text}</p>"
                
                terms_html = ""
                if term_summary:
                    terms_html += "<table style='width: 100%; border-collapse: collapse; margin-top: 15px; font-family: Arial, sans-serif; font-size: 13px;'>"
                    terms_html += "<thead><tr style='color: white;'>"
                    terms_html += "<th style='background-color: #34495e; padding: 10px; border: 1px solid #ddd; text-align: center; width: 16%;'>Year</th>"
                    terms_html += "<th style='background-color: #27ae60; padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Summer</th>"
                    terms_html += "<th style='background-color: #f39c12; padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Fall</th>"
                    terms_html += "<th style='background-color: #3498db; padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Winter</th>"
                    terms_html += "</tr></thead><tbody>"
                    
                    for ts in term_summary:
                        year_str = ts.get('year', '')
                        data_term = ts.get('data', {})
                        
                        terms_html += "<tr>"
                        terms_html += f"<td rowspan='2' style='padding: 10px; border: 1px solid #ddd; vertical-align: middle; background-color: #f8f9fa; text-align: center; font-weight: bold; color: #333;'>{year_str}</td>"
                        
                        for t in ["SUM", "FALL", "WIN"]:
                            t_data = data_term.get(t, {})
                            cr = t_data.get('cr', 0)
                            wt_change = t_data.get('wt_change', '')
                            wt_note_html = f"<br><span style='color: #c0392b; font-size: 10px; font-weight: bold;'>{wt_change}</span>" if wt_change else ""
                            
                            is_curr = t_data.get('is_current_term')
                            is_inst = t_data.get('is_institute_wt')
                            is_coop = t_data.get('is_coop')
                            
                            bg_col = "#fcfcfc"
                            text_col = "#333333"
                            border_col = "#ddd"
                            
                            if is_curr:
                                bg_col = "#fff9c4"
                                border_col = "#fbc02d"
                            elif is_inst:
                                bg_col = "#5DADE2" 
                                text_col = "#ffffff"
                            elif is_coop:
                                bg_col = "#b3e5fc"
                                
                            gpa_info = t_data.get('gpa_info')
                            gpa_html = ""
                            if gpa_info:
                                gpa_val = gpa_info.get('val', 0)
                                gpa_cr = gpa_info.get('credits', 0)
                                cgpa_val = gpa_info.get('cgpa', 0)
                                tot_cr = gpa_info.get('tot_cr', 0)
                                gpa_threshold = gpa_info.get('threshold', 2.0)
                                
                                gpa_cr_str = str(gpa_cr).replace('.0', '') if str(gpa_cr).endswith('.0') else str(gpa_cr)
                                tot_cr_str = str(tot_cr).replace('.0', '') if str(tot_cr).endswith('.0') else str(tot_cr)
                                
                                if gpa_val == -1:
                                    gpa_bg = "transparent"
                                    gpa_col = text_col
                                    display_text = f"GPA past {gpa_cr_str}CR : N/A  <br> CGPA {cgpa_val} / {tot_cr_str}CR total"
                                else:
                                    if gpa_val <= gpa_threshold:
                                        gpa_bg = "#c0392b"
                                        gpa_col = "#ffffff"
                                    elif gpa_val <= gpa_threshold + 0.2:
                                        gpa_bg = "#e67e22"
                                        gpa_col = "#ffffff"
                                    else:
                                        gpa_bg = "transparent"
                                        gpa_col = text_col 
                                    display_text = f"GPA past {gpa_cr_str}CR : {gpa_val}  <br> CGPA {cgpa_val} / {tot_cr_str}CR total"

                                gpa_html = f"<div style='background-color: {gpa_bg}; color: {gpa_col}; font-size: 10px; padding: 4px; margin-top: 4px; border-radius: 3px; border: 1px solid rgba(0,0,0,0.1); font-weight: normal;'>{display_text}</div>"

                            terms_html += f"<td style='padding: 5px; border: 1px solid {border_col}; text-align: center; font-weight: bold; background-color: {bg_col}; color: {text_col};'>{cr} CR{wt_note_html}{gpa_html}</td>"
                        
                        terms_html += "</tr><tr>"

                        for t in ["SUM", "FALL", "WIN"]:
                            t_data = data_term.get(t, {})
                            courses = t_data.get('courses', [])
                            
                            is_curr = t_data.get('is_current_term')
                            is_inst = t_data.get('is_institute_wt')
                            is_coop = t_data.get('is_coop')
                            
                            bg_col = "#ffffff"
                            border_col = "#ddd"
                            
                            if is_curr:
                                bg_col = "#fffde7"
                                border_col = "#fbc02d"
                            elif is_inst:
                                bg_col = "#AED6F1" 
                            elif is_coop:
                                bg_col = "#e1f5fe"
                                
                            courses_html = ""
                            for c in courses:
                                if c.get('is_wt'):
                                    courses_html += f"<div style='background-color: #d5f5e3; font-weight: bold; padding: 4px; border-radius: 4px; color: #27ae60; border: 1px solid #abebc6; margin-bottom: 3px; text-align: center;'>{c.get('name')}</div>"
                                else:
                                    c_text_col = "#154360" if is_inst else "#333333"
                                    c_sub_col = "#2980B9" if is_inst else "#7f8c8d"
                                    courses_html += f"<div style='margin-bottom: 2px; text-align: center; color: {c_text_col};'>{c.get('name')} <span style='font-size: 11px; color: {c_sub_col};'>({c.get('credit')} cr)</span></div>"
                                    
                            terms_html += f"<td style='padding: 10px; border: 1px solid {border_col}; vertical-align: top; background-color: {bg_col};'>{courses_html}</td>"
                        terms_html += "</tr>"
                        
                    terms_html += "</tbody></table>"

                val_errors = data.get('validation_errors', [])
                val_errors_html = "<ul style='margin: 0; padding-left: 20px; font-size: 14px;'>"
                if not val_errors:
                    val_errors_html += "<li style='color: #27ae60; font-weight: bold;'>✅ No validation errors.</li>"
                else:
                    for err_html in val_errors:
                        val_errors_html += f"<li style='margin-bottom: 4px;'>{err_html}</li>"
                val_errors_html += "</ul>"

                html_body = f"""
                <div style="font-family: Arial, sans-serif; color: #333; max-width: 750px; margin: 0 auto; border: 1px solid #e0e0e0; padding: 20px; border-radius: 8px;">
                    <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">New Course Sequence Submitted for Approval</h2>
                    <p><b>Student Email:</b> {email_to_save}</p>
                    <p><b>Student Name:</b> {current_name}</p>
                    <p><b>Student ID:</b> {target_id}</p>
                    <p><b>Program:</b> {program}</p>
                    
                    <div style="background-color: #f0f7ff; border-left: 4px solid #3498db; padding: 10px; margin: 15px 0;">
                        {wt_html}
                    </div>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">

                    <h3 style="color: #2c3e50; margin-top: 15px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Automated System Check</h3>
                    <div style="background-color: #fdf2f2; border: 1px solid #fadbd8; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                        {val_errors_html}
                    </div>
                    
                    <p><b>Student's Justification / Comments:</b><br>
                    <span style="color: #c0392b; background-color: #fdf2f2; padding: 10px; display: inline-block; margin-top: 5px; border-radius: 4px; border: 1px solid #fadbd8; width: 95%; white-space: pre-wrap;">{justification if justification else '✅ Sequence is valid. No warnings or justification provided.'}</span></p>
                    
                    <h3 style="color: #2c3e50; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Submitted Sequence Breakdown</h3>
                    {terms_html}
                    
                    <div style="text-align: center; margin: 35px 0;">
                        <a href="https://concordia-sequence-planner.onrender.com/" style="background-color: #2742ae; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">Log in to Review Sequence</a>
                    </div>
                </div>
                """
                
                resend.Emails.send({
                    "from": "MIAE Planner <auth@concordiasequenceplanner.ca>", 
                    "to": recipients.get("to", []),
                    "cc": recipients.get("cc", []),
                    "bcc": recipients.get("bcc", []),
                    "subject": f"Change of Sequence Approval Requested for {target_id} ({program})",
                    "html": html_body,
                    "reply_to": email_to_save 
                })
            except Exception as mail_err:
                print(f"Eroare la trimiterea e-mailului: {mail_err}")

        return jsonify({"success": True})
    except Exception as e:
        print(f"Save Error: {e}")
        return jsonify({"error": str(e)}), 500
    

@app.route("/load_sequences", methods=["GET"])
def load_sequences():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        current_sid = str(session.get('student_id', ''))
        is_power_user = current_sid.startswith('9') and not session.get('is_guest', False)
        viewing_sid = str(session.get('admin_view_sid', current_sid)).strip()
        target_email = session['user_email'].lower().strip()
        
        with engine.connect() as conn:
            if is_power_user and viewing_sid and viewing_sid != "ADMIN":
                query = text("SELECT * FROM Saved_Sequences WHERE student_id = :val ORDER BY Date_Saved DESC")
                df = pd.read_sql(query, conn, params={"val": viewing_sid})
            else:
                query = text("SELECT * FROM Saved_Sequences WHERE LOWER(Student_Email) = :val ORDER BY Date_Saved DESC")
                df = pd.read_sql(query, conn, params={"val": target_email})
                
            my_recs = []
            for _, r in df.iterrows():
                def safe_json(val):
                    if pd.notna(val) and str(val).strip() and str(val).lower() != 'none':
                        try: return json.loads(str(val))
                        except: return {}
                    return {}
                    
                my_recs.append({
                    "Sequence_Name": r.get('Sequence_Name', 'Untitled'),
                    "Program": r.get('Program', ''),
                    "Date_Saved": str(r.get('Date_Saved', '')),
                    "JSON_Data": safe_json(r.get('JSON_Data')), 
                    "Term_Data": safe_json(r.get('Term_Json_data')), 
                    "Settings_Data": safe_json(r.get('sequence_Json_data')),
                    "Status": r.get('status', ''),
                    "Student_ID": str(r.get('student_id', '')),
                    "Student_Name": r.get('student_id_name', '')
                })
        return jsonify({"sequences": my_recs}) 
    except Exception as e:
        print(f"Load Error DB: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/get_transcript", methods=["POST"])
def get_transcript():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    target_id = request.json.get("student_id", "").strip()
    if session.get('is_guest'):
        return jsonify({"transcript": [], "student_name": f"GUEST - {session.get('guest_name', 'Unknown')}", "suggested_program": ""})
    if not target_id or target_id == "ADMIN": 
        return jsonify({"transcript": [], "student_name": "", "suggested_program": ""})

    try:
        query = text("SELECT * FROM `Transcripts` WHERE `Student ID` = :sid")
        df = pd.read_sql(query, engine, params={"sid": target_id})
        
        if df.empty:
            return jsonify({"transcript": [], "student_name": "", "suggested_program": ""})

        my_courses = []
        term_disciplines = {}
        student_name = ""
        last_prog_link = ""
        last_disc = ""

        suggested_programs_set = set() # NOU: Salvăm toate programele găsite

        for _, row in df.iterrows():
            term_str = str(row.get('Academic Term', '')).strip()
            if term_str and term_str.lower() != 'nan':
                val_d2 = str(row.get('DISCIPLINE2_DESCR', '')).strip()
                val_d3 = str(row.get('DISCIPLINE3_DESCR', '')).strip()
                combined = " ".join([v for v in [val_d2, val_d3] if v and v.lower() != 'nan']).strip()
                if combined and (term_str not in term_disciplines or not term_disciplines[term_str]):
                    term_disciplines[term_str] = combined

            if not student_name:
                name_val = str(row.get('NAME', '')).strip()
                if name_val.lower() != 'nan': student_name = name_val
                
            val_prog = str(row.get('PROG_LINK', '')).strip().upper()
            if val_prog and val_prog != 'NAN': last_prog_link = val_prog
            
            val_disc = str(row.get('DISCIPLINE1_DESCR', '')).strip().upper()
            if val_disc and val_disc != 'NAN': last_disc = val_disc
            
            # --- NOU: Adăugăm în SET orice program prin care a trecut studentul ---
            last_prog_link_upper = last_prog_link.upper()
            last_disc_upper = last_disc.upper()
            if "UGRD" in last_prog_link_upper:
                if "AERODY" in last_disc_upper: suggested_programs_set.add("AERODYNAMICS")
                elif "STRUCTURES" in last_disc_upper: suggested_programs_set.add("STRUCTURES")
                elif "AVIONICS" in val_disc: suggested_programs_set.add("AVIONICS")
                elif "MECH" in last_disc_upper: suggested_programs_set.add("MECHANICAL")
                elif "INDU" in last_disc_upper: suggested_programs_set.add("INDUSTRIAL")
            elif "GRAD" in last_prog_link_upper:
                if "MECH" in last_disc_upper: suggested_programs_set.add("MECHANICAL GRAD")
                elif "INDU" in last_disc_upper: suggested_programs_set.add("INDUSTRIAL GRAD")

            cred_val = row.get('CREDVAL', 0.0)
            try: cred_val = float(cred_val) if pd.notna(cred_val) else 0.0
            except: cred_val = 0.0

            grade = str(row.get('GRADE', '')).strip()
            if grade.lower() == 'nan': grade = ""

            my_courses.append({
                "course": str(row.get('COURSE', '')).strip().replace(" ", "").upper(),
                "term": term_str,
                "grade": grade,
                "credit": cred_val
            })

        suggested_program = ""
        # Ultimul program va fi cel "suggested", dar știm dacă a mai avut și altele
        if "UGRD" in last_prog_link_upper:
            if "AERODY" in last_disc_upper: suggested_program = "AERODYNAMICS"
            elif "STRUCTURES" in last_disc_upper: suggested_program = "STRUCTURES"
            elif "AVIONICS" in last_disc_upper: suggested_program = "AVIONICS"
            elif "MECH" in last_disc_upper: suggested_program = "MECHANICAL"
            elif "INDU" in last_disc_upper: suggested_program = "INDUSTRIAL"
        elif "GRAD" in last_prog_link_upper:
            if "MECH" in last_disc_upper: suggested_program = "MECHANICAL GRAD"
            elif "INDU" in last_disc_upper: suggested_program = "INDUSTRIAL GRAD"

        multiple_programs = len(suggested_programs_set) > 1

        return jsonify({
            "transcript": my_courses, "student_name": student_name, 
            "suggested_program": suggested_program, "term_disciplines": term_disciplines,
            "multiple_programs": multiple_programs 
        })
    except Exception as e:
        print(f"DB Error Transcript: {e}")
        return jsonify({"transcript": [], "student_name": "", "suggested_program": ""})

    
@app.route("/get_courses", methods=["POST"])
def get_courses():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    df_prog = load_data()
    df_prog.columns = [str(c).strip().upper() for c in df_prog.columns]
    program_name = request.json.get('program', '').strip()
    program_name = " ".join(program_name.split()) 
    
    if 'PROGRAM' in df_prog.columns:
        df_prog['PROGRAM'] = df_prog['PROGRAM'].astype(str).replace(r'\s+', ' ', regex=True).str.strip()
        df_prog = df_prog[df_prog['PROGRAM'] == program_name].copy()
    else:
        return jsonify({"error": "Coloana 'PROGRAM' nu exista in Excel"}), 500
    
    for idx in df_prog.index:
        c_name = str(df_prog.at[idx, 'COURSE']).upper()
        if 'WT2' in c_name: df_prog.at[idx, 'PRE-REQUISITE'] = 'WT1'
        elif 'WT3' in c_name: df_prog.at[idx, 'PRE-REQUISITE'] = 'WT2'
    
    reverse_deps = defaultdict(lambda: {"is_prereq_for": set(), "is_coreq_for": set()})
    for _, row in df_prog.iterrows():
        ccid = extract_course_code(row.get('COURSE', ''))
        for r in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?|WT\d', str(row.get('PRE-REQUISITE', '')).upper()): reverse_deps[r.replace(" ","").replace("-","")]["is_prereq_for"].add(ccid)
        for r in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?|WT\d', str(row.get('CO-REQUISITE', '')).upper()): reverse_deps[r.replace(" ","").replace("-","")]["is_coreq_for"].add(ccid)

    all_courses = []
    def safe_str(val): return "" if str(val).strip().lower() == 'nan' else str(val).strip()

    for _, row in df_prog.iterrows():
        cid = extract_course_code(row.get('COURSE', ''))
        terms_offered = []
        if safe_str(row.get('FALL', '')).upper() == 'X': terms_offered.append('FALL')
        if safe_str(row.get('WIN', '')).upper() == 'X': terms_offered.append('WIN')
        if safe_str(row.get('SUM 1', '')).upper() == 'X' or safe_str(row.get('SUM 2', '')).upper() == 'X' or safe_str(row.get('SUM', '')).upper() == 'X':
            terms_offered.append('SUM')
            
        all_courses.append({
            "id": cid, 
            "display": f"{safe_str(row.get('COURSE', ''))} ({row.get('CREDIT', 0)} cr)",
            "credit": float(row.get('CREDIT', 0) or 0), 
            "full_name": safe_str(row.get('COURSE', '')), 
            "title": safe_str(row.get('TITLE', '')), 
            "is_wt": 'WT' in safe_str(row.get('COURSE', '')).upper(),
            "is_ecp": safe_str(row.get('CORE_TE', '')).upper() == 'ECP', 
            "type": safe_str(row.get('CORE_TE', '')),
            "terms": ", ".join(terms_offered) if terms_offered else "ANY", 
            "prereqs": safe_str(row.get('PRE-REQUISITE', '')), 
            "coreqs": safe_str(row.get('CO-REQUISITE', '')),
            "is_prereq_for": ", ".join(reverse_deps[cid]["is_prereq_for"]) or "None", 
            "is_coreq_for": ", ".join(reverse_deps[cid]["is_coreq_for"]) or "None",
            "already_taken": 0
        })
        
    return jsonify({"courses": all_courses, "pre_placed": {}})
    

@app.route("/generate", methods=["POST"])
def generate():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    program_name = " ".join(data.get('program', '').strip().upper().split())
    
    term_limits = data.get('term_limits', {})
    count_limits = data.get('count_limits', {})
    placed_ui = data.get('placed', {})
    unallocated_ids = data.get('unallocated', [])

    df = load_data()
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    df['PROGRAM'] = df['PROGRAM'].astype(str).replace(r'\s+', ' ', regex=True).str.strip().str.upper()
    df_prog = df[df['PROGRAM'] == program_name].copy()

    for idx in df_prog.index:
        c_name = str(df_prog.at[idx, 'COURSE']).upper()
        if 'WT2' in c_name: df_prog.at[idx, 'PRE-REQUISITE'] = 'WT1'
        elif 'WT3' in c_name: df_prog.at[idx, 'PRE-REQUISITE'] = 'WT2'
    
    all_courses_dict = {}
    taken_courses = set()
    placements = {}
    
    for r in df_prog.to_dict('records'):
        cid = extract_course_code(r['COURSE'])
        r['_id'] = cid 
        all_courses_dict[cid] = r

    core_200s = [c for c, c_data in all_courses_dict.items() if get_level(c) == 2 and 'CORE' in str(c_data.get('CORE_TE', '')).upper()]
    for cid, c_data in all_courses_dict.items():
        if get_level(cid) >= 4:
            existing_prqs = str(c_data.get('PRE-REQUISITE', '')).strip()
            current_prqs_list = parse_requirements(existing_prqs)
            flat_current = [item for sublist in current_prqs_list for item in sublist]
            to_add = [req for req in core_200s if req not in flat_current]
            if to_add:
                new_prqs_str = "; ".join(to_add)
                c_data['PRE-REQUISITE'] = (existing_prqs + "; " + new_prqs_str) if (existing_prqs and existing_prqs.lower() not in ['n/a', 'none']) else new_prqs_str

    rep_counts = defaultdict(int)
    for cid in data.get('repeated', []):
        if cid in all_courses_dict:
            rep_counts[cid] += 1
            count = rep_counts[cid]
            rep_id = f"REP{count}_{cid}"
            
            suffix = f" {count}" if count > 1 else ""
            dummy = all_courses_dict[cid].copy()
            dummy['COURSE'] = f"{str(dummy['COURSE'])} REPEATED{suffix}"
            dummy['_id'] = rep_id 
            
            dummy['PRE-REQUISITE'] = f"REP{count-1}_{cid}" if count > 1 else ""
            all_courses_dict[rep_id] = dummy
            
            orig_prq = str(all_courses_dict[cid].get('PRE-REQUISITE', ''))
            if orig_prq and orig_prq.lower() not in ['n/a', 'none']:
                all_courses_dict[cid]['PRE-REQUISITE'] = orig_prq + "; " + rep_id
            else:
                all_courses_dict[cid]['PRE-REQUISITE'] = rep_id

            for other_cid, c_data in all_courses_dict.items():
                if other_cid != cid and other_cid != rep_id:
                    other_prq = str(c_data.get('PRE-REQUISITE', ''))
                    if other_prq and other_prq.lower() not in ['n/a', 'none']:
                        if re.search(rf'\b{cid}\b', other_prq):
                            c_data['PRE-REQUISITE'] = other_prq + "; " + rep_id
    
    sequence_dict = {str(i): {t: {"credite": 0, "cursuri": [], "coduri": set()} for t in ["SUM", "FALL", "WIN"]} for i in range(1, 8)}

    for tk, cids in placed_ui.items():
        if not cids: continue
        if "Y0" in tk:
            for cid in cids: taken_courses.add(cid); placements[cid] = (0, 'ANY', -1)
            continue
        y_str = tk.split("_")[0]; t = tk.split("_")[1]; y = int(y_str[1:])
        if "SUM" in t: 
            t = "SUM"
        for cid in cids:
            if cid in all_courses_dict:
                c = all_courses_dict[cid]
                is_special = 'WT' in str(c['COURSE']).upper() or str(c.get('CORE_TE', '')).upper() == 'REPEAT'
                cr = 0.0 if is_special else float(c.get('CREDIT', 0) or 0)
                sequence_dict[str(y)][t]["cursuri"].append(c)
                sequence_dict[str(y)][t]["credite"] += cr
                sequence_dict[str(y)][t]["coduri"].add(cid)
                taken_courses.add(cid)
                placements[cid] = (str(y), t, (int(y) - 1) * 3 + ["SUM", "FALL", "WIN"].index(t))

    remaining = set(c for c in unallocated_ids if c in all_courses_dict and c not in taken_courses)
    for cid in data.get('repeated', []):
        rep_id = "REP_" + cid
        if rep_id in all_courses_dict and rep_id not in taken_courses: remaining.add(rep_id)

    unallocated_wts = [c for c in unallocated_ids if 'WT' in c.upper()]
    if unallocated_wts:
        return jsonify({"error": "Please place all Work Terms (WT) on the grid before generating."})
        
    all_wts_in_prog = sorted([c for c in all_courses_dict.keys() if 'WT' in c.upper()])
    
    if all_wts_in_prog:
        placed_wt_indices = sorted([placements[wt][2] for wt in all_wts_in_prog if wt in placements])
        
    for cid in data.get('repeated', []):
        rep_id = "REP_" + cid
        if rep_id in all_courses_dict and rep_id not in taken_courses: remaining.add(rep_id)

    def get_reqs(cid, rt): 
        if cid in all_courses_dict: return parse_requirements(all_courses_dict[cid].get(rt, ''))
        return []

    memo_anc = {}
    def get_ancestor_count(cid, visited=None):
        if visited is None: visited = set()
        if cid in memo_anc: return memo_anc[cid]
        if cid in visited: return 0
        visited.add(cid); count = 0
        for grp in get_reqs(cid, 'PRE-REQUISITE') + get_reqs(cid, 'CO-REQUISITE'):
            valid_opts = [o for o in grp if o in all_courses_dict]
            if valid_opts: count += 1 + get_ancestor_count(valid_opts[0], visited)
        memo_anc[cid] = count; visited.remove(cid); return count

    std_prog = {}
    prog_upper = program_name.upper()
    if "INDUSTRIAL" in prog_upper: std_prog = STANDARD_SEQUENCES.get("INDUSTRIAL", {})
    elif "MECHANICAL" in prog_upper: std_prog = STANDARD_SEQUENCES.get("MECHANICAL", {})
    elif "AERO A" in prog_upper or "AERODYNAMICS" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_A", {})
    elif "AERO B" in prog_upper or "STRUCTURES" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_B", {})
    elif "AERO C" in prog_upper or "AVIONICS" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_C", {})
    elif "AERO" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_A", {}) 

    def get_std_idx(cid):
        pos_str = std_prog.get(cid, "") 
        if not pos_str: return 999
        try:
            parts = pos_str.split('_')
            y = int(parts[0].replace('Y', ''))
            t = parts[1]
            if "SUM" in t: t = "SUM" 
            if t in ["SUM", "FALL", "WIN"]:
                return (y - 1) * 3 + ["SUM", "FALL", "WIN"].index(t)
        except: pass
        return 999

    def place_temporarily(cid, idx):
        y = (idx // 3) + 1
        t = ["SUM", "FALL", "WIN"][idx % 3]
        
        c_data = all_courses_dict.get(cid, {"COURSE": cid})
        is_wt_c = 'WT' in cid.upper()
        is_rep_c = str(c_data.get('CORE_TE', '')).upper() == 'REPEAT'
        cr = 0.0 if (is_wt_c or is_rep_c) else float(c_data.get('CREDIT', 0) or 0)
        
        sequence_dict[str(y)][t]["cursuri"].append(c_data)
        sequence_dict[str(y)][t]["credite"] += cr
        sequence_dict[str(y)][t]["coduri"].add(cid)
        placements[cid] = (str(y), t, idx)
        taken_courses.add(cid)

    def undo_placement(cid):
        if cid not in placements: return
        y, t, idx = placements[cid]
        c_data = all_courses_dict.get(cid, {"COURSE": cid})
        
        is_wt_c = 'WT' in cid.upper()
        is_rep_c = str(c_data.get('CORE_TE', '')).upper() == 'REPEAT'
        cr = 0.0 if (is_wt_c or is_rep_c) else float(c_data.get('CREDIT', 0) or 0)
        
        target = sequence_dict[str(y)][t]
        if c_data in target["cursuri"]: target["cursuri"].remove(c_data)
        target["credite"] -= cr
        if cid in target["coduri"]: target["coduri"].remove(cid)
            
        del placements[cid]
        taken_courses.remove(cid) 
    
    
    def is_valid_slot(cid, idx, ignore_offering=False): 
        y = (idx // 3) + 1
        t = ["SUM", "FALL", "WIN"][idx % 3]
        
        if y > 7: return False
        
        c_data = all_courses_dict.get(cid, {})
        
        if not ignore_offering: 
            if t == "SUM":
                is_offered = (str(c_data.get('SUM 1', '')).strip().upper() == 'X' or 
                              str(c_data.get('SUM 2', '')).strip().upper() == 'X' or
                              str(c_data.get('SUM', '')).strip().upper() == 'X')
            else:
                is_offered = str(c_data.get(t, '')).strip().upper() == 'X'
                
            if not is_offered: 
                return False
        
        is_wt_c = 'WT' in cid.upper()
        is_rep_c = str(c_data.get('CORE_TE', '')).upper() == 'REPEAT'
        cr = 0.0 if (is_wt_c or is_rep_c) else float(c_data.get('CREDIT', 0) or 0)
        target = sequence_dict[str(y)][t]
        
        term_has_wt = any('WT' in str(cx.get('COURSE', '')).upper() for cx in target["cursuri"])
        
        if term_has_wt and not is_wt_c and len(target["cursuri"]) >= 1: return False
        if is_wt_c and len(target["cursuri"]) > 0: return False

        l_cr = float(term_limits.get(f"Y{y}_{t}", 16.0 if t == 'SUM' else 18.0))
        l_cnt = int(count_limits.get(f"Y{y}_{t}", 6 if t == 'SUM' else 5))
        
        if l_cr == 0 or l_cnt == 0: return False

        if not is_wt_c and not is_rep_c:
            if target["credite"] + cr > l_cr: return False
            if len(target["cursuri"]) >= l_cnt: return False

        if get_level(cid) >= 4:
            for k in taken_courses:
                if get_level(k) == 2 and placements[k][2] >= idx: return False
        if get_level(cid) == 2:
            for k in taken_courses:
                if get_level(k) >= 4 and placements[k][2] <= idx: return False

        if '490B' in cid and t != 'WIN': return False
        if '490A' in cid and t != 'FALL': return False
        if '490A' in cid:
            req_490b = cid.replace('490A', '490B')
            if req_490b in placements:
                if idx != placements[req_490b][2] - 1: return False
                
        return True
    

    def solve_branch(cid, max_allowed_idx, depth):
            if depth > 15: return False 
            
            if cid in taken_courses: return placements[cid][2] <= max_allowed_idx
            if cid not in all_courses_dict: return True
            
            min_term_index = -1 
            for grp in get_reqs(cid, 'PRE-REQUISITE'):
                opts = [placements[o][2] for o in grp if o in taken_courses]
                if opts: min_term_index = max(min_term_index, min(opts))
                
            start_idx = max(0, min_term_index + 1)
            
            if get_level(cid) >= 4:
                opts_200 = [placements[k][2] for k in taken_courses if get_level(k) == 2]
                if opts_200: start_idx = max(start_idx, max(opts_200) + 1)
                
            if '490B' in cid:
                req_490a = cid.replace('490B', '490A')
                if req_490a in taken_courses: start_idx = max(start_idx, placements[req_490a][2] + 1)
                
            std_idx = get_std_idx(cid)
            if 'WT' in cid.upper() and std_idx != 999: start_idx = max(start_idx, std_idx)
            
            if start_idx > max_allowed_idx: return False
            
            search_space = list(range(start_idx, max_allowed_idx + 1))
            if std_idx != 999:
                search_space.sort(key=lambda x: abs(x - std_idx))
            else:
                if depth == 0: search_space.sort()
                else: search_space.sort(reverse=True)

            for idx in search_space:
                if not is_valid_slot(cid, idx): continue
                
                place_temporarily(cid, idx)
                success = True
                
                for grp in get_reqs(cid, 'PRE-REQUISITE'):
                    valid_opts = [o for o in grp if o in all_courses_dict]
                    if not valid_opts: continue 
                    grp_ok = False
                    for opt in valid_opts:
                        if solve_branch(opt, idx - 1, depth + 1):
                            grp_ok = True; break
                    if not grp_ok: success = False; break
                        
                if success:
                    for grp in get_reqs(cid, 'CO-REQUISITE'):
                        valid_opts = [o for o in grp if o in all_courses_dict]
                        if not valid_opts: continue
                        grp_ok = False
                        for opt in valid_opts:
                            if solve_branch(opt, idx, depth + 1):
                                grp_ok = True; break
                        if not grp_ok: success = False; break
                        
                if success:
                    if cid in remaining: remaining.remove(cid)
                    return True
                    
                undo_placement(cid)
                
            return False

    print("\n" + "="*50 + "\n🚀 STARTING BACKWARD-CHAINING AI PLANNER 🚀\n" + "="*50)
    remaining_list = list(remaining)
    def goal_priority(c_id):
        data_c = all_courses_dict.get(c_id, {})
        is_te = 1 if str(data_c.get('CORE_TE', '')).upper() == 'TE' else 0
        anc_count = get_ancestor_count(c_id)
        return (-is_te, anc_count, get_level(c_id))
    remaining_list.sort(key=goal_priority, reverse=True)
    for c in remaining_list:
        if c in remaining: solve_branch(c, 20, 0)
    print("="*50 + "\n")

    while True:
        total_cr = sum(float(c.get('CREDIT', 0) or 0) for y in range(1, 8) for t in ["SUM", "FALL", "WIN"] for c in sequence_dict[str(y)][t]["cursuri"] if str(c.get('CORE_TE', '')).strip().upper() not in ['REPEAT', 'ECP'] and 'WT' not in str(c['COURSE']).upper())
        if total_cr <= 120: break
        
        removed_any = False
        for y in range(7, 0, -1):
            for t in ["WIN", "FALL", "SUM"]:
                target = sequence_dict[str(y)][t]
                tes = [c for c in target["cursuri"] if str(c.get('CORE_TE', '')).strip().upper() == 'TE']
                if tes:
                    for te in reversed(tes):
                        cr = float(te.get('CREDIT', 0) or 0)
                        if total_cr - cr >= 120:
                            target["cursuri"].remove(te)
                            target["credite"] -= cr
                            cid = te.get('_id', extract_course_code(te['COURSE']))
                            if cid in target["coduri"]: target["coduri"].remove(cid)
                            if cid not in remaining: remaining.add(cid)
                            removed_any = True; break
                    if removed_any: break
            if removed_any: break
        if not removed_any: break

    warning_msgs = []
    
    ft_dict = get_program_ft_credits()
    prog_upper = " ".join(program_name.upper().split())
    ft_limit = ft_dict.get(prog_upper, 99)
    if ft_limit == 0: ft_limit = 99

    if all_wts_in_prog:
        first_wt = all_wts_in_prog[0]
        if first_wt in placements:
            first_wt_idx = placements[first_wt][2]
            core_credits = 0
            for cy in range(1, 8):
                for ct in ["SUM", "FALL", "WIN"]:
                    c_idx = (cy - 1) * 3 + ["SUM", "FALL", "WIN"].index(ct)
                    if c_idx < first_wt_idx:
                        for c in sequence_dict[str(cy)][ct]["cursuri"]:
                            ctype = str(c.get('CORE_TE', '')).upper().strip()
                            if ctype in ['CORE', 'TE', 'PROG'] or 'CORE' in ctype:
                                core_credits += float(c.get('CREDIT', 0) or 0)
            if core_credits < 30.0:
                warning_msgs.append(f"Only {core_credits} credits of CORE/TE before {first_wt}. You need at least 30 CR.")

        if ft_limit != 99:
            last_wt = all_wts_in_prog[-1]
            if last_wt in placements:
                last_wt_idx = placements[last_wt][2]
                for c_idx in range(1, last_wt_idx): 
                    p_y = (c_idx // 3) + 1
                    p_t = ["SUM", "FALL", "WIN"][c_idx % 3]

                    if p_t != "SUM":
                        term_cr = sum(float(c.get('CREDIT', 0) or 0) for c in sequence_dict[str(p_y)][p_t]["cursuri"] if 'WT' not in str(c.get('COURSE', '')).upper())
                        if 0 < term_cr < ft_limit:
                            warning_msgs.append(f"Study term {p_y} {p_t} (before {last_wt}) must be Full-Time (≥ {ft_limit} credits). Currently has {term_cr} CR.")

    res_seq = {}
    for y in range(1, 8):
        res_seq[f"Year {y}"] = {}
        for t in ["SUM", "FALL", "WIN"]:
            cursuri_list = []
            
            for c in sequence_dict[str(y)][t]["cursuri"]:
                cid_for_json = c.get('_id', extract_course_code(c['COURSE']))
                is_wt = 'WT' in str(c['COURSE']).upper()
                is_rep = str(c.get('CORE_TE', '')).upper() == 'REPEAT'
                display_cr = 0 if (is_wt or is_rep) else c.get('CREDIT', 0)
                display = f"{str(c['COURSE']).strip()} ({display_cr} cr)"
                cursuri_list.append({"id": cid_for_json, "display": display, "is_wt": is_wt})
                    
            res_seq[f"Year {y}"][t] = {"credite": sequence_dict[str(y)][t]["credite"], "cursuri": cursuri_list}

    # Construim res_seq (codul vechi rămâne la fel)
    res_seq = {}
    for y in range(1, 8):
        res_seq[f"Year {y}"] = {}
        for t in ["SUM", "FALL", "WIN"]:
            cursuri_list = []
            for c in sequence_dict[str(y)][t]["cursuri"]:
                cid_for_json = c.get('_id', extract_course_code(c['COURSE']))
                is_wt = 'WT' in str(c['COURSE']).upper()
                is_rep = str(c.get('CORE_TE', '')).upper() == 'REPEAT'
                display_cr = 0 if (is_wt or is_rep) else c.get('CREDIT', 0)
                display = f"{str(c['COURSE']).strip()} ({display_cr} cr)"
                cursuri_list.append({"id": cid_for_json, "display": display, "is_wt": is_wt})
                    
            res_seq[f"Year {y}"][t] = {"credite": sequence_dict[str(y)][t]["credite"], "cursuri": cursuri_list}

    # =========================================================
    # REPARAȚIE AICI: Formatăm corect cursurile respinse (Unallocated) 
    # pentru ca interfața web (JavaScript) să le poată redesena!
    # =========================================================
    unalloc_list = []
    for c in remaining:
        if c in all_courses_dict:
            c_data = all_courses_dict[c]
            is_wt = 'WT' in str(c_data.get('COURSE', '')).upper()
            is_rep = str(c_data.get('CORE_TE', '')).upper() == 'REPEAT'
            display_cr = 0 if (is_wt or is_rep) else c_data.get('CREDIT', 0)
            display = f"{str(c_data.get('COURSE', '')).strip()} ({display_cr} cr)"
            
            unalloc_list.append({
                "id": c, 
                "display": display, 
                "is_wt": is_wt
            })
    # =========================================================
    
    return jsonify({"sequence": res_seq, "unallocated": unalloc_list, "warnings": warning_msgs})
    
    

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True, use_reloader=False)