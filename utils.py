import os
import re
import pandas as pd
import resend
from sqlalchemy import text



debug_no_emails =  "SITE_ACTIVE" # then it works
#debug_no_emails = "DEBUG" # debug
debug_email="coop_miae@concordia.ca"


# Setăm API key-ul Resend din variabile de mediu
resend.api_key = os.environ.get("RESEND_API_KEY", "")

# =========================================================
# 1. FUNCȚIA DE ÎNCĂRCARE DINAMICĂ (Din Excel)
# =========================================================
def load_data():
    try:
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx")
        df = pd.read_excel(excel_path)
        df.columns = [str(c).strip() for c in df.columns]
        return df.fillna("")
    except Exception as e:
        print(f"❌ Error loading Excel: {e}")
        return pd.DataFrame()

def load_sequences():
    try:
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx")
        df = pd.read_excel(excel_path, sheet_name='Sequences')
        df.columns = [str(c).strip() for c in df.columns]
        return df.fillna("").to_dict(orient="records")
    except Exception as e:
        print(f"❌ Error loading Sequences: {e}")
        return []

def load_program_names():
    """Load Program_names sheet for GPA thresholds. Returns {program: {GPA_2_terms, ...}}"""
    try:
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx")
        df = pd.read_excel(excel_path, sheet_name='Program_names')
        df.columns = [str(c).strip() for c in df.columns]
        return df.fillna("").to_dict(orient="records")
    except Exception:
        return []

def load_programs_requirements():
    """Load Programs sheet for credit requirements by type. Returns list of dicts with Program, Level, Type of credits, no of credits"""
    try:
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx")
        xl_file = pd.ExcelFile(excel_path)
        
        # Try common variations of the sheet name
        possible_names = ['Programs', 'programs', 'PROGRAMS', 'Program', 'program']
        sheet_name = None
        for name in possible_names:
            if name in xl_file.sheet_names:
                sheet_name = name
                break
        
        if not sheet_name:
            return []
        
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        df.columns = [str(c).strip() for c in df.columns]
        return df.fillna("").to_dict(orient="records")
    except Exception as e:
        return []

def load_restrictions():
    try:
        excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CORE_TE.xlsx")
        df = pd.read_excel(excel_path, sheet_name='restrictions')
        df.columns = [str(c).strip() for c in df.columns]
        # Convert date column to string for JSON serialization
        if 'Date after which takes effect' in df.columns:
            df['Date after which takes effect'] = df['Date after which takes effect'].astype(str)
        return df.fillna("").to_dict(orient="records")
    except Exception as e:
        print(f"❌ Error loading Restrictions: {e}")
        return []

# =========================================================
# 2. FUNCȚIE DE PARSARE TERMENI
# =========================================================
def parse_term(term_str):
    term_str = str(term_str).strip()
    term_up = term_str.upper()
    year = "UNKNOWN"
    season = "UNKNOWN"

    year_match = re.search(r'(\d{4}-\d{4})', term_str)
    if year_match:
        year = year_match.group(1)
    else:
        single_year = re.search(r'(\d{4})', term_str)
        if single_year:
            y = int(single_year.group(1))
            if "WIN" in term_up or "-4" in term_str: year = f"{y-1}-{y}"
            else: year = f"{y}-{y+1}"

    if "SUM" in term_up: season = "Summer"
    elif "WIN" in term_up: season = "Winter"
    elif "FALL" in term_up: season = "Fall"
    else:
        if "-1" in term_str: season = "Summer"
        elif "-4" in term_str: season = "Winter"
        elif "-2" in term_str or "-3" in term_str: season = "Fall"
        
    return year, season


# =========================================================
# 3. FUNCȚII PENTRU EMAIL
# =========================================================

# Funcția universală (Motorul principal)

DEFAULT_COORD_EMAIL = "coop_miae@concordia.ca"

def _merge_email_lists(*groups):
    out = []
    seen = set()
    for grp in groups:
        if not grp:
            continue
        if isinstance(grp, str):
            grp = [grp]
        for item in grp:
            addr = str(item or "").strip()
            if not addr:
                continue
            low = addr.lower()
            if low not in seen:
                seen.add(low)
                out.append(addr)
    return out

