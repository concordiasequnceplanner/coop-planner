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


def get_student_email(target_sid, fallback_email="student@concordia.ca"):
    try:
        client = get_gspread_client()
        # Ne uitam in sheet-ul corect pentru a lega ID-ul de Email!
        sheet = client.open("Sid_Email_Mirror").worksheet("Sid_Email_Admission")
        for row in sheet.get_all_records():
            if str(row.get('Student ID', '')).strip() == str(target_sid).strip():
                em = str(row.get('Primary Email', '')).strip()
                return em if em else fallback_email
    except Exception as e:
        print("Error finding email:", e)
    return fallback_email

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
        # Dacă trece de linia de mai sus fără eroare, Resend confirmă expedierea!
        return True, "I confirm the email has been sent"
    except Exception as e:
        print(f"Resend Error: {e}")
        return False, str(e)


def get_email_recipients(program, target_sid, student_email, action_type):
    # Adrese fixe
    coop_ad_email = "coop_miae@concordia.ca"
    submit_notification = "sorin.voiculescu@concordia.ca"
    miae_program_assistant = "sabrina.poirier@concordia.ca"
    email_coop_approval = "coopresequence@concordia.ca"

    # Logica de selectare a coordonatorului (default Frederick pentru cazurile neacoperite)
    coord_email = "frederick.francis@concordia.ca" 
    
    if program and "INDU" in str(program).upper():
        # Nathalie pentru INDU
        coord_email = "nathalie.steverman@concordia.ca"
    elif target_sid:
        try:
            last_digit = int(str(target_sid)[-1])
            if 0 <= last_digit <= 4:
                # Frederick
                coord_email = "frederick.francis@concordia.ca"
            elif 5 <= last_digit <= 9:
                # Nadia (momentan setat tot pe Frederick, cf. codului tau)
                coord_email = "nadia.mazzaferro@concordia.ca"
        except ValueError:
            pass
            
    # Pregătim dicționarul de returnare
    recipients = {
        "to": [],
        "cc": [],
        "bcc": []
    }

    # Aplicăm logica în funcție de acțiune
    if action_type == "SUBMIT":
        recipients["to"].append(coop_ad_email)
        recipients["cc"].extend([miae_program_assistant, coord_email, student_email])
        recipients["bcc"].append(submit_notification)
        
    elif action_type == "REWORK":
        recipients["to"].append(student_email)
        recipients["cc"].extend([coop_ad_email, miae_program_assistant, coord_email])
        
    elif action_type == "APPROVED":
        recipients["to"].append(email_coop_approval)
        recipients["cc"].extend([coop_ad_email, miae_program_assistant, coord_email, student_email])

    # Curățăm listele de posibile valori nule/goale și eliminăm duplicatele, păstrând formatul de listă
    recipients["to"] = list(set(filter(None, recipients["to"])))
    recipients["cc"] = list(set(filter(None, recipients["cc"])))
    recipients["bcc"] = list(set(filter(None, recipients["bcc"])))

    return recipients



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
        
        # 1. Citim Headerele
        headers = [str(h).strip() for h in sheet.row_values(1)]
        if 'Student ID' not in headers: return {"found": False}
        idx_sid = headers.index('Student ID')
        
        # 2. Descărcăm doar coloana de ID-uri
        all_sids = sheet.col_values(idx_sid + 1)
        
        # 3. Găsim pe ce rânduri se află studentul nostru
        matching_rows = []
        for i, sid in enumerate(all_sids):
            if str(sid).strip().replace('.0', '') == target_sid:
                matching_rows.append(i + 1)
                
        if not matching_rows: return {"found": False}
        
        # 4. Cerem DOAR rândurile studentului din Google Sheets
        ranges = [f"A{r}:Z{r}" for r in matching_rows]
        raw_results = sheet.batch_get(ranges)
        
        # Reconstruim formatul de dicționar așteptat de restul codului tău
        student_records = []
        for res in raw_results:
            if not res or not res[0]: continue
            row = res[0]
            row.extend([""] * (len(headers) - len(row)))
            row_dict = dict(zip(headers, row))
            student_records.append(row_dict)

        admission_info = None
        cutoff_score = float('inf') 
        parsed_records = []

        # ... De aici în jos lasă codul tău ORIGINAL ...
        for row in student_records:
            raw_term = str(row.get('Term', ''))
            # ... restul funcției tale care calculează score, ws, views etc.
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
     


# --- ROUTES ---

@app.route("/save_comments", methods=["POST"])
def save_comments():
    # Doar Power Userii au voie să salveze comentarii automat
    if not str(session.get('student_id', '')).startswith('9'): 
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.json
    target_sid = str(data.get("student_id", "")).strip()
    pub_comment = data.get("public_comments", "")
    priv_comment = data.get("private_comments", "")
    
    if not target_sid: return jsonify({"error": "No ID"}), 400
    
    try:
        client = get_gspread_client()
        comments_sheet = client.open("Sid_Email_Mirror").worksheet("S_id_comments")
        records = comments_sheet.get_all_values()
        
        found_row = -1
        for i, row in enumerate(records[1:], start=2): # +2 pt că indexăm de la rândul 2 (după headere)
            if len(row) > 0 and str(row[0]).strip() == target_sid:
                found_row = i
                break
                
        if found_row != -1:
            # Rândul există, dăm update
            comments_sheet.update(values=[[pub_comment, priv_comment]], range_name=f"B{found_row}:C{found_row}")
        else:
            # Studentul nu are comentarii încă, adăugăm un rând nou
            comments_sheet.append_row([target_sid, pub_comment, priv_comment])
            
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error auto-saving comments: {e}")
        return jsonify({"error": str(e)}), 500
    

