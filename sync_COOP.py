import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import sys
import re

# --- CONFIGURARE ---
SPREADSHEET_NAME = "Sid_Email_Mirror"
TAB_COOP_NAME = "COOP"

# Calea catre fisierul Excel Local
COOP_LOCAL_FILE = r"C:\Users\vosor\OneDrive\! 1.Concordia\!z - COOP director\! PYTHON\WEB_TOOL\INPUT\COOP_website\2_COOP.xlsx"
COOP_SHEET_NAME = "COOP_data"

def get_gspread_client():
    """Autentificare Google Sheets API"""
    try:
        base_path = os.path.dirname(os.path.abspath(__file__))
        json_key_path = os.path.join(base_path, "cheie_google.json")
        
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_path, scope)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Eroare la autentificare Google: {e}")
        sys.exit(1)

def clean_student_id(val):
    """Curata Student ID: elimina zecimalele (.0) si spatiile"""
    if pd.isna(val) or val == "":
        return ""
    s = str(val).strip()
    if s.endswith('.0'):
        return s[:-2]
    return s

def normalize_term_string(val):
    """
    Standardizeaza formatul termenilor (Admission Term).
    Ex: '2020-2021 -2 Fall' -> '2020 Fall'
    """
    if pd.isna(val) or str(val).strip() == "":
        return ""
    s = str(val).strip()
    year_match = re.search(r'(\d{4})', s)
    year = year_match.group(1) if year_match else ""
    
    season = ""
    s_lower = s.lower()
    if 'fall' in s_lower or 'fa ' in s_lower or s_lower.endswith('fa'): season = "Fall"
    elif 'winter' in s_lower or 'wi' in s_lower or 'win' in s_lower: season = "Winter"
    elif 'summer' in s_lower or 'su' in s_lower or 'sum' in s_lower: season = "Summer"

    if year and season: return f"{year} {season}"
    return s

def sync_coop_data():
    print(f"\n🚀 START: Sincronizare date COOP (Merge & Update)...")
    
    # --- PASUL 1: Citire date LOCALE (Excel) ---
    if not os.path.exists(COOP_LOCAL_FILE):
        print(f"❌ EROARE: Fisierul Excel nu exista: {COOP_LOCAL_FILE}")
        return

    try:
        print("📂 Citire date locale...")
        df_local = pd.read_excel(COOP_LOCAL_FILE, sheet_name=COOP_SHEET_NAME, engine='openpyxl')
        
        # Selectam coloanele
        required_columns = ["Student ID", "Term", "Term number Sx or Wx", "Jobs View no", "Jobs Applied no", "Admission Term", "Term Details", "WS", "Transferred Withdrawn OK"]
        existing_cols = [c for c in required_columns if c in df_local.columns]
        df_local = df_local[existing_cols]

        # Curatare date locale
        if "Student ID" in df_local.columns:
            df_local["Student ID"] = df_local["Student ID"].apply(clean_student_id)
            df_local = df_local[df_local["Student ID"] != ""] # Eliminam ID-urile goale

        numeric_cols = ["Jobs View no", "Jobs Applied no"]
        for col in numeric_cols:
            if col in df_local.columns:
                df_local[col] = pd.to_numeric(df_local[col], errors='coerce').fillna(0).astype(int)

        if "Admission Term" in df_local.columns:
            df_local["Admission Term"] = df_local["Admission Term"].apply(normalize_term_string)

        # Convertim totul la string pentru uniformitate la merge
        df_local = df_local.astype(str)
        
        print(f"✅ Date locale incarcate: {len(df_local)} randuri.")

        # --- PASUL 2: Conectare la Google Sheets ---
        client = get_gspread_client()
        sh = client.open(SPREADSHEET_NAME)
        
        try:
            worksheet = sh.worksheet(TAB_COOP_NAME)
            print("☁️  Citire date existente din Cloud...")
            
            # Citim datele existente pentru a face MERGE (nu suprascriem totul orbeste)
            existing_data = worksheet.get_all_records()
            df_cloud = pd.DataFrame(existing_data)
            
            # Ne asiguram ca si datele din cloud sunt string-uri (pentru comparatie corecta)
            if not df_cloud.empty:
                 # Asiguram ca avem doar coloanele relevante si in cloud (pentru a evita erori la concat)
                cols_to_keep = [c for c in required_columns if c in df_cloud.columns]
                df_cloud = df_cloud[cols_to_keep].astype(str)
                # Aplicam clean pe Student ID si in cloud pentru siguranta
                if "Student ID" in df_cloud.columns:
                    df_cloud["Student ID"] = df_cloud["Student ID"].apply(clean_student_id)
            
            print(f"✅ Date cloud existente: {len(df_cloud)} randuri.")

        except gspread.exceptions.WorksheetNotFound:
            print(f"ℹ️  Tab-ul '{TAB_COOP_NAME}' nu exista. Va fi creat.")
            worksheet = sh.add_worksheet(title=TAB_COOP_NAME, rows="1000", cols="20")
            df_cloud = pd.DataFrame(columns=required_columns)

        # --- PASUL 3: MERGE (Suprapunere) ---
        # Concatenam Cloud (Vechi) + Local (Nou)
        # Ordinea este importanta: punem Cloud PRIMUL si Local AL DOILEA
        df_combined = pd.concat([df_cloud, df_local])

        # Verificam daca avem coloanele necesare pentru cheia unica
        if "Student ID" in df_combined.columns and "Term" in df_combined.columns:
            print("🔄 Se elimina duplicatele (Student ID + Term)...")
            
            # DROP DUPLICATES: 
            # subset: defineste ce inseamna "unic" (ID + Term)
            # keep='last': pastreaza ultima aparitie (adica cea din df_local, care e mai recenta/corecta)
            df_final = df_combined.drop_duplicates(subset=['Student ID', 'Term'], keep='last')
            
            print(f"📊 Rezultat final: {len(df_final)} randuri (au fost actualizate/adaugate).")
        else:
            print("⚠️ Atentie: Coloanele 'Student ID' sau 'Term' lipsesc. Se face append simplu.")
            df_final = df_combined

        # --- PASUL 4: Upload Final ---
        print("uploading...")
        worksheet.clear()
        
        # Sortam datele (optional, de ex dupa ID si Term)
        # df_final = df_final.sort_values(by=["Student ID", "Term"]) 

        payload = [df_final.columns.values.tolist()] + df_final.values.tolist()
        worksheet.update(values=payload, range_name='A1')
        
        print(f"✅ SUCCES: Sincronizare completa!")

    except Exception as e:
        print(f"❌ EROARE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    sync_coop_data()