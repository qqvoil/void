import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("Running migration v2...")
    
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN months INTEGER NOT NULL DEFAULT 1;')
        print("Added months to invoices")
    except sqlite3.OperationalError as e:
        print(f"Skipping months: {e}")

    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