def get_email_recipients(program, target_sid, submitter_email, priority1_email, action_type, wts_changed=True):
    coop_ad_email = "coop_miae@concordia.ca"
    submit_notification = "sorin.voiculescu@concordia.ca"

    if debug_no_emails == "SITE_ACTIVE":
        miae_program_assistant = "sabrina.poirier@concordia.ca"
        email_coop_approval = "coopresequence@concordia.ca"
    else:
        miae_program_assistant = debug_email
        email_coop_approval = debug_email
        priority1_email = "vosorin@gmail.com"
        submitter_email = "vosorin@gmail.com"

    # Check if student is GRAD
    is_grad = 'GRAD' in str(program).upper() if program else False
    
    # Determine coordinators based on GRAD status
    if is_grad:
        # GRAD students: Nadia + Charlene
        if debug_no_emails == "SITE_ACTIVE":
            coord_email = "nadia.mazzaferro@concordia.ca"
            grad_coord_email = "charlene.wald@concordia.ca"
        else:
            coord_email = debug_email
            grad_coord_email = debug_email
        miae_program_assistant = None  # GRAD doesn't include Sabrina
    else:
        # UGRD students: determine coordinator based on program and SID
        grad_coord_email = None  # UGRD doesn't have second coordinator
        coord_email = "frederick.francis@concordia.ca"
        if program and "INDU" in str(program).upper():
            # INDU: check SID ending for Nathalie
            if target_sid:
                try:
                    last_digit = int(str(target_sid)[-1])
                    if last_digit >= 5:
                        coord_email = "nathalie.steverman@concordia.ca" if debug_no_emails == "SITE_ACTIVE" else debug_email
                    else:
                        coord_email = "frederick.francis@concordia.ca" if debug_no_emails == "SITE_ACTIVE" else debug_email
                except ValueError:
                    coord_email = "frederick.francis@concordia.ca" if debug_no_emails == "SITE_ACTIVE" else debug_email
            else:
                coord_email = "frederick.francis@concordia.ca" if debug_no_emails == "SITE_ACTIVE" else debug_email
        else:
            # Non-INDU UGRD: always Frederick
            coord_email = "frederick.francis@concordia.ca" if debug_no_emails == "SITE_ACTIVE" else debug_email

    recipients = {"to": [], "cc": [], "bcc": []}

    if action_type == "SUBMIT":
        recipients["to"].append(coop_ad_email)
        cc_list = [coord_email, submitter_email]
        if miae_program_assistant:
            cc_list.append(miae_program_assistant)
        if grad_coord_email:
            cc_list.append(grad_coord_email)
        recipients["cc"].extend(cc_list)
        recipients["bcc"].append(submit_notification)
        if priority1_email and priority1_email.strip().lower() != submitter_email.strip().lower():
            recipients["bcc"].append(priority1_email)

    elif action_type == "REWORK":
        recipients["to"].append(submitter_email)
        cc_list = [coop_ad_email, coord_email]
        if miae_program_assistant:
            cc_list.append(miae_program_assistant)
        if grad_coord_email:
            cc_list.append(grad_coord_email)
        recipients["cc"].extend(cc_list)
        if priority1_email and priority1_email.strip().lower() != submitter_email.strip().lower():
            recipients["bcc"].append(priority1_email)

    elif action_type == "APPROVED":
        if wts_changed:
            recipients["to"].append(email_coop_approval)
            cc_list = [coop_ad_email, coord_email, submitter_email]
            if miae_program_assistant:
                cc_list.append(miae_program_assistant)
            if grad_coord_email:
                cc_list.append(grad_coord_email)
            recipients["cc"].extend(cc_list)
        else:
            recipients["to"].append(submitter_email)
            cc_list = [coop_ad_email, coord_email]
            if miae_program_assistant:
                cc_list.append(miae_program_assistant)
            if grad_coord_email:
                cc_list.append(grad_coord_email)
            recipients["cc"].extend(cc_list)

        if priority1_email and priority1_email.strip().lower() != submitter_email.strip().lower():
            recipients["bcc"].append(priority1_email)

    recipients["to"] = list(set(filter(None, recipients["to"])))
    recipients["cc"] = list(set(filter(None, recipients["cc"])))
    recipients["bcc"] = list(set(filter(None, recipients["bcc"])))

    return recipients


