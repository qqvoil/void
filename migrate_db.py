import sqlite3
import os

def migrate():
    db_path = os.path.join(os.path.dirname(__file__), 'users.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable WAL mode if not already
    cursor.execute('PRAGMA journal_mode=WAL;')

    print("Running migrations...")
    
    # 1. Add columns to users table
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN telegram_id INTEGER;')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);')
        print("Added telegram_id")
    except sqlite3.OperationalError as e:
        print(f"Skipping telegram_id: {e}")

    try:
        cursor.execute('ALTER TABLE users ADD COLUMN tg_link_token TEXT;')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tg_link_token ON users(tg_link_token);')
        print("Added tg_link_token")
    except sqlite3.OperationalError as e:
        print(f"Skipping tg_link_token: {e}")

    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_legacy BOOLEAN DEFAULT 0;')
        print("Added is_legacy")
    except sqlite3.OperationalError as e:
        print(f"Skipping is_legacy: {e}")

    # Mark existing users as legacy (they have no telegram_id)
    cursor.execute('UPDATE users SET is_legacy = 1 WHERE telegram_id IS NULL;')
    print("Marked existing users as legacy.")

    # 2. Create invoices table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        order_id TEXT UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    ''')
    print("Created invoices table.")

    conn.commit()
    conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
