import os
import random
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import re
from collections import defaultdict

# Sus de tot, asigura-te ca ai import os (deja il ai)

# Modifică secțiunea de setări email așa:
EMAIL_SENDER = "concordia.sequnce.planner@gmail.com" 
# Serverul va lua parola dintr-un seif digital (os.environ), dar dacă nu o găsește, o va folosi pe cea locală
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "hpvdhzdjllmkczfc")

app = Flask(__name__)
app.secret_key = "SVsecretKEY" 

# ==========================================
# SETĂRI EMAIL
# ==========================================
#EMAIL_SENDER = "concordia.sequnce.planner@gmail.com" 
#EMAIL_PASSWORD = "hpvdhzdjllmkczfc" 

pending_otps = {}

# ==========================================
# FUNCȚII AUTENTIFICARE & EMAIL
# ==========================================
def verify_email_in_sheets(email):
    base_path = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_path, "cheie_google.json")
    scop = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scop)
        client = gspread.authorize(creds)
        sheet = client.open("Baza Date COOP").sheet1
        datele = sheet.get_all_records()
        
        for rand in datele:
            if str(rand.get('Email', '')).strip().lower() == email.strip().lower():
                return True
        return False
    except Exception as e:
        print(f"Eroare la conectarea cu Google Sheets: {e}")
        return False

def send_otp_email(destinatar, otp):
    subiect = "Codul tău de acces pentru Academic Planner COOP"
    corp_mesaj = f"Salut,\n\nCodul tău de conectare este: {otp}\n\nAcest cod este valabil 5 minute."
    msg = MIMEText(corp_mesaj)
    msg['Subject'] = subiect
    msg['From'] = EMAIL_SENDER
    msg['To'] = destinatar

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, destinatar, msg.as_string())
        return True
    except Exception as e:
        print(f"Eroare la trimiterea emailului: {e}")
        return False

# ==========================================
# FUNCȚII AJUTĂTOARE DATE 
# ==========================================
def incarca_date():
    base_path = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(base_path, "CORE_TE.xlsx")
    try:
        df = pd.read_excel(excel_path)
        df.columns = [str(c).strip() for c in df.columns] 
        return df.fillna("")
    except Exception as e:
        print(f"Eroare la citirea Excel: {e}")
        return pd.DataFrame()

def extrage_cod(nume_curs):
    if not nume_curs: return ""
    match = re.search(r'[A-Z]{3,4}\s?\d{3}[A-Z]?|WT\d', str(nume_curs).upper())
    return match.group(0).replace(" ", "") if match else str(nume_curs).strip().upper()

def get_level(nume_curs):
    match = re.search(r'(\d)\d{2}', str(nume_curs))
    return int(match.group(1)) if match else 9

def parse_reqs(req_str):
    if not req_str or str(req_str).lower() in ['n/a', 'none', '']: return []
    cerinte = []
    grupuri_si = re.split(r'[;,]', str(req_str))
    for grup in grupuri_si:
        opt_sau = re.split(r'\bor\b', grup, flags=re.IGNORECASE)
        opt_curate = []
        for o in opt_sau:
            m = re.search(r'[A-Z]{3,4}\s\d{3}[A-Z]?', o.upper())
            if m: opt_curate.append(m.group(0).replace(" ", ""))
        if opt_curate: cerinte.append(opt_curate)
    return cerinte

# ==========================================
# RUTE DE LOGIN
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
            else:
                return render_template("login.html", error="Eroare la trimiterea emailului.")
        else:
            return render_template("login.html", error="Email neautorizat.")
    return render_template("login.html")