@app.route("/get_comments", methods=["POST"])
def get_comments():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    sid = str(request.json.get("student_id", "")).strip()
    if not sid: return jsonify({"public": "", "private": ""})
    
    try:
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("S_id_comments")
        records = sheet.get_all_values() # Folosim values, nu records
        
        for row in records[1:]: # Sarim peste primul rand (headerele)
            if len(row) > 0 and str(row[0]).strip() == sid:
                return jsonify({
                    "public": str(row[1]).strip() if len(row) > 1 else "",
                    "private": str(row[2]).strip() if len(row) > 2 else ""
                })
    except Exception as e:
        print(f"Error fetching comments: {e}")
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
        client = get_gspread_client()
        
        # 1. Update S_id_comments (Corectat pentru noul format gspread)
        comments_sheet = client.open("Sid_Email_Mirror").worksheet("S_id_comments")
        records = comments_sheet.get_all_values()
        found_row = -1
        for i, row in enumerate(records[1:], start=2):
            if len(row) > 0 and str(row[0]).strip() == target_sid:
                found_row = i
                break
                
        if found_row != -1:
            # Formatul corect: specificam argumentele cu nume (values si range_name)
            comments_sheet.update(values=[[pub_comment, priv_comment]], range_name=f"B{found_row}:C{found_row}")
        else:
            comments_sheet.append_row([target_sid, pub_comment, priv_comment])
            
        row_idx = data.get("row_index") # Extragem randul sigur
        
        # 2. Update Saved_Sequences Status (FOLOSIND RANDUL EXACT + CLEANUP PENDING)
        seq_sheet = client.open("Sid_Email_Mirror").worksheet("Saved_Sequences")
        
        if status == "APPROVED":
            status_to_save = f"APPROVED on {datetime.datetime.now().strftime('%Y-%m-%d')}"
            seq_records = seq_sheet.get_all_values()
            
            # Parcurgem tot fisierul pentru a aproba secventa curenta si a le anula pe restul
            for i, row in enumerate(seq_records[1:], start=2):
                row_sid = str(row[10]).strip() if len(row) > 10 else ""
                row_time = str(row[4]).strip() if len(row) > 4 else ""
                row_status = str(row[7]).strip().upper() if len(row) > 7 else ""
                
                # A. Aceasta este secventa pe care o aprobam ACUM
                if (row_idx is not None and i == row_idx) or (row_idx is None and row_sid == target_sid and row_time == str(timestamp).strip()):
                    seq_sheet.update_cell(i, 8, status_to_save)
                    
                # B. Daca e acelasi student si secventa e inca in Pending, o trecem pe IGNORED
                elif row_sid == target_sid and row_status == "PENDING APPROVAL":
                    seq_sheet.update_cell(i, 8, "IGNORED")
                    
        else:
            # Daca statusul este REWORK, modificam STRICT secventa selectata, nu ne atingem de restul
            status_to_save = status
            if row_idx is not None:
                seq_sheet.update_cell(row_idx, 8, status_to_save)
            else:
                seq_records = seq_sheet.get_all_values()
                for i, row in enumerate(seq_records[1:], start=2):
                    row_sid = str(row[10]).strip() if len(row) > 10 else ""
                    row_time = str(row[4]).strip() if len(row) > 4 else ""
                    if row_sid == target_sid and row_time == str(timestamp).strip():
                        seq_sheet.update_cell(i, 8, status_to_save) 
                        break
                
        # 3. Trimitem Emailul
        student_email = get_student_email(target_sid)
        power_user_name = session.get('guest_name', 'Coordinator') if session.get('is_guest') else session.get('user_email').split('@')[0]
        recipients = get_email_recipients(program, target_sid, student_email, status)

        if status == "APPROVED":
            subject = f"Approved sequence for {student_name} {target_sid} {program}"
            
            wt_html = ""
            for wt in ["WT1", "WT2", "WT3"]:
                if wt in wt_summary:
                    info = wt_summary[wt]
                    change_text = f"<span style='color:red; font-weight:bold;'>changed from ({info['original']})</span>" if info['changed'] else "<span style='font-weight:bold;'>NO CHANGE</span>"
                    wt_html += f"<p style='margin: 4px 0;'><b>{wt}:</b> {info['new_term']} - {change_text}</p>"
                    
            # --- CONSTRUIRE TABEL 4 COLOANE / 2 RANDURI ---
            terms_html = ""
            if term_summary:
                terms_html += "<table style='width: 100%; border-collapse: collapse; margin-top: 15px; font-family: Arial, sans-serif; font-size: 13px;'>"
                terms_html += "<thead><tr style='background-color: #34495e; color: white;'><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 16%;'>Year</th><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Summer</th><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Fall</th><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Winter</th></tr></thead>"
                terms_html += "<tbody>"
                
                for ts in term_summary:
                    year_str = ts.get('year', '')
                    data_term = ts.get('data', {})
                    
                    # Randul 1: Credite si Nota "WAS W-x"
                    terms_html += "<tr>"
                    terms_html += f"<td rowspan='2' style='padding: 10px; border: 1px solid #ddd; vertical-align: middle; background-color: #f8f9fa; text-align: center; font-weight: bold;'>{year_str}</td>"
                    
                    for t in ["SUM", "FALL", "WIN"]:
                        t_data = data_term.get(t, {})
                        cr = t_data.get('cr', 0)
                        wt_change = t_data.get('wt_change', '')
                        wt_note_html = f"<br><span style='color: #c0392b; font-size: 11px;'>{wt_change}</span>" if wt_change else ""
                        terms_html += f"<td style='padding: 5px; border: 1px solid #ddd; text-align: center; font-weight: bold; background-color: #fcfcfc;'>{cr} CR{wt_note_html}</td>"
                    terms_html += "</tr>"
                    
                    # Randul 2: Cursurile
                    terms_html += "<tr>"
                    for t in ["SUM", "FALL", "WIN"]:
                        t_data = data_term.get(t, {})
                        courses = t_data.get('courses', [])
                        courses_html = ""
                        for c in courses:
                            if c.get('is_wt'):
                                courses_html += f"<div style='background-color: #d5f5e3; font-weight: bold; padding: 4px; border-radius: 4px; color: #27ae60; border: 1px solid #abebc6; margin-bottom: 3px; text-align: center;'>{c.get('name')}</div>"
                            else:
                                courses_html += f"<div style='margin-bottom: 2px; text-align: center;'>{c.get('name')} <span style='font-size: 11px; color: #7f8c8d;'>({c.get('credit')} cr)</span></div>"
                        terms_html += f"<td style='padding: 10px; border: 1px solid #ddd; vertical-align: top;'>{courses_html}</td>"
                    terms_html += "</tr>"
                    
                terms_html += "</tbody></table>"

            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 750px; margin: 0 auto; color: #333;">
                <p>Hello,</p>
                <p>Please find the approved sequence for {student_name} ({target_sid}) - {program}</p>
                <div style="background-color: #f0f7ff; border-left: 4px solid #3498db; padding: 10px; margin: 15px 0;">
                    {wt_html}
                </div>
                
                <p><b>Coordinator Comments:</b></p>
                <div style="background-color: #e8f5e9; border: 1px solid #c8e6c9; padding: 12px; border-radius: 5px; white-space: pre-wrap; font-style: italic;">{pub_comment if pub_comment else 'No additional comments.'}</div>
                
                <h3 style="color: #2c3e50; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px;">Approved Sequence Breakdown</h3>
                {terms_html}
                
                <p style="margin-top: 30px;">Best Regards,<br><b>{power_user_name}</b></p>
            </div>
            """
            
        else: # REWORK
            subject = f"REWORK for sequence submitted on {original_timestamp_title}"
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
                <p>Hello {student_name},</p>
                <p>Please consider the comments below and update your sequence.</p>
                <div style="background-color: #fff8e1; border-left: 4px solid #f39c12; padding: 10px; border-radius: 5px; white-space: pre-wrap; margin: 15px 0;">{pub_comment if pub_comment else 'Please review your sequence rules.'}</div>
                <br>
                <p>Best Regards,<br><b>{power_user_name}</b></p>
            </div>
            """
                    
                # Așa preiei destinatarii acum:
        # Așa preiei destinatarii acum (am adăugat parametrul 'status'):
        email_data = get_email_recipients(program, target_sid, student_email, status)

        try:
            resend.Emails.send({
                "from": "MIAE Planner <auth@concordiasequenceplanner.ca>",
                "to": email_data["to"],
                "cc": email_data["cc"],
                "bcc": email_data["bcc"], 
                "reply_to": "coop_miae@concordia.ca",
                "subject": subject,       # <-- Folosim variabila reală creată mai sus
                "html": html_body         # <-- Folosim corpul de email real creat mai sus
            })
        except Exception as e:
            print(f"Eroare la trimitere email: {e}")
            
        return jsonify({"success": True})
    except Exception as e:
        print(f"Status Update Error: {e}")
        return jsonify({"error": str(e)}), 500
    



