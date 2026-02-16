import os
import random
import re
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

# External integrations
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import resend

app = Flask(__name__)
app.secret_key = "SVsecretKEY" # Secret key for secure sessions

# Resend API Key - Retrieved from environment variables
resend.api_key = os.environ.get("RESEND_API_KEY")

# ==========================================
# AUTHENTICATION & EMAIL FUNCTIONS
# ==========================================

def verify_email_in_sheets(email):
    """Checks if the student's email exists in the specific Google Sheet tab."""
    base_path = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_path, "cheie_google.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
        client = gspread.authorize(creds)
        
        # Deschidem fișierul și apoi tab-ul specific
        spreadsheet = client.open("Sid_Email_Mirror")
        sheet = spreadsheet.worksheet("Sid_Email_Admission")
        
        data = sheet.get_all_records()
        
        for row in data:
            # Atenție: folosim noul nume de coloană "Primary Email"
            if str(row.get('Primary Email', '')).strip().lower() == email.strip().lower():
                return True
        return False
    except Exception as e:
        print(f"Google Sheets Verification Error: {e}")
        return False

def send_otp_email(recipient, otp):
    """Sends the OTP code using the official domain concordiasequenceplanner.ca."""
    try:
        params = {
            "from": "MIAE Planner <auth@concordiasequenceplanner.ca>",
            "to": [recipient],
            "subject": "Access Code - COOP Academic Planner",
            "html": f"""
                <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 8px;">
                    <h2 style="color: #912338;">Concordia MIAE</h2>
                    <p>Hello,</p>
                    <p>Your login access code is: <strong style="font-size: 24px; color: #912338;">{otp}</strong></p>
                    <p>This code is valid for 5 minutes.</p>
                    <hr style="border: 0; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666;">
                        This is an automated email. For assistance, please reply directly to this message.
                    </p>
                </div>
            """,
            "reply_to": "coop_miae@concordia.ca"
        }
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Resend Error: {e}")
        return False

# ==========================================
# DATA PROCESSING LOGIC
# ==========================================

def load_data():
    """Loads course data from the Excel file."""
    base_path = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(base_path, "CORE_TE.xlsx")
    try:
        df = pd.read_excel(excel_path)
        df.columns = [str(c).strip() for c in df.columns] 
        return df.fillna("")
    except Exception as e:
        print(f"Excel Error: {e}")
        return pd.DataFrame()

def extract_course_code(course_name):
    """Extracts the course ID (e.g., ENGR201) from a string."""
    if not course_name: return ""
    match = re.search(r'[A-Z]{3,4}\s?\d{3}[A-Z]?|WT\d', str(course_name).upper())
    return match.group(0).replace(" ", "") if match else str(course_name).strip().upper()

def get_level(course_name):
    """Extracts the course level (e.g., 2 for ENGR201)."""
    match = re.search(r'(\d)\d{2}', str(course_name))
    return int(match.group(1)) if match else 9

def parse_requirements(req_str):
    """Parses pre-requisite or co-requisite strings into structured lists."""
    if not req_str or str(req_str).lower() in ['n/a', 'none', '']: return []
    requirements = []
    and_groups = re.split(r'[;,]', str(req_str))
    for group in and_groups:
        or_options = re.split(r'\bor\b', group, flags=re.IGNORECASE)
        clean_options = []
        for o in or_options:
            m = re.search(r'[A-Z]{3,4}\s\d{3}[A-Z]?', o.upper())
            if m: clean_options.append(m.group(0).replace(" ", ""))
        if clean_options: requirements.append(clean_options)
    return requirements

pending_otps = {}

# ==========================================
# FLASK ROUTES (PAGES & API)
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").strip().lower()
        if verify_email_in_sheets(email):
            otp = str(random.randint(100000, 999999))
            pending_otps[email] = otp
            if send_otp_email(email, otp):
                session['pre_auth_email'] = email
                return redirect(url_for('verify'))
            return render_template("login.html", error="Error sending email. Please try again.")
        return render_template("login.html", error="Email not authorized in the database.")
    return render_template("login.html")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get('pre_auth_email')
    if not email: return redirect(url_for('login'))
    if request.method == "POST":
        user_otp = request.form.get("otp").strip()
        if pending_otps.get(email) == user_otp:
            session['user_email'] = email
            pending_otps.pop(email, None)
            return redirect(url_for('index'))
        return render_template("verify.html", error="Incorrect code!")
    return render_template("verify.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/", methods=["GET"])
def index():
    if 'user_email' not in session: return redirect(url_for('login'))
    df = load_data()
    if df.empty: return "Error: Could not load course data file."
    programs = sorted(df['Program'].apply(lambda x: str(x).strip()).unique().tolist())
    return render_template("planner.html", programe=programs)

