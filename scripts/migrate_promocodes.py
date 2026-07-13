import sqlite3
import os

DB_PATH = "/opt/void/users.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create promocodes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_percent INTEGER NOT NULL,
            max_uses INTEGER NOT NULL DEFAULT 0,
            current_uses INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Check if promo_code column exists in invoices
    cursor.execute("PRAGMA table_info(invoices)")
    columns = [row[1] for row in cursor.fetchall()]

    if "promo_code" not in columns:
        print("Adding promo_code column to invoices...")
        cursor.execute("ALTER TABLE invoices ADD COLUMN promo_code TEXT DEFAULT NULL")

    conn.commit()
    conn.close()
    print("Promocodes migration completed.")

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        migrate()
    elif os.path.exists("../users.db"):
        DB_PATH = "../users.db"
        migrate()
    elif os.path.exists("users.db"):
        DB_PATH = "users.db"
        migrate()
    else:
        print("Database not found.")