@app.route("/health", methods=["GET"])
def health_check():
    # Returnează un simplu 200 OK pentru Render, ca să nu ne mai restarteze aplicația
    return "OK", 200


@app.route("/", methods=["GET"])
def index():
    if 'user_email' not in session: return redirect(url_for('login'))
    
    df = load_data()
    
    # 1. NORMALIZEAZA COLOANELE (Litere mari, fara spatii la capete)
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    programs = []
    if not df.empty and 'PROGRAM' in df.columns:
        # 2. STERGE SPATIILE DUBLE SI INVIZIBILE DIN NUMELE PROGRAMELOR
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
            client = get_gspread_client()
            sheet = client.open("Sid_Email_Mirror").worksheet("Saved_Sequences")
            
            # Folosim get_all_values() în loc de records, citim strict după poziția coloanei
            rows = sheet.get_all_values()
            
            for r in rows[1:]: # Sărim peste primul rând (headerele)
                # Verificăm coloana 7 (Index 7 = Statusul "PENDING APPROVAL")
                if len(r) > 7 and str(r[7]).strip().upper() == 'PENDING APPROVAL':
                    pending_list.append({
                        "email": r[0] if len(r) > 0 else "N/A",
                        "name": r[1] if len(r) > 1 else "Untitled",
                        "program": r[2] if len(r) > 2 else "",
                        "sequence_data": r[3] if len(r) > 3 else "{}",
                        "timestamp": r[4] if len(r) > 4 else "",
                        "term_data": r[5] if len(r) > 5 else "{}",
                        "settings_data": r[6] if len(r) > 6 else "{}",
                        "status": r[7],
                        "justification": r[8] if len(r) > 8 else "",
                        "student_comments": r[9] if len(r) > 9 else "",
                        "student_id": r[10] if len(r) > 10 else "Unknown ID",
                        "student_name": r[11] if len(r) > 11 else "Student"
                    })
        except Exception as e:
            print(f"Pending List Error: {e}")
    return render_template("planner.html", programe=programs, coop_data_json=json.dumps(coop_data),
                           is_power_user=is_power_user, viewing_sid=viewing_sid, pending_list=pending_list)

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
    client = get_gspread_client()
    doc = client.open("Sid_Email_Mirror")
    
    sheet = None
    for s in doc.worksheets():
        if s.title.strip().lower() == "logins":
            sheet = s
            break
            
    if sheet is None:
        sheet = doc.add_worksheet(title="logins", rows="1000", cols="4")
        sheet.append_row(["Email", "Time", "login_code", "used"])
        
    records = sheet.get_all_values()
    now = datetime.datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"
    
    # 1. Verificăm dacă există deja un cod trimis în ultimele 30 de minute
    for i in range(len(records)-1, 0, -1):
        if records[i][0].strip().lower() == email.strip().lower() and str(records[i][3]).strip() == "0":
            try:
                req_time = datetime.datetime.strptime(records[i][1], fmt)
            except ValueError:
                continue 
                
            if (now - req_time).total_seconds() < 1800:
                time_str = req_time.strftime('%H:%M:%S')
                # Studentul a cerut un cod prea devreme, NU trimitem altul.
                session['otp_message'] = f"⚠️ A code was already sent to you at {time_str}. Please use that same code (check your spam folder). It remains valid for 30 minutes."
                session['pre_auth_email'] = email
                session['temp_sid'] = sid
                session['temp_is_guest'] = is_guest
                session['temp_guest_name'] = guest_name
                return
            else:
                # Codul este mai vechi de 30 de minute, îl marcăm ca expirat (used=1)
                sheet.update_cell(i + 1, 4, 1)

    # 2. Generăm cod NOU
    otp = str(random.randint(100000, 999999))
    
    # 3. Trimitem pe email și capturăm răspunsul de la serverul Resend
    is_sent, resend_msg = send_otp_email(email, otp)
    
    # 4. Salvăm în Google Sheets
    sheet.append_row([email, now.strftime(fmt), otp, 0])
    valid_until = (now + datetime.timedelta(minutes=30)).strftime('%H:%M:%S')
    
    if is_sent:
        # Mesajul verde de confirmare dorit
        session['otp_message'] = f"✅ {resend_msg} to {email}! Please enter the access code below. The code is valid until {valid_until}."
    else:
        # Mesajul roșu în caz că Resend e picat sau API key-ul e greșit
        session['otp_message'] = f"❌ Error sending email via Resend API: {resend_msg}"
    
    session['pre_auth_email'] = email
    session['temp_sid'] = sid
    session['temp_is_guest'] = is_guest
    session['temp_guest_name'] = guest_name

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
            
            # --- NOU: LOGAM DIRECT GUEST-UL FARA NICIUN COD ---
            session['user_email'] = email
            session['student_id'] = guest_sid
            session['is_guest'] = True
            session['guest_name'] = guest_name
            
            # Îl trimitem direct pe pagina principală (Sare peste verify)
            return redirect(url_for('index'))

    return render_template("login.html")



