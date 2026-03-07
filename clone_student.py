"""
Clone Student — creates a dummy student by copying an existing student's data.

Usage:
  1. Set the variables below (SOURCE_SID, NEW_NAME, NEW_EMAIL)
  2. Set DB credentials as environment variables (or edit directly)
  3. Run: python clone_student.py
"""

import os
import sys
import pymysql
from sqlalchemy import create_engine, text

# =========================================================
# CONFIGURATION — edit these
# =========================================================
SOURCE_SID = "40314109"                          # existing student ID to clone from
NEW_NAME   = "Test Student"                       # name for the new dummy student
NEW_EMAIL  = "vvvsss75@gmail.com"          # email for the new dummy student

# DB credentials (from env or hardcode for local use)
DB_USER = os.environ.get("planner_db_USER", "")
DB_PASS = os.environ.get("planner_db_password", "")
DB_HOST = os.environ.get("planner_db_HOST", "")
DB_NAME = os.environ.get("planner_db_NAME", "")

# =========================================================
# DO NOT EDIT BELOW THIS LINE
# =========================================================
DUMMY_PREFIX = "85550"  # new IDs will be 85550001, 85550002, ...

def get_engine():
    if not DB_PASS:
        print("❌ DB credentials not set. Set environment variables or edit the script.")
        sys.exit(1)
    uri = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}"
    return create_engine(uri, pool_pre_ping=True, connect_args={"ssl": {}})


def find_next_dummy_id(conn):
    """Find the next available 85550xxx ID."""
    result = conn.execute(
        text("SELECT `Student ID` FROM `Sid_Email_Admission` WHERE `Student ID` LIKE :pat ORDER BY `Student ID` DESC LIMIT 1"),
        {"pat": f"{DUMMY_PREFIX}%"}
    ).fetchone()

    if result:
        last_id = int(str(result[0]).strip())
        return str(last_id + 1)
    else:
        return f"{DUMMY_PREFIX}001"


def check_email_exists(conn, email):
    """Check if the email already exists in Sid_Email_Admission."""
    result = conn.execute(
        text("SELECT COUNT(*) FROM `Sid_Email_Admission` WHERE LOWER(`Primary Email`) = :email"),
        {"email": email.strip().lower()}
    ).fetchone()
    return result[0] > 0


def check_source_exists(conn, sid):
    """Check if the source student exists."""
    result = conn.execute(
        text("SELECT COUNT(*) FROM `Sid_Email_Admission` WHERE `Student ID` = :sid"),
        {"sid": sid}
    ).fetchone()
    return result[0] > 0


