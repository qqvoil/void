import sqlite3
import os

DB_PATH = "/opt/void/users.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if columns already exist
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]

    new_columns = [
        "referrer_id INTEGER DEFAULT NULL",
        "has_brought_referral_bonus BOOLEAN DEFAULT 0"
    ]

    for col_def in new_columns:
        col_name = col_def.split()[0]
        if col_name not in columns:
            print(f"Adding column {col_name}...")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_def}")

    conn.commit()
    conn.close()
    print("Referrals migration completed.")

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        migrate()
    else:
        print(f"Database not found at {DB_PATH}")
