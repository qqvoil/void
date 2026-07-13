import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
import requests
import json
import logging
import hashlib
import hmac
import time
from flask import g, redirect, url_for, session, current_app, request, flash

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__))) if 'routes' in __file__ else os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "users.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

def notify_admin(message):
    admin_tg_id = os.environ.get("ADMIN_TG_ID")
    bot_token = os.environ.get("BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")
    if admin_tg_id and bot_token:
        try:
            tg_api_server = os.environ.get("TG_API_SERVER", "https://api.telegram.org")
            requests.post(f"{tg_api_server}/bot{bot_token}/sendMessage", json={
                "chat_id": admin_tg_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=3)
        except Exception as e:
            print(f"Failed to notify admin: {e}")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config.get("DATABASE", DATABASE))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL;")
    return g.db

def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()

def query_one(query, params=()):
    db = get_db()
    return db.execute(query, params).fetchone()

def query_all(query, params=()):
    db = get_db()
    return db.execute(query, params).fetchall()

def execute(query, params=()):
    db = get_db()
    db.execute(query, params)
    db.commit()

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if getattr(g, 'user', None) is None:
            session.clear()
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped_view

def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.admin_login"))
        return view(*args, **kwargs)
    return wrapped_view

def get_remnawave_squad_uuid(api_key):
    try:
        resp = requests.get(
            "https://panel.jointhevoid.ru/api/users",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )
        if resp.status_code == 200:
            users = resp.json().get("response", [])
            for u in users:
                if isinstance(u, dict) and u.get("activeInternalSquads"):
                    return u["activeInternalSquads"][0]["uuid"]
    except Exception as e:
        logging.error(f"Error fetching squad: {e}")
    return "82e7d898-a7ee-4826-9f9d-ae9eb0933ed9"  # Fallback to known Default-Squad

def remnawave_create_or_extend_user(username, expire_date_str):
    api_key = os.environ.get("RW_API_KEY")
    if not api_key:
        return None
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # expire_date_str is YYYY-MM-DD HH:MM:SS
    expire_dt = datetime.strptime(expire_date_str, "%Y-%m-%d %H:%M:%S")
    # Remnawave expects ISO 8601 with Z
    expire_iso = expire_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    # Check if user already exists
    users_resp = requests.get("https://panel.jointhevoid.ru/api/users", headers=headers, timeout=5)
    existing_user = None
    if users_resp.status_code == 200:
        rw_data = users_resp.json().get("response", {})
        rw_users = rw_data.get("users", []) if isinstance(rw_data, dict) else []
        for u in rw_users:
            if isinstance(u, dict) and u.get("username") == username:
                existing_user = u
                break
                
    if existing_user:
        # Extend user
        update_payload = {
            "uuid": existing_user["uuid"],
            "status": "ACTIVE",
            "expireAt": expire_iso
        }
        resp = requests.patch("https://panel.jointhevoid.ru/api/users", headers=headers, json=update_payload, timeout=5)
        if resp.status_code == 200:
            return existing_user.get("subscriptionUrl")
    else:
        # Create user
        squad_uuid = get_remnawave_squad_uuid(api_key)
        create_payload = {
            "username": username,
            "status": "ACTIVE",
            "trafficLimitBytes": 0,
            "trafficLimitStrategy": "NO_RESET",
            "expireAt": expire_iso,
            "activeInternalSquads": [squad_uuid]
        }
        resp = requests.post("https://panel.jointhevoid.ru/api/users", headers=headers, json=create_payload, timeout=5)
        if resp.status_code == 201:
            data = resp.json().get("response", {})
            return data.get("subscriptionUrl")
            
    return None

import hashlib
import hmac
import time

def check_telegram_authorization(auth_data: dict) -> bool:
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        return False
    check_hash = auth_data.pop('hash', None)
    if not check_hash:
        return False
    
    if time.time() - int(auth_data.get('auth_date', 0)) > 86400:
        return False
        
    data_check_arr = [f"{key}={value}" for key, value in auth_data.items() if value]
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)
    
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    hash_computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(hash_computed, check_hash)


def check_webapp_authorization(init_data: str) -> bool:
    import urllib.parse
    bot_token = os.environ.get("BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")
    if not bot_token:
        return False
        
    parsed_data = urllib.parse.parse_qsl(init_data)
    auth_data = dict(parsed_data)
    
    check_hash = auth_data.pop('hash', None)
    if not check_hash:
        return False
        
    data_check_arr = [f"{key}={value}" for key, value in auth_data.items()]
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)
    
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(hash_computed, check_hash)