@app.route("/get_courses", methods=["POST"])
def get_courses():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    program_name = data.get('program').strip()
    df = load_data()
    df_prog = df[df['Program'].str.strip() == program_name]

    # Calculate inverse dependencies for UI
    reverse_deps = defaultdict(lambda: {"is_prereq_for": set(), "is_coreq_for": set()})
    for _, row in df_prog.iterrows():
        current_cid = extract_course_code(row['COURSE'])
        for req_match in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?', str(row.get('PRE-REQUISITE', '')).upper()):
            req_code = req_match.replace(" ", "").replace("-", "")
            reverse_deps[req_code]["is_prereq_for"].add(current_cid)
        for req_match in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?', str(row.get('CO-REQUISITE', '')).upper()):
            req_code = req_match.replace(" ", "").replace("-", "")
            reverse_deps[req_code]["is_coreq_for"].add(current_cid)

    all_courses = []
    pre_placed = defaultdict(list)
    def safe_str(val): return "" if str(val).strip().lower() == 'nan' else str(val).strip()

    for _, row in df_prog.iterrows():
        cid = extract_course_code(row['COURSE'])
        suggested_term = safe_str(row.get('Course to place in q1', ''))
        terms_offered = [t for t, col in zip(['Fall', 'Winter', 'Sum 1', 'Sum 2'], ['FALL', 'WIN', 'SUM 1', 'SUM 2']) if safe_str(row.get(col, '')).upper() == 'X']

        all_courses.append({
            "id": cid, 
            "display": f"{safe_str(row['COURSE'])} ({row.get('CREDIT', 0)} cr)",
            "credit": float(row.get('CREDIT', 0) or 0), 
            "is_wt": 'WT' in safe_str(row['COURSE']).upper(),
            "is_ecp": safe_str(row.get('CORE_TE', '')).upper() == 'ECP',
            "full_name": safe_str(row['COURSE']), 
            "type": safe_str(row.get('CORE_TE', '')),
            "terms": ", ".join(terms_offered) if terms_offered else "N/A",
            "prereqs": safe_str(row.get('PRE-REQUISITE', '')), 
            "coreqs": safe_str(row.get('CO-REQUISITE', '')),
            "is_prereq_for": ", ".join(reverse_deps[cid]["is_prereq_for"]) or "None",
            "is_coreq_for": ", ".join(reverse_deps[cid]["is_coreq_for"]) or "None"
        })

        if suggested_term:
            term_up = suggested_term.upper()
            t_str = 'FALL' if 'FALL' in term_up else 'WIN' if 'WIN' in term_up else 'SUM1' if 'SUM 1' in term_up or 'SUM1' in term_up or 'SUM' in term_up else 'SUM2' if 'SUM 2' in term_up or 'SUM2' in term_up else None
            m_year = re.search(r'(\d)', term_up)
            y_str = m_year.group(1) if m_year else None
            if t_str and y_str: pre_placed[f"Y{y_str}_{t_str}"].append(cid)

    return jsonify({"courses": all_courses, "pre_placed": dict(pre_placed)})

