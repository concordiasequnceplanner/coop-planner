import os
import random
import re
import json
import datetime
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import resend

app = Flask(__name__)
app.secret_key = "SVsecretKEY"
resend.api_key = os.environ.get("RESEND_API_KEY")

STANDARD_SEQUENCES = {
    "INDUSTRIAL": {
        "ENGR213": "Y1_FALL", "INDU211": "Y1_FALL", "MIAE211": "Y1_FALL", "MIAE215": "Y1_FALL", "MIAE221": "Y1_FALL",
        "ACCO220": "Y1_WIN", "ENCS282": "Y1_WIN", "ENGR201": "Y1_WIN", "ENGR245": "Y1_WIN", "MIAE313": "Y1_WIN",
        "ENGR202": "Y2_SUM1", "ENGR233": "Y2_SUM1", "ENGR251": "Y2_SUM1", "ENGR371": "Y2_SUM1", "MIAE311": "Y2_SUM1", "MIAE312": "Y2_SUM1",
        "WT1": "Y2_FALL",
        "INDU323": "Y2_WIN", "INDU371": "Y2_WIN", "INDU372": "Y2_WIN", "MIAE380": "Y2_WIN",
        "INDU311": "Y3_SUM1", "INDU320": "Y3_SUM1", "INDU324": "Y3_SUM1", "INDU330": "Y3_SUM1", "INDU423": "Y3_SUM1",
        "WT2": "Y3_FALL",
        "ENGR311": "Y3_WIN", "INDU411": "Y3_WIN", "INDU421": "Y3_WIN",
        "WT3": "Y4_SUM1",
        "INDU490A": "Y4_FALL", "INDU412": "Y4_FALL", 
        "INDU490B": "Y4_WIN"
    },
    "MECHANICAL": {
        "CHEM205": "Y1_FALL", "ENGR213": "Y1_FALL", "MIAE211": "Y1_FALL", "MIAE215": "Y1_FALL", "PHYS204": "Y1_FALL",
        "ENGR201": "Y1_WIN", "ENGR233": "Y1_WIN", "ENGR245": "Y1_WIN", "MIAE221": "Y1_WIN", "PHYS205": "Y1_WIN",
        "ENCS282": "Y2_SUM1", "ENGR202": "Y2_SUM1", "ENGR251": "Y2_SUM1", "MIAE313": "Y2_SUM1",
        "ENGR311": "Y2_FALL", "MECH343": "Y2_FALL", "MECH361": "Y2_FALL", "MIAE311": "Y2_FALL", "MIAE312": "Y2_FALL",
        "WT1": "Y2_WIN",
        "MECH351": "Y3_SUM1", "MECH352": "Y3_SUM1", "MECH368": "Y3_SUM1", "MIAE380": "Y3_SUM1",
        "ENGR361": "Y3_FALL", "MECH370": "Y3_FALL", "MECH371": "Y3_FALL", "MECH390": "Y3_FALL",
        "WT2": "Y3_WIN",
        "MECH490A": "Y4_FALL",
        "MECH490B": "Y4_WIN"
    }
}

def get_gspread_client():
    base_path = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_path, "cheie_google.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
    return gspread.authorize(creds)

def verify_email_in_sheets(email):
    try:
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("Sid_Email_Admission")
        for row in sheet.get_all_records():
            if str(row.get('Primary Email', '')).strip().lower() == email.strip().lower():
                return True, str(row.get('Student ID', ''))
        return False, ""
    except Exception: return False, ""

def send_otp_email(recipient, otp):
    try:
        resend.Emails.send({
            "from": "MIAE Planner <auth@concordiasequenceplanner.ca>",
            "to": [recipient],
            "bcc": ["concordia.sequence.planner@gmail.com"],
            "subject": "Access Code - COOP Academic Planner",
            "html": f"<h2>Concordia MIAE</h2><p>Your login access code is: <strong>{otp}</strong></p>",
            "reply_to": "coop_miae@concordia.ca"
        })
        return True
    except Exception: return False

