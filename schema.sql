DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS invoices;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    password_hash TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    subscription_url TEXT,
    instructions_url TEXT,
    has_trial_used BOOLEAN DEFAULT 0,
    expires_at TEXT,
    telegram_id INTEGER UNIQUE,
    tg_link_token TEXT UNIQUE,
    notified_3d BOOLEAN DEFAULT 0,
    notified_1d BOOLEAN DEFAULT 0,
    notified_10h BOOLEAN DEFAULT 0,
    notified_1h BOOLEAN DEFAULT 0,
    referrer_id INTEGER DEFAULT NULL,
    has_brought_referral_bonus BOOLEAN DEFAULT 0,
    is_legacy BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    months INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    order_id TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