def send_email(to, subject, content, cc=None, bcc=None, reply_to=None, is_html=True, sender="MIAE Planner <auth@concordiasequenceplanner.ca>"):
    if isinstance(to, str): to = [to]
    if isinstance(cc, str): cc = _merge_email_lists(cc, DEFAULT_COORD_EMAIL)
    if isinstance(bcc, str): bcc = [bcc]
    
    # Set default reply_to to coop_miae@concordia.ca if not provided
    if reply_to is None:
        reply_to = ["coop_miae@concordia.ca"]
    elif isinstance(reply_to, str):
        reply_to = [reply_to]

    # Add footer to all emails
    footer_html = """
        <div style="margin-top:30px;padding-top:20px;border-top:2px solid #e0e0e0;">
            <p style="font-size:13px;color:#333;line-height:1.6;margin-bottom:8px;">
                <strong style="color:#912338;">To update your sequence:</strong>
            </p>
            <p style="font-size:12px;color:#666;line-height:1.6;margin-top:0;">
                Login to <strong>concordia-sequence-planner.onrender.com</strong> using your CO-OP registered email (the one used for this communication).
            </p>
            <p style="font-size:11px;color:#999;margin-top:15px;font-style:italic;">
                This is an automated message from the MIAE CO-OP Sequence Planner.
            </p>
        </div>
    """
    
    footer_text = """
---
To update your sequence:
Login to concordia-sequence-planner.onrender.com using your CO-OP registered email (the one used for this communication).

This is an automated message from the MIAE CO-OP Sequence Planner.
"""
    
    # Add footer to content
    if is_html:
        content = str(content) + footer_html
    else:
        content = str(content) + footer_text

    # DEBUG mode: redirect ALL recipients to debug_email
    if debug_no_emails == "DEBUG":
        original_to = to or []
        original_cc = cc or []
        original_bcc = bcc or []
        to = [debug_email]
        cc = None
        bcc = None
        subject = f"[DEBUG] {subject}"
        debug_note = (
            f"<hr><p style='color:red;font-size:11px;'><b>DEBUG MODE</b> — original recipients:<br>"
            f"TO: {', '.join(original_to)}<br>"
            f"CC: {', '.join(original_cc)}<br>"
            f"BCC: {', '.join(original_bcc)}</p>"
        )
        if is_html:
            content = str(content) + debug_note
        else:
            content = str(content) + f"\n\n--- DEBUG: original TO={original_to} CC={original_cc} BCC={original_bcc}"
        print(f"📧 DEBUG email → {debug_email} (original TO: {original_to})")

    email_data = {
        "from": sender,
        "to": to,
        "subject": subject,
    }

    if is_html:
        email_data["html"] = content
    else:
        email_data["text"] = content

    if cc: email_data["cc"] = cc
    if bcc: email_data["bcc"] = bcc
    if reply_to: email_data["reply_to"] = reply_to

    try:
        resend.Emails.send(email_data)
        return True
    except Exception as e:
        print(f"❌ Email Sending Error: {e}")
        return False

# Funcția ta originală actualizată (Acum folosește motorul de mai sus)
def send_otp_email(recipient, otp):
    html_body = f"""
        <div style="font-family: sans-serif; padding: 20px; border: 1px solid #eee;">
            <h2 style="color: #912338;">MIAE Academic Planner</h2>
            <p>Your access code is: <b style="font-size: 24px; color: #333;">{otp}</b></p>
            <p style="font-size: 12px; color: #666;">This code is valid for any login within the next 30 minutes.</p>
        </div>
    """
    
    # Apelăm funcția universală cu toți parametrii doriți
    return send_email(
        to=recipient,
        subject=f"{otp} is your access code",
        content=html_body,
        bcc="concordia.sequence.planner@gmail.com",
        is_html=True
    )

