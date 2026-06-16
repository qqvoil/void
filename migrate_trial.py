import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "users.db")

def migrate():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN has_trial_used BOOLEAN DEFAULT 0;")
        conn.commit()
        print("Migration successful: added has_trial_used.")
    except sqlite3.OperationalError as e:
        print("Migration skipped or failed:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
