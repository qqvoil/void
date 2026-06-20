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
        "notified_3d BOOLEAN DEFAULT 0",
        "notified_1d BOOLEAN DEFAULT 0",
        "notified_10h BOOLEAN DEFAULT 0",
        "notified_1h BOOLEAN DEFAULT 0"
    ]

    for col_def in new_columns:
        col_name = col_def.split()[0]
        if col_name not in columns:
            print(f"Adding column {col_name}...")
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_def}")

    # Convert expires_at format
    cursor.execute("SELECT id, expires_at FROM users WHERE expires_at IS NOT NULL AND expires_at != 'Безлимит'")
    users = cursor.fetchall()
    
    for uid, exp in users:
        # If exp is like '2026-05-20' (length 10)
        if len(exp) == 10:
            new_exp = f"{exp} 00:00:00"
            cursor.execute("UPDATE users SET expires_at = ? WHERE id = ?", (new_exp, uid))
            print(f"Updated user {uid}: {exp} -> {new_exp}")

    conn.commit()
    conn.close()
    print("Migration completed.")

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        migrate()
    else:
        print(f"Database not found at {DB_PATH}")