# =========================================================
# 4. FUNCȚIE CALCUL ISTORIC GPA
# =========================================================
def calculate_cgpa(ts_df, student_id=None, db_engine=None):
    """Read CGPA data from CGPA_Timeline table (pre-calculated by 0_master).
       Falls back to local calculation only if DB read fails."""
    cgpa_history = []

    # --- Try DB first ---
    if student_id and db_engine:
        try:
            with db_engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT `Academic Term`, CGPA, CGPA_Total_Credits, GPA_X_CR, GPA_X_CR_Actual_Credits "
                         "FROM `CGPA_Timeline` WHERE `Student ID` = :sid ORDER BY `Academic Term`"),
                    {"sid": student_id}
                ).fetchall()
            for row in rows:
                term_str = str(row[0])
                cgpa = float(row[1]) if row[1] is not None else 0.0
                total_cr = float(row[2]) if row[2] is not None else 0.0
                gpa_xcr = float(row[3]) if row[3] is not None else -1
                xcr_credits = float(row[4]) if row[4] is not None else 0.0

                y, s = parse_term(term_str)
                if y == "UNKNOWN":
                    continue

                # GPA_X_CR = -1 means not enough credits yet
                if gpa_xcr < 0:
                    info_html = f"GPA past {xcr_credits}cr: <b>N/A</b><br>(CGPA {cgpa} / {total_cr}cr total)"
                else:
                    is_low = gpa_xcr < 2.5 or cgpa < 2.5
                    if is_low:
                        info_html = (f"<span style='font-size:14px;font-weight:bold;color:#c0392b;'>"
                                     f"GPA past {xcr_credits}cr: {gpa_xcr}<br>"
                                     f"(CGPA {cgpa} / {total_cr}cr total)</span>")
                    else:
                        info_html = f"GPA past {xcr_credits}cr: <b>{gpa_xcr}</b><br>(CGPA {cgpa} / {total_cr}cr total)"
                cgpa_history.append({"year": y, "season": s, "info": info_html})

            if cgpa_history:
                return cgpa_history
        except Exception as e:
            print(f"[CGPA] DB read failed, falling back to local calc: {e}")

    # --- Fallback: local calculation from transcript dataframe ---
    grade_pts = {'A+':4.3, 'A':4.0, 'A-':3.7, 'B+':3.3, 'B':3.0, 'B-':2.7, 'C+':2.3, 'C':2.0, 'C-':1.7, 'D+':1.3, 'D':1.0, 'D-':0.7, 'F':0, 'FNS':0}
    
    def get_sort_val(t_str):
        y_val, s_val = parse_term(t_str)
        if y_val == "UNKNOWN": return "9999-9"
        s_num = {"Summer":1, "Fall":2, "Winter":3}.get(s_val, 0)
        return f"{y_val}-{s_num}"
        
    if not ts_df.empty and 'Academic Term' in ts_df.columns:
        valid_ts = ts_df[
            ts_df['Academic Term'].notna() & 
            ts_df['GRADE'].notna() & 
            (ts_df['GRADE'].str.strip() != '') &
            (ts_df['GRADE'].str.upper() != 'DISC')
        ].copy()
        
        valid_ts['sort_col'] = valid_ts['Academic Term'].apply(get_sort_val)
        valid_ts = valid_ts.sort_values('sort_col')
        valid_ts = valid_ts.drop_duplicates(subset=['COURSE'], keep='last')
        valid_ts = valid_ts.sort_values('sort_col')
        
        unique_terms = valid_ts['Academic Term'].unique()
        for term in unique_terms:
            subset = valid_ts[valid_ts['sort_col'] <= get_sort_val(term)]
            
            total_cr = 0
            total_pts = 0
            for _, row in subset.iterrows():
                gr = str(row.get('GRADE', '')).strip().upper()
                cr = float(row.get('CREDVAL', 0)) if pd.notna(row.get('CREDVAL')) else 0
                if gr in grade_pts and cr > 0:
                    total_cr += cr
                    total_pts += cr * grade_pts[gr]
                    
            cgpa = round(total_pts / total_cr, 2) if total_cr > 0 else 0.0
            
            recent_cr = 0
            recent_pts = 0
            for _, row in subset.iloc[::-1].iterrows():
                gr = str(row.get('GRADE', '')).strip().upper()
                cr = float(row.get('CREDVAL', 0)) if pd.notna(row.get('CREDVAL')) else 0
                if gr in grade_pts and cr > 0:
                    if recent_cr + cr <= 24.5:
                        recent_cr += cr
                        recent_pts += cr * grade_pts[gr]
                    else:
                        needed = 24.5 - recent_cr
                        recent_cr += needed
                        recent_pts += needed * grade_pts[gr]
                        break
                        
            recent_gpa = round(recent_pts / recent_cr, 2) if recent_cr > 0 else 0.0
            
            y, s = parse_term(term)
            if y != "UNKNOWN":
                is_low = recent_gpa < 2.5 or cgpa < 2.5
                if is_low:
                    info_html = f"<span style='font-size:14px;font-weight:bold;color:#c0392b;'>GPA past {recent_cr}cr: {recent_gpa}<br>(CGPA {cgpa} / {total_cr}cr total)</span>"
                else:
                    info_html = f"GPA past {recent_cr}cr: <b>{recent_gpa}</b><br>(CGPA {cgpa} / {total_cr}cr total)"
                cgpa_history.append({"year": y, "season": s, "info": info_html})
                
    return cgpa_history