@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get('pre_auth_email')
    if not email: return redirect(url_for('login'))
    
    # Preluăm mesajul dinamic generat anterior
    msg = session.get('otp_message', "Please enter your access code.")

    if request.method == "POST":
        user_otp = request.form.get("otp").strip()
        
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("logins")
        records = sheet.get_all_values()
        
        now = datetime.datetime.now()
        fmt = "%Y-%m-%d %H:%M:%S"
        
        # Căutăm codul activ în sheet
        for i in range(len(records)-1, 0, -1):
            if records[i][0].strip().lower() == email and str(records[i][3]).strip() == "0":
                stored_otp = str(records[i][2]).strip()
                try:
                    req_time = datetime.datetime.strptime(records[i][1], fmt)
                except ValueError:
                    continue
                
                # Verificăm dacă a expirat între timp (verificare de siguranță)
                if (now - req_time).total_seconds() > 1800:
                    sheet.update_cell(i + 1, 4, 1) # Îl marcăm ca expirat
                    return render_template("verify.html", error="Code expired! Please request a new one.", message=msg)
                
                # Verificăm dacă a introdus codul corect
                if user_otp == stored_otp:
                    # AM ELIMINAT LINIA AICI: Nu mai marcăm cu 1 la succes! 
                    # Codul rămâne '0' pe coloana D, putând fi folosit iar în cele 30 min.
                    
                    session['user_email'] = email
                    session['student_id'] = session.get('temp_sid', '')
                    session['is_guest'] = session.get('temp_is_guest', False)
                    session['guest_name'] = session.get('temp_guest_name', '')
                    session.pop('otp_message', None) # Curățăm mesajul
                    return redirect(url_for('index'))
                else:
                    return render_template("verify.html", error="Incorrect code!", message=msg)
                    
        return render_template("verify.html", error="No valid code found or code expired. Please request a new one.", message=msg)

    return render_template("verify.html", message=msg)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route("/api/get_coop_data", methods=["POST"])
def api_get_coop_data():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    # --- NOU: Securitate Strictă! Guest-ul primește mereu obiect GOL ---
    if session.get('is_guest'): 
        return jsonify({"found": False})
        
    # Primim ID-ul studentului de la interfață și cerem excel-ul
    target_sid = str(request.json.get("student_id", "")).strip()
    coop_data = get_student_coop_data(target_sid)
    
    return jsonify(coop_data)