def load_data():
    try:
        df = pd.read_excel(os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx"))
        df.columns = [str(c).strip() for c in df.columns] 
        return df.fillna("")
    except Exception: return pd.DataFrame()

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


def get_student_coop_data(target_sid):
    if not target_sid: return {"found": False}
    target_sid = str(target_sid).strip().replace('.0', '')
    
    try:
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("COOP")
        all_records = sheet.get_all_records()
        student_records = [r for r in all_records if str(r.get('Student ID', '')).strip().replace('.0', '') == target_sid]
        
        if not student_records: return {"found": False}

        admission_info = None
        cutoff_score = float('inf') # Setam limita initial la infinit
        parsed_records = []

        for row in student_records:
            raw_term = str(row.get('Term', ''))
            year, season = parse_coop_term_string(raw_term)
            
            if not admission_info and str(row.get('Admission Term', '')).lower() != 'nan':
                 adm_year, adm_season = parse_coop_term_string(row.get('Admission Term'))
                 if adm_year and adm_season: admission_info = {"year": adm_year, "term": adm_season}

            if year and season:
                # 1. Calculăm SCORUL CRONOLOGIC (Ex: Winter 2025 = 20251, Summer 2025 = 20252, Fall = 20253)
                score = 0
                y_int = int(year)
                if season == 'WIN': score = y_int * 10 + 1
                elif season == 'SUM': score = y_int * 10 + 2
                elif season == 'FALL': score = y_int * 10 + 3

                # 2. Verificăm "Transferred Withdrawn OK"
                tw_ok = str(row.get('Transferred Withdrawn OK', '')).strip()
                tw_lower = tw_ok.lower()
                is_cutoff = False
                
                # Dacă e diferit de "OK" sau gol, stabilim un nou punct de cut-off
                if tw_lower and tw_lower != 'nan' and tw_lower != 'ok':
                    is_cutoff = True
                    if score < cutoff_score:
                        cutoff_score = score # Păstrăm cel mai devreme termen cu problemă

                ws_raw = str(row.get('WS', '')).replace('_NF', ' not found')
                views, applied = 0, 0
                try: views = int(float(row.get('Jobs View no', 0)))
                except: pass
                try: applied = int(float(row.get('Jobs Applied no', 0)))
                except: pass
                
                details = str(row.get('Term Details', '')).strip()
                if details.lower() == 'nan': details = ""

                parsed_records.append({
                    "score": score,
                    "key": f"{year}_{season}",
                    "label": str(row.get('Term number Sx or Wx', '')),
                    "ws": ws_raw, 
                    "views": views, 
                    "applied": applied, 
                    "details": details,
                    "tw_ok": tw_ok if is_cutoff else "" # Trimitem mesajul de eroare către UI
                })
        
        # 3. FILTRAM DATELE pe baza cut-off-ului
        coop_data = {}
        for rec in parsed_records:
            # Păstrăm datele doar până la termenul problemă inclusiv (score <= cutoff_score)
            if rec["score"] <= cutoff_score:
                coop_data[rec["key"]] = {
                    "label": rec["label"],
                    "ws": rec["ws"],
                    "views": rec["views"],
                    "applied": rec["applied"],
                    "details": rec["details"],
                    "tw_ok": rec["tw_ok"]
                }

        return {"found": True, "admission": admission_info, "terms": coop_data}
    
    except Exception as e:
        print(f"Eroare COOP Fetch Backend: {e}")
        return {"found": False, "error": str(e)}
    
    
pending_otps = {}

# --- ROUTES ---
@app.route("/", methods=["GET"])
def index():
    if 'user_email' not in session: return redirect(url_for('login'))
    
    df = load_data()
    programs = sorted(df['Program'].apply(lambda x: str(x).strip()).unique().tolist())
    
    current_sid = str(session.get('student_id', ''))
    is_power_user = current_sid.startswith('9')
    viewing_sid = session.get('admin_view_sid', current_sid)
    
    coop_data = get_student_coop_data(viewing_sid)
    
    return render_template("planner.html", 
                           programe=programs, 
                           coop_data_json=json.dumps(coop_data),
                           is_power_user=is_power_user,
                           viewing_sid=viewing_sid)

@app.route("/admin_change_sid", methods=["POST"])
def admin_change_sid():
    if not str(session.get('student_id', '')).startswith('9'):
        return jsonify({"error": "Unauthorized"}), 403
    
    new_sid = request.json.get('target_sid')
    if new_sid:
        session['admin_view_sid'] = str(new_sid).strip()
        return jsonify({"success": True})
    return jsonify({"error": "Invalid ID"}), 400

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").strip().lower()
        is_valid, sid = verify_email_in_sheets(email)
        if is_valid:
            otp = str(random.randint(100000, 999999))
            pending_otps[email] = otp
            send_otp_email(email, otp)
            session['pre_auth_email'] = email
            session['temp_sid'] = sid
            return redirect(url_for('verify'))
        return render_template("login.html", error="Email not authorized.")
    return render_template("login.html")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get('pre_auth_email')
    if not email: return redirect(url_for('login'))
    if request.method == "POST":
        if pending_otps.get(email) == request.form.get("otp").strip():
            session['user_email'] = email
            session['student_id'] = session.get('temp_sid', '')
            pending_otps.pop(email, None)
            return redirect(url_for('index'))
        return render_template("verify.html", error="Incorrect code!")
    return render_template("verify.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/save_sequence", methods=["POST"])
def save_sequence():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.json
        name = data.get('name', 'Untitled')
        program = data.get('program', '')
        seq_json = json.dumps(data.get('sequence_data', {}))
        term_json = json.dumps(data.get('term_data', {}))
        settings_json = json.dumps(data.get('settings_data', {}))
        
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("Saved_Sequences")
        email = session['user_email']
        timestamp = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        sheet.append_row([email, name, program, seq_json, timestamp, term_json, settings_json])
        return jsonify({"success": True})
    except Exception as e:
        print(f"Save Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/load_sequences", methods=["GET"])
def load_sequences():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    try:
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("Saved_Sequences")
        raw_rows = sheet.get_all_values() 
        target_email = session['user_email'].lower().strip()
        my_recs = []
        for row in raw_rows[1:]:
            if len(row) > 0 and str(row[0]).lower().strip() == target_email:
                def safe_json(idx):
                    if len(row) > idx and row[idx].strip():
                        try: return json.loads(row[idx])
                        except: return {}
                    return {}
                my_recs.append({
                    "Sequence_Name": row[1] if len(row) > 1 else "Untitled",
                    "Program": row[2] if len(row) > 2 else "",
                    "Date_Saved": row[4] if len(row) > 4 else "",
                    "JSON_Data": safe_json(3), "Term_Data": safe_json(5), "Settings_Data": safe_json(6)
                })
        return jsonify({"sequences": my_recs[::-1]}) 
    except Exception as e:
        print(f"Load Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/get_courses", methods=["POST"])
def get_courses():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    df_prog = load_data()
    df_prog = df_prog[df_prog['Program'].str.strip() == request.json.get('program').strip()].copy()
    
    for idx in df_prog.index:
        c_name = str(df_prog.at[idx, 'COURSE']).upper()
        if 'WT2' in c_name: df_prog.at[idx, 'PRE-REQUISITE'] = 'WT1'
        elif 'WT3' in c_name: df_prog.at[idx, 'PRE-REQUISITE'] = 'WT2'
    
    reverse_deps = defaultdict(lambda: {"is_prereq_for": set(), "is_coreq_for": set()})
    for _, row in df_prog.iterrows():
        ccid = extract_course_code(row['COURSE'])
        for r in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?|WT\d', str(row.get('PRE-REQUISITE', '')).upper()): reverse_deps[r.replace(" ","").replace("-","")]["is_prereq_for"].add(ccid)
        for r in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?|WT\d', str(row.get('CO-REQUISITE', '')).upper()): reverse_deps[r.replace(" ","").replace("-","")]["is_coreq_for"].add(ccid)

    all_courses, pre_placed = [], defaultdict(list)
    def safe_str(val): return "" if str(val).strip().lower() == 'nan' else str(val).strip()

    for _, row in df_prog.iterrows():
        cid = extract_course_code(row['COURSE'])
        terms_offered = [t for t, col in zip(['Fall', 'Winter', 'Sum 1', 'Sum 2'], ['FALL', 'WIN', 'SUM 1', 'SUM 2']) if safe_str(row.get(col, '')).upper() == 'X']
        all_courses.append({
            "id": cid, "display": f"{safe_str(row['COURSE'])} ({row.get('CREDIT', 0)} cr)",
            "credit": float(row.get('CREDIT', 0) or 0), "full_name": safe_str(row['COURSE']), 
            "title": safe_str(row.get('TITLE', '')), "is_wt": 'WT' in safe_str(row['COURSE']).upper(),
            "is_ecp": safe_str(row.get('CORE_TE', '')).upper() == 'ECP', "type": safe_str(row.get('CORE_TE', '')),
            "terms": ", ".join(terms_offered) if terms_offered else "N/A",
            "prereqs": safe_str(row.get('PRE-REQUISITE', '')), "coreqs": safe_str(row.get('CO-REQUISITE', '')),
            "is_prereq_for": ", ".join(reverse_deps[cid]["is_prereq_for"]) or "None", "is_coreq_for": ", ".join(reverse_deps[cid]["is_coreq_for"]) or "None",
            "already_taken": 0
        })
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
    df_prog = df[df['Program'].str.strip() == program_name].copy()
    
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

    for cid in data.get('repeated', []):
        if cid in all_courses_dict:
            rep_id = "REP_" + cid
            dummy = all_courses_dict[cid].copy()
            dummy['COURSE'] = "1st attempt " + str(dummy['COURSE'])
            dummy['CORE_TE'] = "REPEAT"; dummy['_id'] = rep_id 
            all_courses_dict[rep_id] = dummy
            orig_prq = str(all_courses_dict[cid].get('PRE-REQUISITE', ''))
            all_courses_dict[cid]['PRE-REQUISITE'] = (orig_prq + "; " + rep_id) if orig_prq else rep_id

    sequence_dict = {str(y): {t: {"cursuri": [], "credite": 0.0, "coduri": set()} for t in ["SUM1", "SUM2", "FALL", "WIN"]} for y in range(1, 8)}

    for tk, cids in placed_ui.items():
        if not cids: continue
        if "Y0" in tk:
            for cid in cids: taken_courses.add(cid); placements[cid] = (0, 'ANY', -1)
            continue
        y_str = tk.split("_")[0]; t = tk.split("_")[1]; y = int(y_str[1:])
        for cid in cids:
            if cid in all_courses_dict:
                c = all_courses_dict[cid]
                is_special = 'WT' in str(c['COURSE']).upper() or str(c.get('CORE_TE', '')).upper() == 'REPEAT'
                cr = 0.0 if is_special else float(c.get('CREDIT', 0) or 0)
                sequence_dict[str(y)][t]["cursuri"].append(c)
                sequence_dict[str(y)][t]["credite"] += cr
                sequence_dict[str(y)][t]["coduri"].add(cid)
                taken_courses.add(cid)
                placements[cid] = (y, t, (y - 1) * 4 + ["SUM1", "SUM2", "FALL", "WIN"].index(t))

    remaining = set(c for c in unallocated_ids if c in all_courses_dict and c not in taken_courses)
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
    if "INDUSTRIAL" in program_name.upper(): std_prog = STANDARD_SEQUENCES.get("INDUSTRIAL", {})
    elif "MECHANICAL" in program_name.upper(): std_prog = STANDARD_SEQUENCES.get("MECHANICAL", {})

    def get_std_idx(cid):
        base_cid = cid.replace("REP_", "")
        loc = std_prog.get(base_cid)
        if loc:
            y = int(loc.split('_')[0][1:]); t_idx = {"SUM": 0, "SUM1": 0, "SUM2": 1, "FALL": 2, "WIN": 3}.get(loc.split('_')[1], 2)
            return (y - 1) * 4 + t_idx
        return 999

    def place_temporarily(cid, idx):
        y = (idx // 4) + 1; t = ["SUM1", "SUM2", "FALL", "WIN"][idx % 4]
        target = sequence_dict[str(y)][t]; c_data = all_courses_dict[cid]
        cr = 0.0 if ('WT' in cid.upper() or c_data.get('CORE_TE', '') == 'REPEAT') else float(c_data.get('CREDIT', 0) or 0)
        target["cursuri"].append(c_data); target["credite"] += cr; target["coduri"].add(cid); taken_courses.add(cid); placements[cid] = (y, t, idx)

    def undo_placement(cid):
        idx = placements[cid][2]; y = (idx // 4) + 1; t = ["SUM1", "SUM2", "FALL", "WIN"][idx % 4]
        target = sequence_dict[str(y)][t]; c_data = all_courses_dict[cid]
        cr = 0.0 if ('WT' in cid.upper() or c_data.get('CORE_TE', '') == 'REPEAT') else float(c_data.get('CREDIT', 0) or 0)
        target["cursuri"] = [c for c in target["cursuri"] if c['_id'] != cid]
        target["credite"] -= cr; target["coduri"].remove(cid); taken_courses.remove(cid); del placements[cid]

    def is_valid_slot(cid, idx):
        y = (idx // 4) + 1; t = ["SUM1", "SUM2", "FALL", "WIN"][idx % 4]
        if y > 7: return False
        c_data = all_courses_dict[cid]; col_map = {"SUM1": "SUM 1", "SUM2": "SUM 2", "FALL": "FALL", "WIN": "WIN"}
        if str(c_data.get(col_map[t], '')).strip().upper() != 'X': return False
        
        is_wt_c = 'WT' in cid.upper(); is_rep_c = str(c_data.get('CORE_TE', '')).upper() == 'REPEAT'
        cr = 0.0 if (is_wt_c or is_rep_c) else float(c_data.get('CREDIT', 0) or 0)
        target = sequence_dict[str(y)][t]
        term_has_wt = any('WT' in str(cx.get('COURSE', '')).upper() for cx in target["cursuri"])
        
        other_summer_has_wt = False; other_summer_has_courses = False
        if 'SUM' in t:
            other_t = 'SUM2' if t == 'SUM1' else 'SUM1'; other_target = sequence_dict[str(y)][other_t]
            other_summer_has_wt = any('WT' in str(cx.get('COURSE', '')).upper() for cx in other_target["cursuri"])
            other_summer_has_courses = len(other_target["cursuri"]) > 0

        if term_has_wt or other_summer_has_wt: return False
        if is_wt_c and (len(target["cursuri"]) > 0 or other_summer_has_courses): return False

        l_cr = float(term_limits.get(f"Y{y}_{t}", 10.0 if 'SUM' in t else 17.0))
        l_cnt = int(count_limits.get(f"Y{y}_{t}", 3 if 'SUM' in t else 5))
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
        if c in remaining: solve_branch(c, 27, 0)
    print("="*50 + "\n")

    while True:
        total_cr = sum(float(c.get('CREDIT', 0) or 0) for y in range(1, 8) for t in ["SUM1", "SUM2", "FALL", "WIN"] for c in sequence_dict[str(y)][t]["cursuri"] if str(c.get('CORE_TE', '')).strip().upper() not in ['REPEAT', 'ECP'] and 'WT' not in str(c['COURSE']).upper())
        if total_cr <= 120: break
        removed_any = False
        for y in range(7, 0, -1):
            for t in ["WIN", "FALL", "SUM2", "SUM1"]:
                target = sequence_dict[str(y)][t]
                tes = [c for c in target["cursuri"] if str(c.get('CORE_TE', '')).strip().upper() == 'TE']
                if tes:
                    for te in reversed(tes):
                        cr = float(te.get('CREDIT', 0) or 0)
                        if total_cr - cr >= 120:
                            target["cursuri"].remove(te); target["credite"] -= cr; cid = te.get('_id', extract_course_code(te['COURSE']))
                            if cid in target["coduri"]: target["coduri"].remove(cid)
                            if cid not in remaining: remaining.add(cid)
                            removed_any = True; break
                    if removed_any: break
            if removed_any: break
        if not removed_any: break

    res_seq = {}
    for y in range(1, 8):
        res_seq[f"Year {y}"] = {}
        for t in ["SUM1", "SUM2", "FALL", "WIN"]:
            cursuri_list = []
            for c in sequence_dict[str(y)][t]["cursuri"]:
                cid_for_json = c.get('_id', extract_course_code(c['COURSE']))
                is_wt = 'WT' in str(c['COURSE']).upper()
                is_rep = str(c.get('CORE_TE', '')).upper() == 'REPEAT'
                display_cr = 0 if (is_wt or is_rep) else c.get('CREDIT', 0)
                display = f"{str(c['COURSE']).strip()} ({display_cr} cr)"
                cursuri_list.append({"id": cid_for_json, "display": display, "is_wt": is_wt})
            res_seq[f"Year {y}"][t] = {"credite": sequence_dict[str(y)][t]["credite"], "cursuri": cursuri_list}
            
    unalloc_list = [{"id": cid, "display": all_courses_dict[cid]['COURSE']} for cid in remaining]
    return jsonify({"sequence": res_seq, "unallocated": unalloc_list})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True, use_reloader=False)