@app.route("/generate", methods=["POST"])
def generate():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    program_name = data.get('program').strip()
    term_limits = data.get('term_limits', {})
    count_limits = data.get('count_limits', {})
    placed_ui = data.get('placed', {})
    unallocated_ids = data.get('unallocated', [])

    df = load_data()
    df_prog = df[df['Program'].str.strip() == program_name]
    
    all_courses_dict = {extract_course_code(row['COURSE']): row for row in df_prog.to_dict('records') if str(row.get('CORE_TE', '')).strip().upper() != 'ECP'}
    taken_courses = set([extract_course_code(row['COURSE']) for row in df_prog.to_dict('records') if str(row.get('CORE_TE', '')).strip().upper() == 'ECP'])
    
    sequence_dict = {f"Y{y}": {t: {"cursuri": [], "credite": 0.0, "coduri": set()} for t in ["SUM1", "SUM2", "FALL", "WIN"]} for y in range(1, 8)}
    placements = {}

    def get_term_index(y, t): return y * 4 + ["SUM1", "SUM2", "FALL", "WIN"].index(t)

    # Process manually placed courses from UI
    for tk, cids in placed_ui.items():
        if "Y0" in tk or not cids: continue
        y_str, t = tk.split("_")
        y = int(y_str[1:])
        for cid in cids:
            if cid in all_courses_dict:
                c = all_courses_dict[cid]
                sequence_dict[y_str][t]["cursuri"].append(c)
                sequence_dict[y_str][t]["credite"] += float(c.get('CREDIT', 0) or 0)
                sequence_dict[y_str][t]["coduri"].add(cid)
                taken_courses.add(cid)
                placements[cid] = (y, t, get_term_index(y, t))

    remaining = [cid for cid in unallocated_ids if cid in all_courses_dict]

    def get_reqs(cid, req_type): return parse_requirements(all_courses_dict[cid].get(req_type, '')) if cid in all_courses_dict else []

    # Calculate prerequisite depth for optimal sorting
    memo_depth = {}
    def calc_depth(cid):
        if cid in memo_depth: return memo_depth[cid]
        if cid not in all_courses_dict: return 0
        pre_groups = get_reqs(cid, 'PRE-REQUISITE')
        if not pre_groups:
            memo_depth[cid] = 1; return 1
        max_d = 0
        for group in pre_groups:
            group_max = max((calc_depth(opt) for opt in group if opt in all_courses_dict), default=0)
            if group_max > max_d: max_d = group_max
        depth = 1 + max_d
        memo_depth[cid] = depth
        return depth

    for cid in all_courses_dict: calc_depth(cid)
    # Sort remaining courses by depth (dependencies first), then level (e.g., 200s before 400s)
    remaining.sort(key=lambda x: (memo_depth.get(x, 0), get_level(x)), reverse=True)

    def place_course(cid):
        if cid in taken_courses: return True
        if cid not in all_courses_dict: return False

        c_data = all_courses_dict[cid]
        cr = float(c_data.get('CREDIT', 0) or 0)

        pre_groups = get_reqs(cid, 'PRE-REQUISITE')
        min_term_index = -1 

        for group in pre_groups:
            group_placed = False
            for opt in group:
                if opt in taken_courses:
                    min_term_index = max(min_term_index, placements.get(opt, (0, '', -1))[2])
                    group_placed = True; break
            if not group_placed:
                for opt in group:
                    if opt in all_courses_dict:
                        if place_course(opt):
                            min_term_index = max(min_term_index, placements.get(opt, (0, '', -1))[2])
                            group_placed = True; break
                    else:
                        group_placed = True; break
            if not group_placed: return False

        start_idx = max(0, min_term_index + 1)

        # Force 400-level courses to be placed after all 200-level courses are done
        if get_level(cid) >= 4:
            for k2 in list(all_courses_dict.keys()):
                if get_level(k2) == 2 and k2 not in taken_courses: place_course(k2)
            idx200 = max([placements.get(k, (0,'',-1))[2] for k in taken_courses if get_level(k) == 2], default=-1)
            start_idx = max(start_idx, idx200 + 1)

        for idx in range(start_idx, 7*4): 
            y = (idx // 4) + 1
            if y > 7: break
            t = ["SUM1", "SUM2", "FALL", "WIN"][idx % 4]
            target = sequence_dict[f"Y{y}"][t]

            col_map = {"SUM1": "SUM 1", "SUM2": "SUM 2", "FALL": "FALL", "WIN": "WIN"}
            if str(c_data.get(col_map[t], '')).strip().upper() != 'X': continue

            l_cr = float(term_limits.get(f"Y{y}_{t}", 14))
            l_cnt = int(count_limits.get(f"Y{y}_{t}", 5))
            
            if 'SUM' in t and len(target["cursuri"]) >= 2: continue
            if target["credite"] + cr > l_cr: continue
            if 'SUM' not in t and len(target["cursuri"]) >= l_cnt: continue

            co_groups = get_reqs(cid, 'CO-REQUISITE')
            co_ok = True
            for c_grp in co_groups:
                if not any((r in taken_courses and placements.get(r, (0,'',999))[2] <= idx) for r in c_grp):
                    co_placed = False
                    for r in c_grp:
                        if r in all_courses_dict:
                            if place_course(r) and placements.get(r, (0,'',999))[2] <= idx:
                                co_placed = True; break
                        else:
                            co_placed = True; break 
                    if not co_placed: co_ok = False; break
            if not co_ok: continue

            # Special cases for Capstone (490A/490B)
            if '490A' in cid and t != 'FALL': continue
            if '490B' in cid:
                if t != 'WIN': continue
                idx_490a = placements.get(cid.replace('490B', '490A'), (0,'',-1))[2]
                if idx != idx_490a + 1: continue

            target["cursuri"].append(c_data)
            target["credite"] += cr
            target["coduri"].add(cid)
            taken_courses.add(cid)
            placements[cid] = (y, t, idx)
            if cid in remaining: remaining.remove(cid)
            return True

        return False

    for c in list(remaining): place_course(c)

    # Note: JSON keys "credite" and "cursuri" kept in Romanian to match current JS in planner.html
    res_seq = {f"Year {y}": {t: {"credite": sequence_dict[f"Y{y}"][t]["credite"], "cursuri": [{"id": extract_course_code(c['COURSE']), "display": f"{str(c['COURSE']).strip()} ({c.get('CREDIT',0)} cr)", "is_wt": 'WT' in str(c['COURSE']).upper()} for c in sequence_dict[f"Y{y}"][t]["cursuri"]]} for t in ["SUM1", "SUM2", "FALL", "WIN"]} for y in range(1, 8)}
    
    return jsonify({"sequence": res_seq, "unallocated": [{"id": cid, "display": all_courses_dict[cid]['COURSE']} for cid in remaining]})

if __name__ == "__main__":
    # Dynamically bind to the port provided by Render or use 5000 locally
    port = int(os.environ.get("PORT", 5000))
    # host='0.0.0.0' is required for the app to be accessible in the cloud
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)