@app.route("/api/pending_approvals", methods=["GET"])
def get_pending_approvals():
    current_sid = str(session.get('student_id', ''))
    is_guest = session.get('is_guest', False)
    if not (current_sid.startswith('9') and not is_guest):
        return jsonify([]) # Dacă nu e Power User, returnează listă goală
        
    pending_list = []
    try:
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("Saved_Sequences")
        rows = sheet.get_all_values()
        
        for idx, r in enumerate(rows[1:], start=2): # Memoram exact randul din Excel!
            if len(r) > 7 and str(r[7]).strip().upper() == 'PENDING APPROVAL':
                pending_list.append({
                    "row_index": idx,  # <-- ADAUGAT
                    "email": r[0] if len(r) > 0 else "N/A",
                    "name": r[1] if len(r) > 1 else "Untitled",
                    "program": r[2] if len(r) > 2 else "",
                    "sequence_data": r[3] if len(r) > 3 else "{}",
                    "timestamp": r[4] if len(r) > 4 else "",
                    "term_data": r[5] if len(r) > 5 else "{}",
                    "settings_data": r[6] if len(r) > 6 else "{}",
                    "student_id": r[10] if len(r) > 10 else "Unknown ID",
                    "student_name": r[11] if len(r) > 11 else "Student"
                })
    except Exception as e:
        print(f"Pending List Error: {e}")
        
    # NOU: Sortăm descrescător după timestamp
    pending_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
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
        student_comments = data.get('student_comments', '')
        
        # ... existing save_sequence code ...
        # Identificăm cine face salvarea
        current_user_id = str(session.get('student_id', ''))
        is_guest = session.get('is_guest', False)
        is_power_user = current_user_id.startswith('9') and not is_guest
        student_name_ui = data.get('student_name', '').strip()
        if is_guest:
            current_name = f"GUEST - {session.get('guest_name', '')}"
        else:
            current_name = student_name_ui if student_name_ui else "Official Student"
        
        # ... Codul de identificare a utilizatorului rămâne la fel ...
        email_to_save = session['user_email']
        client = get_gspread_client()
        
        # --- REQUIREMENT 3: Find real student email AND change sequence name ---
        if is_power_user and target_id != current_user_id:
            # MODIFICARE AICI: Folosim helper-ul 
            email_to_save = get_student_email(target_id, fallback_email=session['user_email'])
                
            # Override the name of the sequence
            power_user_name = session.get('guest_name', 'Coordinator') if is_guest else session.get('user_email').split('@')[0]
            name = f"Submitted on {datetime.datetime.now().strftime('%Y-%m-%d')} by {power_user_name}"
            current_name = "ADMIN (PowerUser)"
        
        sheet = client.open("Sid_Email_Mirror").worksheet("Saved_Sequences")
        timestamp = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        sheet.append_row([email_to_save, name, program, seq_json, timestamp, term_json, settings_json, status, justification, student_comments, target_id, current_name])
        
        # 2. Trimitem E-mailul daca este Submit Oficial
        if status == "PENDING APPROVAL":
            try:
                recipients = get_email_recipients(program, target_id, email_to_save, "SUBMIT")
                
                # --- NOU: Preluăm sumarul trimis de pe frontend ---
                wt_summary = data.get('wt_summary', {})
                term_summary = data.get('term_summary', [])
                
                wt_html = ""
                for wt in ["WT1", "WT2", "WT3"]:
                    if wt in wt_summary:
                        info = wt_summary[wt]
                        change_text = f"<span style='color:red; font-weight:bold;'>changed from ({info['original']})</span>" if info['changed'] else "<span style='font-weight:bold;'>NO CHANGE</span>"
                        wt_html += f"<p style='margin: 4px 0;'><b>{wt}:</b> {info['new_term']} - {change_text}</p>"
                
                terms_html = ""
                if term_summary:
                    terms_html += "<table style='width: 100%; border-collapse: collapse; margin-top: 15px; font-family: Arial, sans-serif; font-size: 13px;'>"
                    terms_html += "<thead><tr style='background-color: #34495e; color: white;'><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 16%;'>Year</th><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Summer</th><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Fall</th><th style='padding: 10px; border: 1px solid #ddd; text-align: center; width: 28%;'>Winter</th></tr></thead>"
                    terms_html += "<tbody>"
                    
                    for ts in term_summary:
                        year_str = ts.get('year', '')
                        data_term = ts.get('data', {})
                        
                        terms_html += "<tr>"
                        terms_html += f"<td rowspan='2' style='padding: 10px; border: 1px solid #ddd; vertical-align: middle; background-color: #f8f9fa; text-align: center; font-weight: bold;'>{year_str}</td>"
                        
                        for t in ["SUM", "FALL", "WIN"]:
                            t_data = data_term.get(t, {})
                            cr = t_data.get('cr', 0)
                            wt_change = t_data.get('wt_change', '')
                            wt_note_html = f"<br><span style='color: #c0392b; font-size: 11px;'>{wt_change}</span>" if wt_change else ""
                            terms_html += f"<td style='padding: 5px; border: 1px solid #ddd; text-align: center; font-weight: bold; background-color: #fcfcfc;'>{cr} CR{wt_note_html}</td>"
                        terms_html += "</tr><tr>"
                        
                        for t in ["SUM", "FALL", "WIN"]:
                            t_data = data_term.get(t, {})
                            courses = t_data.get('courses', [])
                            courses_html = ""
                            for c in courses:
                                if c.get('is_wt'):
                                    courses_html += f"<div style='background-color: #d5f5e3; font-weight: bold; padding: 4px; border-radius: 4px; color: #27ae60; border: 1px solid #abebc6; margin-bottom: 3px; text-align: center;'>{c.get('name')}</div>"
                                else:
                                    courses_html += f"<div style='margin-bottom: 2px; text-align: center;'>{c.get('name')} <span style='font-size: 11px; color: #7f8c8d;'>({c.get('credit')} cr)</span></div>"
                            terms_html += f"<td style='padding: 10px; border: 1px solid #ddd; vertical-align: top;'>{courses_html}</td>"
                        terms_html += "</tr>"
                        
                    terms_html += "</tbody></table>"

                # Incorporăm totul în HTML-ul E-mailului de Submit
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
                    
                    <p><b>Validation Warnings & Student Justification:</b><br>
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
                    "subject": f"Sequence Approval Requested for {target_id} ({program})",
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
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("Saved_Sequences")
        raw_rows = sheet.get_all_values() 
        
        current_sid = str(session.get('student_id', ''))
        is_power_user = current_sid.startswith('9') and not session.get('is_guest', False)
        viewing_sid = str(session.get('admin_view_sid', current_sid)).strip()
        target_email = session['user_email'].lower().strip()
        
        my_recs = []
        for row in raw_rows[1:]:
            if len(row) == 0: continue
            row_email = str(row[0]).lower().strip()
            row_sid = str(row[10]).strip() if len(row) > 10 else ""
            
            # Daca e admin, filtreaza dupa studentul vizualizat. Daca e student, dupa email!
            is_match = False
            if is_power_user and viewing_sid and viewing_sid != "ADMIN":
                if row_sid == viewing_sid: is_match = True
            else:
                if row_email == target_email: is_match = True
                
            if is_match:
                def safe_json(idx):
                    if len(row) > idx and row[idx].strip():
                        try: return json.loads(row[idx])
                        except: return {}
                    return {}
                my_recs.append({
                    "Sequence_Name": row[1] if len(row) > 1 else "Untitled",
                    "Program": row[2] if len(row) > 2 else "",
                    "Date_Saved": row[4] if len(row) > 4 else "",
                    "JSON_Data": safe_json(3), "Term_Data": safe_json(5), "Settings_Data": safe_json(6),
                    "Status": row[7] if len(row) > 7 else "",
                    "Student_ID": row_sid,
                    "Student_Name": row[11] if len(row) > 11 else ""
                })
                
        my_recs.sort(key=lambda x: x.get('Date_Saved', ''), reverse=True)
        return jsonify({"sequences": my_recs}) 
    except Exception as e:
        print(f"Load Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/get_transcript", methods=["POST"])