def clone_student(engine, source_sid, new_name, new_email):
    with engine.begin() as conn:
        # ── Validations ──
        if not check_source_exists(conn, source_sid):
            print(f"❌ Source student {source_sid} not found in Sid_Email_Admission.")
            return False

        if check_email_exists(conn, new_email):
            print(f"❌ Email '{new_email}' already exists in Sid_Email_Admission. Aborting.")
            return False

        new_sid = find_next_dummy_id(conn)
        print(f"📋 Cloning {source_sid} → {new_sid}")
        print(f"   Name:  {new_name}")
        print(f"   Email: {new_email}")
        print()

        # ── 1. Clone Sid_Email_Admission ──
        # First, get all columns dynamically
        cols_result = conn.execute(text("SELECT * FROM `Sid_Email_Admission` WHERE `Student ID` = :sid"), {"sid": source_sid}).fetchall()
        if cols_result:
            # Get column names
            col_names = conn.execute(text("SELECT * FROM `Sid_Email_Admission` WHERE `Student ID` = :sid LIMIT 1"), {"sid": source_sid}).keys()
            col_list = list(col_names)

            for row in cols_result:
                row_dict = dict(zip(col_list, row))
                row_dict["Student ID"] = new_sid
                row_dict["Primary Email"] = new_email
                # Replace name if column exists
                for name_col in ["Name", "NAME", "name", "Student Name"]:
                    if name_col in row_dict:
                        row_dict[name_col] = new_name

                placeholders = ", ".join([f":{c.replace(' ', '_').replace('#','')}" for c in col_list])
                columns = ", ".join([f"`{c}`" for c in col_list])
                params = {c.replace(' ', '_').replace('#',''): v for c, v in row_dict.items()}

                conn.execute(text(f"INSERT INTO `Sid_Email_Admission` ({columns}) VALUES ({placeholders})"), params)

            count = len(cols_result)
            print(f"   ✅ Sid_Email_Admission: {count} row(s) cloned")
        else:
            print("   ⚠ Sid_Email_Admission: no rows found for source")

        # ── 2. Clone Transcripts ──
        ts_result = conn.execute(text("SELECT * FROM `Transcripts` WHERE `Student ID` = :sid"), {"sid": source_sid}).fetchall()
        if ts_result:
            col_names = conn.execute(text("SELECT * FROM `Transcripts` WHERE `Student ID` = :sid LIMIT 1"), {"sid": source_sid}).keys()
            col_list = list(col_names)

            for row in ts_result:
                row_dict = dict(zip(col_list, row))
                row_dict["Student ID"] = new_sid
                # Replace NAME if present
                if "NAME" in row_dict:
                    row_dict["NAME"] = new_name

                placeholders = ", ".join([f":{c.replace(' ', '_').replace('#','')}" for c in col_list])
                columns = ", ".join([f"`{c}`" for c in col_list])
                params = {c.replace(' ', '_').replace('#',''): v for c, v in row_dict.items()}

                conn.execute(text(f"INSERT INTO `Transcripts` ({columns}) VALUES ({placeholders})"), params)

            print(f"   ✅ Transcripts: {len(ts_result)} row(s) cloned")
        else:
            print("   ⚠ Transcripts: no rows found for source")

        # ── 3. Clone coop ──
        coop_result = conn.execute(text("SELECT * FROM `coop` WHERE `Student ID` = :sid"), {"sid": source_sid}).fetchall()
        if coop_result:
            col_names = conn.execute(text("SELECT * FROM `coop` WHERE `Student ID` = :sid LIMIT 1"), {"sid": source_sid}).keys()
            col_list = list(col_names)

            for row in coop_result:
                row_dict = dict(zip(col_list, row))
                row_dict["Student ID"] = new_sid

                placeholders = ", ".join([f":{c.replace(' ', '_').replace('#','')}" for c in col_list])
                columns = ", ".join([f"`{c}`" for c in col_list])
                params = {c.replace(' ', '_').replace('#',''): v for c, v in row_dict.items()}

                conn.execute(text(f"INSERT INTO `coop` ({columns}) VALUES ({placeholders})"), params)

            print(f"   ✅ coop: {len(coop_result)} row(s) cloned")
        else:
            print("   ⚠ coop: no rows found for source (student may not be in CO-OP)")

        # ── 4. login vs id — this is a VIEW (not a table), no insert needed ──
        # It reads from Sid_Email_Admission + logins automatically.
        # Just verify the new student is visible through the view.
        check = conn.execute(
            text("SELECT `Student ID`, `Name` FROM `login vs id` WHERE `Student ID` = :sid LIMIT 1"),
            {"sid": new_sid}
        ).fetchone()
        if check:
            print(f"   ✅ login vs id (VIEW): new student visible as '{check[1]}'")
        else:
            print(f"   ⚠ login vs id (VIEW): new student not yet visible — will appear after first login")

        print()
        print(f"🎉 Done! New dummy student created:")
        print(f"   ID:    {new_sid}")
        print(f"   Name:  {new_name}")
        print(f"   Email: {new_email}")
        print(f"   (cloned from {source_sid})")
        return True


def delete_dummy(engine, sid):
    """Delete a dummy student (85550xxx) from all tables."""
    if not sid.startswith(DUMMY_PREFIX):
        print(f"❌ Safety: can only delete dummy IDs starting with {DUMMY_PREFIX}. Got: {sid}")
        return False

    with engine.begin() as conn:
        tables = ["Sid_Email_Admission", "Transcripts", "coop", "Saved_Sequences", "S_id_comments", "course_deviation", "logins"]
        for tbl in tables:
            try:
                result = conn.execute(text(f"DELETE FROM `{tbl}` WHERE `Student ID` = :sid"), {"sid": sid})
                if result.rowcount > 0:
                    print(f"   🗑 {tbl}: deleted {result.rowcount} row(s)")
            except Exception:
                pass  # table may not exist or column name differs

        # logins uses 'email' not 'Student ID' — delete by email
        try:
            email_row = conn.execute(
                text("SELECT `Primary Email` FROM `Sid_Email_Admission` WHERE `Student ID` = :sid LIMIT 1"),
                {"sid": sid}
            ).fetchone()
            if email_row and email_row[0]:
                conn.execute(text("DELETE FROM `logins` WHERE `email` = :email"), {"email": email_row[0]})
        except Exception:
            pass

    print(f"   ✅ Dummy student {sid} deleted.")
    return True


if __name__ == "__main__":
    # Support --delete 85550001 to remove a dummy
    if len(sys.argv) >= 3 and sys.argv[1] == "--delete":
        delete_sid = sys.argv[2].strip()
        print(f"Deleting dummy student {delete_sid}...")
        engine = get_engine()
        delete_dummy(engine, delete_sid)
        sys.exit(0)

    print("=" * 60)
    print("  CLONE STUDENT — Create Dummy User")
    print("=" * 60)
    print(f"  Source:  {SOURCE_SID}")
    print(f"  Name:   {NEW_NAME}")
    print(f"  Email:  {NEW_EMAIL}")
    print("=" * 60)
    print()

    confirm = input("Proceed? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        sys.exit(0)

    engine = get_engine()
    success = clone_student(engine, SOURCE_SID, NEW_NAME, NEW_EMAIL)
    sys.exit(0 if success else 1)
