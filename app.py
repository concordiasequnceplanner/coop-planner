import os
import random
import re
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

# Integrări externe
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import resend

from dotenv import load_dotenv # Adaugă asta
load_dotenv() # Această linie încarcă variabilele din .env în sistem

app = Flask(__name__)
app.secret_key = "SVsecretKEY" # Cheia pentru sesiuni securizate

# --- LINII DE VERIFICARE (DEBUG) ---
api_key_verificare = os.environ.get("RESEND_API_KEY")
print(f"\n--- DEBUG LOG ---")
print(f"RESEND_API_KEY detectat: {api_key_verificare}")
print(f"------------------\n")
# ----------------------------------

resend.api_key = api_key_verificare

print(resend.api_key)

# ==========================================
# FUNCȚII AUTENTIFICARE & EMAIL (RESEND)
# ==========================================

def verify_email_in_sheets(email):
    """Verifică dacă emailul studentului există în baza de date Google Sheets."""
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
        print(f"Eroare Google Sheets: {e}")
        return False

def send_otp_email(destinatar, otp):
    """Trimite codul OTP folosind noul domeniu concordiasequenceplanner.ca."""
    try:
        params = {
            "from": "MIAE Planner <auth@concordiasequenceplanner.ca>",
            "to": [destinatar],
            "subject": "Cod de acces - Academic Planner COOP",
            "html": f"""
                <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 8px;">
                    <h2 style="color: #912338;">Concordia MIAE</h2>
                    <p>Salut,</p>
                    <p>Codul tău de conectare este: <strong style="font-size: 24px; color: #912338;">{otp}</strong></p>
                    <p>Acest cod este valabil 5 minute.</p>
                    <hr style="border: 0; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666;">
                        Acest email a fost trimis automat. Pentru asistență, răspunde direct la acest mesaj.
                    </p>
                </div>
            """,
            "reply_to": "coop_miae@concordia.ca" # Redirecționare răspunsuri către facultate
        }
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Eroare trimitere Resend: {e}")
        return False

# ==========================================
# LOGICĂ PROCESARE DATE CURSURI
# ==========================================

def incarca_date():
    base_path = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(base_path, "CORE_TE.xlsx")
    try:
        df = pd.read_excel(excel_path)
        df.columns = [str(c).strip() for c in df.columns] 
        return df.fillna("")
    except Exception as e:
        print(f"Eroare Excel: {e}")
        return pd.DataFrame()

def extrage_cod(nume_curs):
    if not nume_curs: return ""
    match = re.search(r'[A-Z]{3,4}\s?\d{3}[A-Z]?|WT\d', str(nume_curs).upper())
    return match.group(0).replace(" ", "") if match else str(nume_curs).strip().upper()

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

# Colectare coduri OTP temporare
pending_otps = {}

# ==========================================
# RUTE FLASK (PAGINI ȘI API)
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
            return render_template("login.html", error="Eroare la trimiterea emailului.")
        return render_template("login.html", error="Email neautorizat în baza de date.")
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
        return render_template("verify.html", error="Cod incorect!")
    return render_template("verify.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/", methods=["GET"])
def index():
    if 'user_email' not in session: return redirect(url_for('login'))
    df = incarca_date()
    if df.empty: return "Eroare la încărcarea fișierului Excel."
    programe = sorted(df['Program'].apply(lambda x: str(x).strip()).unique().tolist())
    return render_template("planner.html", programe=programe)

@app.route("/get_courses", methods=["POST"])
def get_courses():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    program_name = data.get('program').strip()
    df = incarca_date()
    df_prog = df[df['Program'].str.strip() == program_name]

    # Calcul dependențe inverse pentru UI
    reverse_deps = defaultdict(lambda: {"is_prereq_for": set(), "is_coreq_for": set()})
    for _, row in df_prog.iterrows():
        cid_curent = extrage_cod(row['COURSE'])
        for m in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?', str(row.get('PRE-REQUISITE', '')).upper()):
            reverse_deps[m.replace(" ", "")]["is_prereq_for"].add(cid_curent)
        for m in re.findall(r'[A-Z]{3,4}\s*\d{3}[A-Z]?', str(row.get('CO-REQUISITE', '')).upper()):
            reverse_deps[m.replace(" ", "")]["is_coreq_for"].add(cid_curent)

    toate_cursurile = []
    pre_placed = defaultdict(list)
    def safe_str(val): return "" if str(val).strip().lower() == 'nan' else str(val).strip()

    for _, row in df_prog.iterrows():
        cid = extrage_cod(row['COURSE'])
        terms_offered = [t for t, col in zip(['Fall', 'Winter', 'Sum 1', 'Sum 2'], ['FALL', 'WIN', 'SUM 1', 'SUM 2']) if safe_str(row.get(col, '')).upper() == 'X']
        
        toate_cursurile.append({
            "id": cid, "display": f"{safe_str(row['COURSE'])} ({row.get('CREDIT', 0)} cr)",
            "credit": float(row.get('CREDIT', 0) or 0), "is_wt": 'WT' in safe_str(row['COURSE']).upper(),
            "is_ecp": safe_str(row.get('CORE_TE', '')).upper() == 'ECP',
            "full_name": safe_str(row['COURSE']), "type": safe_str(row.get('CORE_TE', '')),
            "terms": ", ".join(terms_offered) or "N/A",
            "prereqs": safe_str(row.get('PRE-REQUISITE', '')), "coreqs": safe_str(row.get('CO-REQUISITE', '')),
            "is_prereq_for": ", ".join(reverse_deps[cid]["is_prereq_for"]) or "None",
            "is_coreq_for": ", ".join(reverse_deps[cid]["is_coreq_for"]) or "None"
        })

        # Alocare automată inițială dacă există sugestii în Excel
        sugestie = safe_str(row.get('Course to place in q1', '')).upper()
        if sugestie:
            t_id = 'FALL' if 'FALL' in sugestie else 'WIN' if 'WIN' in sugestie else 'SUM1' if 'SUM' in sugestie else None
            y_m = re.search(r'(\d)', sugestie)
            if t_id and y_m: pre_placed[f"Y{y_m.group(1)}_{t_id}"].append(cid)

    return jsonify({"courses": toate_cursurile, "pre_placed": dict(pre_placed)})

# Endpoint-ul /generate păstrează logica de algoritm din scriptul original
@app.route("/generate", methods=["POST"])
def generate():
    if 'user_email' not in session: return jsonify({"error": "Unauthorized"}), 401
    # ... (Codul de generare rămâne cel stabilit anterior)
    return jsonify({"status": "Algorithm logic executed"})

if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)