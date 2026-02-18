import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

spreadsheet_name = "Sid_Email_Mirror"
google_tab_name = "Sid_Email_Admission"
PwrUsrsLocalFile = "PowerUsers"

def sync_to_google_sheets():
    # 1. Definirea căilor (dinamice și absolute)
    base_path = os.path.dirname(os.path.abspath(__file__))
    json_key_path = os.path.join(base_path, "cheie_google.json")
    
    # Calea către fișierul prioritar (din același folder cu scriptul)
    priority_file_path = os.path.join(base_path, f"{PwrUsrsLocalFile}.xlsx")
    
    # Calea către fișierul principal din folderul INPUT (urcă un nivel, apoi intră în INPUT)
    main_excel_path = os.path.abspath(os.path.join(base_path, "..", "INPUT","COOP_website", "co-op record sequence.xlsx"))

    # Numele exacte ale coloanelor pe care dorim să le extragem
    target_columns = ["Primary Email", "Student ID", "Admission Term"]

    # 2. Citirea fișierului prioritar (din PY_code)
    df_priority = pd.DataFrame()
    if os.path.exists(priority_file_path):
        try:
            df_priority = pd.read_excel(priority_file_path, sheet_name=PwrUsrsLocalFile)
            
            # Ne asigurăm că păstrăm doar coloanele de interes dacă există mai multe
            existing_cols = [c for c in target_columns if c in df_priority.columns]
            df_priority = df_priority[existing_cols]
            
            # Eliminăm rândurile goale
            df_priority = df_priority.dropna(how='all')
            print(f"Am citit {len(df_priority)} rânduri din fișierul prioritar '{google_tab_name}.xlsx'.")
        except Exception as e:
            print(f"Avertisment: Nu am putut procesa {google_tab_name}.xlsx - {e}")
    else:
        print(f"Fișierul prioritar '{google_tab_name}.xlsx' nu a fost găsit. Continuăm doar cu baza principală.")

    # 3. Citirea și procesarea fișierului principal (din INPUT)
    if not os.path.exists(main_excel_path):
        print(f"Eroare: Nu găsesc Excel-ul principal la: {main_excel_path}")
        return

    try:
        df_main = pd.read_excel(main_excel_path, sheet_name="Page 1")
        
        # Verificăm dacă fișierul conține coloanele necesare
        missing_cols = [col for col in target_columns if col not in df_main.columns]
        if missing_cols:
            print(f"Eroare: Următoarele coloane lipsesc din sheet-ul 'Page 1': {missing_cols}")
            return
            
        # Extragem doar cele 3 coloane după NUME
        df_main = df_main[target_columns]
        
        # Eliminăm rândurile care NU au o adresă de email
        df_main = df_main.dropna(subset=["Primary Email"])
        
        # Păstrăm doar combinațiile unice ale celor 3 coloane
        df_main = df_main.drop_duplicates(subset=target_columns)
        print(f"Am extras {len(df_main)} combinații unice valide din fișierul principal.")
        
    except Exception as e:
        print(f"Eroare la citirea fișierului principal Excel: {e}")
        return

    # 4. Combinarea datelor (Fișierul prioritar PRIMUL)
    if not df_priority.empty:
        # Concatenăm, punând fișierul din PY_code deasupra
        df_final = pd.concat([df_priority, df_main], ignore_index=True)
        # Eliminăm duplicatele pentru a nu avea același student de două ori (păstrăm prima apariție, cea din fișierul prioritar)
        df_final = df_final.drop_duplicates(subset=target_columns, keep='first')
    else:
        df_final = df_main

    # Curățăm datele (eliminăm valorile NaN și formatăm eventualele date calendaristice)
    for col in df_final.select_dtypes(include=['datetime64', 'datetimetz']).columns:
        df_final[col] = df_final[col].dt.strftime('%Y-%m-%d %H:%M:%S')
    df_final = df_final.fillna("")

    # 5. Sincronizarea cu Google Sheets
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_path, scope)
        client = gspread.authorize(creds)
        sh = client.open(spreadsheet_name)
    except Exception as e:
        print(f"Eroare la autentificarea Google: {e}")
        return

    try:
        worksheet = sh.worksheet(google_tab_name)
        print(f"Am deschis tab-ul '{google_tab_name}' în Google Sheets.")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Tab-ul '{google_tab_name}' nu există. Îl creez automat...")
        worksheet = sh.add_worksheet(title=google_tab_name, rows=str(max(100, len(df_final)+10)), cols=str(max(10, len(df_final.columns))))

    # Ștergem conținutul vechi
    worksheet.clear()
    
    # Pregătim datele pentru upload (Header + Valori)
    data_to_upload = [df_final.columns.values.tolist()] + df_final.values.tolist()
    
    # Încărcăm datele (folosind sintaxa actualizată)
    worksheet.update(values=data_to_upload, range_name='A1')
    print(f"=== Sincronizare reușită! Au fost încărcate {len(df_final)} rânduri. ===")

if __name__ == "__main__":
    sync_to_google_sheets()