# =========================================================
# 5. PROCESARE DATE STUDENT & DETECTARE PROGRAM
# =========================================================
def process_student_data(ts_df, coop_df):
    is_grad = False
    if not ts_df.empty and 'PROG_LINK' in ts_df.columns:
        latest_prog_link = str(ts_df['PROG_LINK'].dropna().iloc[-1]).upper()
        if 'GRAD' in latest_prog_link: is_grad = True

    student_courses = []
    taken_course_ids = set()
    
    # Procesare Cursuri
    for _, row in ts_df.iterrows():
        term_val = str(row.get('Academic Term', '')).strip()
        course_val = str(row.get('COURSE', '')).strip().replace(" ", "").upper()
        cred_val = float(row.get('CREDVAL', 0)) if pd.notna(row.get('CREDVAL')) else 0.0
        grade_val = str(row.get('GRADE', '')).strip() if pd.notna(row.get('GRADE')) else ""
        
        taken_course_ids.add(course_val)
        y, s = parse_term(term_val)
        
        if y != "UNKNOWN" and s != "UNKNOWN":
            # Capstone handling:
            # - If transcript has base 490 (e.g., AERO490), split into 490A (Fall) + 490B (Winter) of SAME academic year.
            # - If transcript already has 490A/490B, keep as-is but force seasons (A=Fall, B=Winter).
            m490 = re.match(r'^(?P<prefix>[A-Z]{2,5})490(?P<part>[AB])?$', course_val)
            if m490:
                prefix = m490.group('prefix')
                part   = m490.group('part')

                if part is None:
                    student_courses.append({"id": f"{prefix}490A", "year": y, "season": "Fall",   "credit": cred_val/2, "grade": grade_val})
                    student_courses.append({"id": f"{prefix}490B", "year": y, "season": "Winter", "credit": cred_val/2, "grade": grade_val})
                elif part.upper() == 'A':
                    student_courses.append({"id": f"{prefix}490A", "year": y, "season": "Fall",   "credit": cred_val, "grade": grade_val})
                else:  # 'B'
                    student_courses.append({"id": f"{prefix}490B", "year": y, "season": "Winter", "credit": cred_val, "grade": grade_val})
            else:
                student_courses.append({"id": course_val, "year": y, "season": s, "credit": cred_val, "grade": grade_val})

    # Detectare automată a programului din DISCIPLINE1_DESCR
    detected_program = "Mechanical Engineering"
    if not ts_df.empty and 'DISCIPLINE1_DESCR' in ts_df.columns:
        disc = str(ts_df['DISCIPLINE1_DESCR'].dropna().iloc[-1]).lower() if not ts_df['DISCIPLINE1_DESCR'].dropna().empty else ""
        if "industrial" in disc:
            detected_program = "Industrial Engineering"
        elif "mechanical" in disc:
            detected_program = "Mechanical Engineering"
        elif "aero" in disc or "aerospace" in disc:
            if "aerodyn" in disc or "propul" in disc:
                detected_program = "Aero A: Aerodynamics and Propulsion"
            elif "struct" in disc or "material" in disc:
                detected_program = "Aero B: Aerospace Structures and Materials"
            elif "avioni" in disc or "avionics" in disc:
                detected_program = "Aero C: Avionics and Aerospace Systems"
            else:
                detected_program = "Aero C: Avionics and Aerospace Systems"
    else:
        # Fallback: detectare din cursuri
        if any("INDU" in c for c in taken_course_ids):
            detected_program = "Industrial Engineering"
        elif "AERO201" in taken_course_ids:
            detected_program = "Aero C: Avionics and Aerospace Systems"
            if "AERO480" in taken_course_ids or "AERO482" in taken_course_ids:
                detected_program = "Aero A: Aerodynamics and Propulsion"
            elif "AERO431" in taken_course_ids:
                detected_program = "Aero B: Aerospace Structures and Materials"

    if is_grad:
        if "MECH" in detected_program.upper():
            detected_program = "Mechanical GRAD"
        elif "INDU" in detected_program.upper():
            detected_program = "Industrial GRAD"
        else:
            detected_program = "Aerospace GRAD"

    # Procesare termeni CO-OP
    coop_terms = []
    if not coop_df.empty:
        for _, row in coop_df.iterrows():
            y, s = parse_term(row['Term'])
            if y != "UNKNOWN" and s != "UNKNOWN":
                term_details = str(row.get('Term Details', '')).strip() if pd.notna(row.get('Term Details')) else ""
                ws = str(row.get('WS', '')).strip() if pd.notna(row.get('WS')) else ""
                jobs_view = str(row.get('Jobs View No', '')).strip() if pd.notna(row.get('Jobs View No')) else ""
                jobs_applied = str(row.get('Jobs Applied No', '')).strip() if pd.notna(row.get('Jobs Applied No')) else ""
                
                coop_terms.append({
                    "year": y, 
                    "season": s, 
                    "type": str(row.get('Term number Sx or Wx', '')).strip(),
                    "details": term_details,
                    "ws": ws,
                    "jobs_view": jobs_view,
                    "jobs_applied": jobs_applied
                })

    return is_grad, student_courses, detected_program, coop_terms