@app.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get('pre_auth_email')
    if not email: return redirect(url_for('login'))
    if request.method == "POST":
        user_otp = request.form.get("otp").strip()
        core_otp = pending_otps.get(email)
        if core_otp and user_otp == core_otp:
            session['user_email'] = email
            pending_otps.pop(email, None)
            return redirect(url_for('index'))
        else:
            return render_template("verify.html", error="Cod incorect!")
    return render_template("verify.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# RUTE PLANNER (Protejate)
# ==========================================
@app.route("/", methods=["GET"])
def index():
    if 'user_email' not in session: return redirect(url_for('login'))
    
    df = incarca_date()
    if df.empty: 
        return "Eroare: Fisierul CORE_TE.xlsx nu a fost gasit sau nu poate fi citit."
    programe = sorted(df['Program'].apply(lambda x: str(x).strip()).unique().tolist())
    return render_template("planner.html", programe=programe)

@app.route("/get_courses", methods=["POST"])
def get_courses():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    program_name = data.get('program').strip()
    df = incarca_date()
    df_prog = df[df['Program'].str.strip() == program_name]

    reverse_deps = defaultdict(lambda: {"is_prereq_for": set(), "is_coreq_for": set()})
    for _, row in df_prog.iterrows():
        cid_curent = extrage_cod(row['COURSE'])
        for req_match in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?', str(row.get('PRE-REQUISITE', '')).upper()):
            req_code = req_match.replace(" ", "").replace("-", "")
            reverse_deps[req_code]["is_prereq_for"].add(cid_curent)
        for req_match in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?', str(row.get('CO-REQUISITE', '')).upper()):
            req_code = req_match.replace(" ", "").replace("-", "")
            reverse_deps[req_code]["is_coreq_for"].add(cid_curent)

    toate_cursurile = []
    pre_placed = defaultdict(list)
    def safe_str(val): return "" if str(val).strip().lower() == 'nan' else str(val).strip()

    for _, row in df_prog.iterrows():
        cid = extrage_cod(row['COURSE'])
        term_sugerat = safe_str(row.get('Course to place in q1', ''))
        terms_offered = [t for t, col in zip(['Fall', 'Winter', 'Sum 1', 'Sum 2'], ['FALL', 'WIN', 'SUM 1', 'SUM 2']) if safe_str(row.get(col, '')).upper() == 'X']

        toate_cursurile.append({
            "id": cid, "display": f"{safe_str(row['COURSE'])} ({row.get('CREDIT', 0)} cr)",
            "credit": float(row.get('CREDIT', 0) or 0), "is_wt": 'WT' in safe_str(row['COURSE']).upper(),
            "is_ecp": safe_str(row.get('CORE_TE', '')).upper() == 'ECP',
            "full_name": safe_str(row['COURSE']), "type": safe_str(row.get('CORE_TE', '')),
            "terms": ", ".join(terms_offered) if terms_offered else "N/A",
            "prereqs": safe_str(row.get('PRE-REQUISITE', '')), "coreqs": safe_str(row.get('CO-REQUISITE', '')),
            "is_prereq_for": ", ".join(reverse_deps[cid]["is_prereq_for"]) or "None",
            "is_coreq_for": ", ".join(reverse_deps[cid]["is_coreq_for"]) or "None"
        })

        if term_sugerat:
            term_up = term_sugerat.upper()
            t_str = 'FALL' if 'FALL' in term_up else 'WIN' if 'WIN' in term_up else 'SUM1' if 'SUM 1' in term_up or 'SUM1' in term_up or 'SUM' in term_up else 'SUM2' if 'SUM 2' in term_up or 'SUM2' in term_up else None
            m_year = re.search(r'(\d)', term_up)
            y_str = m_year.group(1) if m_year else None
            if t_str and y_str: pre_placed[f"Y{y_str}_{t_str}"].append(cid)

    return jsonify({"courses": toate_cursurile, "pre_placed": dict(pre_placed)})

@app.route("/generate", methods=["POST"])
def generate():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    program_name = data.get('program').strip()
    term_limits = data.get('term_limits', {})
    count_limits = data.get('count_limits', {})
    placed_ui = data.get('placed', {})
    unallocated_ids = data.get('unallocated', [])

    df = incarca_date()
    df_prog = df[df['Program'].str.strip() == program_name]
    
    toate_dict = {extrage_cod(row['COURSE']): row for row in df_prog.to_dict('records') if str(row.get('CORE_TE', '')).strip().upper() != 'ECP'}
    luate = set([extrage_cod(row['COURSE']) for row in df_prog.to_dict('records') if str(row.get('CORE_TE', '')).strip().upper() == 'ECP'])
    
    secventa = {f"Y{y}": {t: {"cursuri": [], "credite": 0.0, "coduri": set()} for t in ["SUM1", "SUM2", "FALL", "WIN"]} for y in range(1, 8)}
    plasamente = {}

    def get_term_index(y, t): return y * 4 + ["SUM1", "SUM2", "FALL", "WIN"].index(t)

    for tk, cids in placed_ui.items():
        if "Y0" in tk or not cids: continue
        y_str, t = tk.split("_")
        y = int(y_str[1:])
        for cid in cids:
            if cid in toate_dict:
                c = toate_dict[cid]
                secventa[y_str][t]["cursuri"].append(c)
                secventa[y_str][t]["credite"] += float(c.get('CREDIT', 0) or 0)
                secventa[y_str][t]["coduri"].add(cid)
                luate.add(cid)
                plasamente[cid] = (y, t, get_term_index(y, t))

    remaining = [cid for cid in unallocated_ids if cid in toate_dict]

    def get_reqs(cid, req_type): return parse_reqs(toate_dict[cid].get(req_type, '')) if cid in toate_dict else []

    memo_depth = {}
    def calc_depth(cid):
        if cid in memo_depth: return memo_depth[cid]
        if cid not in toate_dict: return 0
        pre_groups = get_reqs(cid, 'PRE-REQUISITE')
        if not pre_groups:
            memo_depth[cid] = 1; return 1
        max_d = 0
        for group in pre_groups:
            group_max = max((calc_depth(opt) for opt in group if opt in toate_dict), default=0)
            if group_max > max_d: max_d = group_max
        depth = 1 + max_d
        memo_depth[cid] = depth
        return depth

    for cid in toate_dict: calc_depth(cid)
    remaining.sort(key=lambda x: (memo_depth.get(x, 0), get_level(x)), reverse=True)

    def place_course(cid):
        if cid in luate: return True
        if cid not in toate_dict: return False

        c_data = toate_dict[cid]
        cr = float(c_data.get('CREDIT', 0) or 0)

        pre_groups = get_reqs(cid, 'PRE-REQUISITE')
        min_term_index = -1 

        for group in pre_groups:
            plasat_grup = False
            for opt in group:
                if opt in luate:
                    min_term_index = max(min_term_index, plasamente.get(opt, (0, '', -1))[2])
                    plasat_grup = True; break
            if not plasat_grup:
                for opt in group:
                    if opt in toate_dict:
                        if place_course(opt):
                            min_term_index = max(min_term_index, plasamente.get(opt, (0, '', -1))[2])
                            plasat_grup = True; break
                    else:
                        plasat_grup = True; break
            if not plasat_grup: return False

        start_idx = max(0, min_term_index + 1)

        if get_level(cid) >= 4:
            for k2 in list(toate_dict.keys()):
                if get_level(k2) == 2 and k2 not in luate: place_course(k2)
            idx200 = max([plasamente.get(k, (0,'',-1))[2] for k in luate if get_level(k) == 2], default=-1)
            start_idx = max(start_idx, idx200 + 1)

        for idx in range(start_idx, 7*4): 
            y = (idx // 4) + 1
            if y > 7: break
            t = ["SUM1", "SUM2", "FALL", "WIN"][idx % 4]
            target = secventa[f"Y{y}"][t]

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
                if not any((r in luate and plasamente.get(r, (0,'',999))[2] <= idx) for r in c_grp):
                    co_placed = False
                    for r in c_grp:
                        if r in toate_dict:
                            if place_course(r) and plasamente.get(r, (0,'',999))[2] <= idx:
                                co_placed = True; break
                        else:
                            co_placed = True; break 
                    if not co_placed: co_ok = False; break
            if not co_ok: continue

            if '490A' in cid and t != 'FALL': continue
            if '490B' in cid:
                if t != 'WIN': continue
                idx_490a = plasamente.get(cid.replace('490B', '490A'), (0,'',-1))[2]
                if idx != idx_490a + 1: continue

            target["cursuri"].append(c_data)
            target["credite"] += cr
            target["coduri"].add(cid)
            luate.add(cid)
            plasamente[cid] = (y, t, idx)
            if cid in remaining: remaining.remove(cid)
            return True

        return False

    for c in list(remaining): place_course(c)

    res_seq = {f"Year {y}": {t: {"credite": secventa[f"Y{y}"][t]["credite"], "cursuri": [{"id": extrage_cod(c['COURSE']), "display": f"{str(c['COURSE']).strip()} ({c.get('CREDIT',0)} cr)", "is_wt": 'WT' in str(c['COURSE']).upper()} for c in secventa[f"Y{y}"][t]["cursuri"]]} for t in ["SUM1", "SUM2", "FALL", "WIN"]} for y in range(1, 8)}
    
    return jsonify({"sequence": res_seq, "unallocated": [{"id": cid, "display": toate_dict[cid]['COURSE']} for cid in remaining]})

if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)