def get_transcript():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    target_id = request.json.get("student_id", "").strip()
    
    if session.get('is_guest'):
        guest_name = session.get('guest_name', 'Unknown')
        return jsonify({"transcript": [], "student_name": f"GUEST - {guest_name}", "suggested_program": ""})

    if not target_id or target_id == "ADMIN": 
        return jsonify({"transcript": [], "student_name": "", "suggested_program": ""})

    try:
        client = get_gspread_client()
        sheet = client.open("Sid_Email_Mirror").worksheet("Transcripts")
        
        # 1. Citim DOAR primul rând pentru Headere
        headers = [str(h).strip() for h in sheet.row_values(1)]
        
        try:
            idx_sid = headers.index('Student ID')
            idx_course = headers.index('COURSE')
            idx_term = headers.index('Academic Term')
            idx_grade = headers.index('GRADE')
            idx_cred = headers.index('CREDVAL') if 'CREDVAL' in headers else -1
            idx_name = headers.index('NAME') if 'NAME' in headers else -1
            idx_prog = headers.index('PROG_LINK') if 'PROG_LINK' in headers else -1
            idx_disc = headers.index('DISCIPLINE1_DESCR') if 'DISCIPLINE1_DESCR' in headers else -1
        except ValueError:
            return jsonify({"transcript": [], "student_name": "", "suggested_program": ""})

        # 2. Descărcăm DOAR coloana cu ID-uri (rapid și nu consumă RAM)
        all_sids = sheet.col_values(idx_sid + 1)
        
        # 3. Găsim rândurile unde apare studentul nostru
        matching_rows = []
        for i, sid in enumerate(all_sids):
            if str(sid).strip() == target_id:
                matching_rows.append(i + 1) # gspread folosește rânduri începând de la 1
                
        if not matching_rows:
            return jsonify({"transcript": [], "student_name": "", "suggested_program": ""})

        # 4. Cerem de la Google FIX rândurile studentului
        ranges = [f"A{r}:Z{r}" for r in matching_rows]
        raw_results = sheet.batch_get(ranges)

        my_courses = []
        student_name = ""
        last_prog_link = ""
        last_disc = ""

        # Iterăm prin rândurile primite direct de la server
        for res in raw_results:
            if not res or not res[0]: continue
            row = res[0]
            
            # În caz că rândul e mai scurt pentru că ultimele celule erau goale
            row.extend([""] * (len(headers) - len(row)))

            if not student_name and idx_name != -1 and len(row) > idx_name:
                student_name = str(row[idx_name]).strip()
            
            if idx_prog != -1 and len(row) > idx_prog:
                val_prog = str(row[idx_prog]).strip().upper()
                if val_prog: last_prog_link = val_prog
                
            if idx_disc != -1 and len(row) > idx_disc:
                val_disc = str(row[idx_disc]).strip().upper()
                if val_disc: last_disc = val_disc
            
            cred_val = 0.0
            if idx_cred != -1 and len(row) > idx_cred:
                try: cred_val = float(str(row[idx_cred]).strip())
                except ValueError: cred_val = 0.0

            my_courses.append({
                "course": str(row[idx_course]).strip().replace(" ", "").upper(),
                "term": str(row[idx_term]).strip(),
                "grade": str(row[idx_grade]).strip() if len(row) > idx_grade else "",
                "credit": cred_val
            })

        # Logica de deducere a programului
        suggested_program = ""
        last_prog_link_upper = last_prog_link.upper()
        last_disc_upper = last_disc.upper()
        
        if "UGRD" in last_prog_link_upper:
            if "AERODY" in last_disc_upper: suggested_program = "AERODYNAMICS"
            elif "STRUCTURES" in last_disc_upper: suggested_program = "STRUCTURES"
            elif "AVIONICS" in last_disc_upper: suggested_program = "AVIONICS"
            elif "MECH" in last_disc_upper: suggested_program = "MECHANICAL"
            elif "INDU" in last_disc_upper: suggested_program = "INDUSTRIAL"
        elif "GRAD" in last_prog_link_upper:
            if "MECH" in last_disc_upper: suggested_program = "MECHANICAL GRAD"
            elif "INDU" in last_disc_upper: suggested_program = "INDUSTRIAL GRAD"

        return jsonify({
            "transcript": my_courses, 
            "student_name": student_name, 
            "suggested_program": suggested_program
        })
    except Exception as e:
        print("Transcript fetch error:", e)
        return jsonify({"transcript": [], "student_name": "", "suggested_program": ""})

    
@app.route("/get_courses", methods=["POST"])
def get_courses():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    df_prog = load_data()
    
    # 1. NORMALIZEAZA COLOANELE
    df_prog.columns = [str(c).strip().upper() for c in df_prog.columns]
    
    # 2. NORMALIZEAZA PROGRAMUL CERUT DE FRONTEND (sterge spatiile duble)
    program_name = request.json.get('program', '').strip()
    program_name = " ".join(program_name.split()) 
    
    if 'PROGRAM' in df_prog.columns:
        # NORMALIZEAZA DATELE DIN EXCEL
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
        
        # Combinam verile citind coloanele normalizate
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
    # Stergem spatiile duble din numele venit de la browser
    program_name = " ".join(data.get('program', '').strip().upper().split())
    
    term_limits = data.get('term_limits', {})
    count_limits = data.get('count_limits', {})
    placed_ui = data.get('placed', {})
    unallocated_ids = data.get('unallocated', [])

    df = load_data()
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # Filtrare blindată: stergem spatiile duble si din Excel inainte de comparare
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

    # --- LOGICA PENTRU CURSURI REPETATE ---
    rep_counts = defaultdict(int)
    for cid in data.get('repeated', []):
        if cid in all_courses_dict:
            rep_counts[cid] += 1
            count = rep_counts[cid]
            rep_id = f"REP{count}_{cid}"
            
            # Denumire cu REPEATED
            suffix = f" {count}" if count > 1 else ""
            dummy = all_courses_dict[cid].copy()
            dummy['COURSE'] = f"{str(dummy['COURSE'])} REPEATED{suffix}"
            #dummy['CORE_TE'] = "REPEAT"
            dummy['_id'] = rep_id 
            
            # Repetarea 2 cere Repetarea 1
            dummy['PRE-REQUISITE'] = f"REP{count-1}_{cid}" if count > 1 else ""
            all_courses_dict[rep_id] = dummy
            
            # 1. Cursul original trebuie sa astepte dupa aceasta repetare
            orig_prq = str(all_courses_dict[cid].get('PRE-REQUISITE', ''))
            if orig_prq and orig_prq.lower() not in ['n/a', 'none']:
                all_courses_dict[cid]['PRE-REQUISITE'] = orig_prq + "; " + rep_id
            else:
                all_courses_dict[cid]['PRE-REQUISITE'] = rep_id

            # 2. Orice ALT curs care depindea de original, va depinde acum SI de repetare
            for other_cid, c_data in all_courses_dict.items():
                if other_cid != cid and other_cid != rep_id:
                    other_prq = str(c_data.get('PRE-REQUISITE', ''))
                    if other_prq and other_prq.lower() not in ['n/a', 'none']:
                        # Folosim regex pentru a gasi cursul original in text (ex: INDU320)
                        if re.search(rf'\b{cid}\b', other_prq):
                            c_data['PRE-REQUISITE'] = other_prq + "; " + rep_id
    
    # Folosim o singura cutie pentru SUM, la fel ca in frontend, si adaugam sertarul 'coduri'
    sequence_dict = {str(i): {t: {"credite": 0, "cursuri": [], "coduri": set()} for t in ["SUM", "FALL", "WIN"]} for i in range(1, 8)}

    for tk, cids in placed_ui.items():
        if not cids: continue
        if "Y0" in tk:
            for cid in cids: taken_courses.add(cid); placements[cid] = (0, 'ANY', -1)
            continue
        y_str = tk.split("_")[0]; t = tk.split("_")[1]; y = int(y_str[1:])
        # NOU: Orice variatie de SUM1 sau SUM2 devine automat SUM
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
                
                # MODIFICAT: Folosim noul sistem de 3 semestre (index de la 0 la 2)
                placements[cid] = (str(y), t, (int(y) - 1) * 3 + ["SUM", "FALL", "WIN"].index(t))

    remaining = set(c for c in unallocated_ids if c in all_courses_dict and c not in taken_courses)
    for cid in data.get('repeated', []):
        rep_id = "REP_" + cid
        if rep_id in all_courses_dict and rep_id not in taken_courses: remaining.add(rep_id)

    # =========================================================
    # --- 1. PRE-CHECK: VERIFICĂRI WORK TERMS (ÎNAINTE DE AI) ---
    # =========================================================
    unallocated_wts = [c for c in unallocated_ids if 'WT' in c.upper()]
    if unallocated_wts:
        return jsonify({"error": "Please place all Work Terms (WT) on the grid before generating."})
        
    all_wts_in_prog = sorted([c for c in all_courses_dict.keys() if 'WT' in c.upper()])
    
    if all_wts_in_prog:
        # Obținem indecșii unde au fost plasate WT-urile
        placed_wt_indices = sorted([placements[wt][2] for wt in all_wts_in_prog if wt in placements])
        
        # =========================================================
    # --- 1. PRE-CHECK: VERIFICĂRI WORK TERMS (ÎNAINTE DE AI) ---
    # =========================================================
    unallocated_wts = [c for c in unallocated_ids if 'WT' in c.upper()]
    if unallocated_wts:
        return jsonify({"error": "Please place all Work Terms (WT) on the grid before generating."})
        
    all_wts_in_prog = sorted([c for c in all_courses_dict.keys() if 'WT' in c.upper()])
    
    if all_wts_in_prog:
        # Obținem indecșii și termenele (SUM/FALL/WIN) unde au fost plasate WT-urile
        placed_wt_indices = sorted([placements[wt][2] for wt in all_wts_in_prog if wt in placements])
        
        # REGULA: Fără 3 termene consecutive de WT
        #for i in range(len(placed_wt_indices) - 2):
        #    if placed_wt_indices[i+2] - placed_wt_indices[i] == 2:
        #        return jsonify({"error": "You cannot have 3 consecutive Work Terms. Please adjust them."})

        # REGULA NOUĂ: Fără 3 WT-uri plasate în Summer
        #summer_wts = sum(1 for wt in all_wts_in_prog if wt in placements and placements[wt][1] == 'SUM')
        #if summer_wts >= 3:
        #    return jsonify({"error": "You cannot have 3 Work Terms in the Summer semester. Please move at least one to Fall or Winter."})
                
        # REGULA: Cel puțin 2 termene înainte de primul WT (raportat la grilă)
        #first_wt = all_wts_in_prog[0]
        #if first_wt in placements:
        #   if placements[first_wt][2] < 2:
        #        return jsonify({"error": "There must be at least 2 study terms before your first Work Term."})
    # =========================================================
    # =========================================================


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
    # NOU pentru AERO: Caută cuvinte cheie din numele pe care le vei pune în Excel
    elif "AERO A" in prog_upper or "AERODYNAMICS" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_A", {})
    elif "AERO B" in prog_upper or "STRUCTURES" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_B", {})
    elif "AERO C" in prog_upper or "AVIONICS" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_C", {})
    elif "AERO" in prog_upper: std_prog = STANDARD_SEQUENCES.get("AERO_A", {}) # Fallback generic

    def get_std_idx(cid):
        # Cautam indexul standard pe noul sistem de 3 trimestre (0-20)
        pos_str = std_prog.get(cid, "") # <--- AICI ERA PROBLEMA (standard_seq in loc de std_prog)
        if not pos_str: return 999
        try:
            parts = pos_str.split('_')
            y = int(parts[0].replace('Y', ''))
            t = parts[1]
            if "SUM" in t: t = "SUM" # Absoarbe orice variatie de SUM din STANDARD_SEQUENCES
            if t in ["SUM", "FALL", "WIN"]:
                return (y - 1) * 3 + ["SUM", "FALL", "WIN"].index(t)
        except: pass
        return 999

    def place_temporarily(cid, idx):
        # Impartirea inteligenta la 3
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
    
    
    def is_valid_slot(cid, idx, ignore_offering=False): # <-- Adăugat parametrul aici
        # 1. Impartim la 3 (pentru SUM, FALL, WIN)
        y = (idx // 3) + 1
        t = ["SUM", "FALL", "WIN"][idx % 3]
        
        if y > 7: return False
        
        c_data = all_courses_dict.get(cid, {})
        
        # 2. Verificam daca e oferit in acest trimestru (cautam in Excel)
        if not ignore_offering: # <-- Folosim parametrul
            if t == "SUM":
                # Verificăm dacă e oferit în oricare variantă de vară din Excel
                is_offered = (str(c_data.get('SUM 1', '')).strip().upper() == 'X' or 
                              str(c_data.get('SUM 2', '')).strip().upper() == 'X' or
                              str(c_data.get('SUM', '')).strip().upper() == 'X')
            else:
                is_offered = str(c_data.get(t, '')).strip().upper() == 'X'
                
            # AICI ERA PROBLEMA: Daca nu e oferit, trebuie sa ii spunem AI-ului sa se opreasca!
            if not is_offered: 
                return False
        
        is_wt_c = 'WT' in cid.upper()
        is_rep_c = str(c_data.get('CORE_TE', '')).upper() == 'REPEAT'
        cr = 0.0 if (is_wt_c or is_rep_c) else float(c_data.get('CREDIT', 0) or 0)
        target = sequence_dict[str(y)][t]
        
        term_has_wt = any('WT' in str(cx.get('COURSE', '')).upper() for cx in target["cursuri"])
        
        # 3. Nu permitem unui curs sa se aseze peste un WT (si invers)
        if term_has_wt and not is_wt_c and len(target["cursuri"]) >= 1: return False
        if is_wt_c and len(target["cursuri"]) > 0: return False

        # 4. Limitele noi (16 cr / 6 cursuri pentru vara, 18 / 5 pentru restul)
        l_cr = float(term_limits.get(f"Y{y}_{t}", 16.0 if t == 'SUM' else 18.0))
        l_cnt = int(count_limits.get(f"Y{y}_{t}", 6 if t == 'SUM' else 5))
        
        if l_cr == 0 or l_cnt == 0: return False

        if not is_wt_c and not is_rep_c:
            if target["credite"] + cr > l_cr: return False
            if len(target["cursuri"]) >= l_cnt: return False

        # 5. Reguli de pre-requisites nivel 200 vs 400
        if get_level(cid) >= 4:
            for k in taken_courses:
                if get_level(k) == 2 and placements[k][2] >= idx: return False
        if get_level(cid) == 2:
            for k in taken_courses:
                if get_level(k) >= 4 and placements[k][2] <= idx: return False

        # 6. Reguli stricte Capstone (490A obligatoriu toamna, 490B obligatoriu iarna)
        if '490B' in cid and t != 'WIN': return False
        if '490A' in cid and t != 'FALL': return False
        if '490A' in cid:
            req_490b = cid.replace('490A', '490B')
            if req_490b in placements:
                if idx != placements[req_490b][2] - 1: return False
                
        return True
    

    def solve_branch(cid, max_allowed_idx, depth):
            # NOU: Preventie impotriva infinite loops la pre-requisites incrucisate
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

    # --- Bucla de limitare la 120 credite ---
    while True:
        # NOU: Folosim "SUM", "FALL", "WIN"
        total_cr = sum(float(c.get('CREDIT', 0) or 0) for y in range(1, 8) for t in ["SUM", "FALL", "WIN"] for c in sequence_dict[str(y)][t]["cursuri"] if str(c.get('CORE_TE', '')).strip().upper() not in ['REPEAT', 'ECP'] and 'WT' not in str(c['COURSE']).upper())
        if total_cr <= 120: break
        
        removed_any = False
        for y in range(7, 0, -1):
            # NOU: Folosim "WIN", "FALL", "SUM" in ordine inversa
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

    # =========================================================
    # --- 2. POST-CHECK: VALIDARE CREDITE MINIME ---
    # =========================================================
    warning_msgs = []
    
    if all_wts_in_prog:
        # REGULA: 30 CR (CORE/PROG/TE) înainte de primul WT
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
                
        # REGULA: Full-Time (>= 12 CR) înainte de ULTIMUL WT
        last_wt = all_wts_in_prog[-1]
        if last_wt in placements:
            last_wt_idx = placements[last_wt][2]
            prev_idx = last_wt_idx - 1
            if prev_idx >= 0:
                p_y = (prev_idx // 3) + 1
                p_t = ["SUM", "FALL", "WIN"][prev_idx % 3]
                
                # Excepția 1: Fără limită de 12CR dacă termenul precedent este Summer
                if p_t != "SUM":
                    # Excepția 2: Fără limită dacă termenul precedent este tot un WT
                    prev_has_wt = any('WT' in str(c.get('COURSE', '')).upper() for c in sequence_dict[str(p_y)][p_t]["cursuri"])
                    
                    if not prev_has_wt:
                        # Calculăm totalul de credite valide în acel termen anterior
                        prev_cr = sum(float(c.get('CREDIT', 0) or 0) for c in sequence_dict[str(p_y)][p_t]["cursuri"] if 'WT' not in str(c.get('COURSE', '')).upper())
                        if prev_cr < 12.0:
                            warning_msgs.append(f"Term before {last_wt} must be Full-Time (≥ 12 credits). Currently has {prev_cr} CR.")

    # --- Construim raspunsul final de trimis catre Javascript ---

    # --- Construim raspunsul final de trimis catre Javascript ---
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

    # Formatam cursurile ramase (unallocated)
    unalloc_list = [{"id": c, "display": all_courses_dict[c]["COURSE"]} for c in remaining if c in all_courses_dict]
    
    # NOU: Returnam efectiv rezultatul catre browser! (Aceasta linie lipsea din ultimul tau fisier)
    return jsonify({"sequence": res_seq, "unallocated": unalloc_list, "warnings": warning_msgs})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True, use_reloader=False)