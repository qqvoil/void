import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
import requests
import json
import logging

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "users.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

INSTRUCTION_TEMPLATES = {
    "ios": "inst-ios.html",
    "android": "inst-android.html",
    "windows": "inst-windows.html",
    "macos": "inst-macos.html",
    "dev": "inst-dev.html",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = DATABASE

csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["1000 per day", "100 per hour"],
    storage_uri="memory://"
)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

CONTACT_TELEGRAM = os.environ.get("CONTACT_TELEGRAM", "@yourcontact")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "hello@example.com")
CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "+49 000 000 0000")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL;")
    return g.db


@app.teardown_appcontext
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
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped_view


def render_instruction_page(template_name):
    template_path = os.path.join(TEMPLATES_DIR, template_name)

    if os.path.exists(template_path):
        return render_template(template_name)

    return render_template("inst-landing.html")


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None

    if user_id:
        g.user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))


@app.context_processor
def inject_globals():
    return {
        "current_user": g.get("user"),
        "contact_telegram": CONTACT_TELEGRAM,
        "contact_email": CONTACT_EMAIL,
        "contact_phone": CONTACT_PHONE,
    }

@app.route("/anypay-verification.txt")
def anypay_verification():
    return "39bb84b1154ceecdf62eb423d3a3"

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/")
def index():
    if session.get("is_admin"):
        return redirect(url_for("admin_panel"))
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/webapp")
def webapp():
    # Telegram Android WebApp sometimes gets stuck on 302 redirects.
    # We return a 200 OK page that redirects via JS.
    target_url = url_for("dashboard") if session.get("user_id") else url_for("login")
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Loading...</title>
        <script src="{url_for('static', filename='telegram-web-app.js')}"></script>
        <script>
            if (window.Telegram && window.Telegram.WebApp) {
                window.Telegram.WebApp.ready();
            }
            window.location.replace("TARGET_URL");
        </script>
    </head>
    <body style="background-color: #0a0a0a; color: white; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: sans-serif;">
        <div style="text-align: center;">Загрузка...</div>
    </body>
    </html>
    """
    return html_content.replace("TARGET_URL", target_url)


#@app.route("/init-db")
#def init_db_route():
#    init_db()
#    return "Database initialized."


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        error = None

        if not full_name:
            error = "Введите логин."
        elif len(full_name) < 3:
            error = "Логин слишком короткий (минимум 3 символа)."
        elif not password:
            error = "Введите пароль."
        elif len(password) < 6:
            error = "Пароль должен быть не короче 6 символов."
        elif password != confirm_password:
            error = "Пароли не совпадают."

        existing_user = query_one(
            "SELECT id FROM users WHERE lower(full_name) = lower(?)",
            (full_name,),
        )
        if existing_user:
            error = "Этот логин уже занят. Пожалуйста, придумайте другой."

        referrer_id = None
        ref = request.args.get("ref") or request.form.get("ref")
        if ref and ref.isdigit():
            referrer = query_one("SELECT id FROM users WHERE id = ?", (int(ref),))
            if referrer:
                referrer_id = int(ref)

        if error is None:
            password_hash = generate_password_hash(password)
            execute(
                """
                INSERT INTO users (full_name, password_hash, status, instructions_url, referrer_id)
                VALUES (?, ?, 'new', ?, ?)
            """,
                (full_name, password_hash, "/inst-landing", referrer_id),
            )
            flash("Регистрация успешна. Теперь войдите в аккаунт.", "success")
            return redirect(url_for("login"))

        flash(error, "error")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")

        error = "Неверные данные для входа."
        user = query_one(
            "SELECT * FROM users WHERE lower(full_name) = lower(?)",
            (full_name,),
        )

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash(error, "error")

    return render_template("login.html")


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


@app.route("/auth/telegram")
def auth_telegram():
    auth_data = request.args.to_dict()
    if check_telegram_authorization(auth_data.copy()):
        telegram_id = auth_data.get('id')
        first_name = auth_data.get('first_name', 'Telegram User')
        
        user = query_one("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        if user:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        else:
            execute(
                "INSERT INTO users (full_name, telegram_id, status) VALUES (?, ?, ?)",
                (first_name, telegram_id, "new")
            )
            new_user = query_one("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            session.clear()
            session.permanent = True
            session["user_id"] = new_user["id"]
            return redirect(url_for("dashboard"))
    
    flash("Ошибка авторизации Telegram", "error")
    return redirect(url_for("login"))


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


@app.route("/auth/webapp", methods=["POST"])
@csrf.exempt
def auth_webapp():
    init_data = request.json.get('initData')
    if not init_data:
        logging.error("No initData provided")
        return {"success": False, "error": "No initData"}
        
    is_valid = check_webapp_authorization(init_data)
    logging.info(f"WebApp Auth check: {is_valid}")
    if is_valid:
        import urllib.parse
        import json
        parsed = dict(urllib.parse.parse_qsl(init_data))
        user_data = json.loads(parsed.get('user', '{}'))
        
        telegram_id = user_data.get('id')
        first_name = user_data.get('first_name', 'Telegram User')
        
        if not telegram_id:
            logging.error("No telegram_id in user_data")
            return {"success": False, "error": "No telegram_id"}
            
        existing_tg_user = query_one("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        
        if getattr(g, 'user', None):
            # User is already logged in, let's link the TG account if possible
            current_user_id = g.user["id"]
            if existing_tg_user and existing_tg_user["id"] == current_user_id:
                # Already linked properly
                return {"success": True, "linked": False}
            elif not existing_tg_user:
                execute("UPDATE users SET telegram_id = ? WHERE id = ?", (telegram_id, current_user_id))
                return {"success": True, "linked": True}
            else:
                # Switch to existing TG user to avoid conflicts
                session.clear()
                session.permanent = True
                session["user_id"] = existing_tg_user["id"]
                return {"success": True, "linked": True}
                
        # User not logged in
        if existing_tg_user:
            session.clear()
            session.permanent = True
            session["user_id"] = existing_tg_user["id"]
            return {"success": True}
        else:
            execute(
                "INSERT INTO users (full_name, telegram_id, status) VALUES (?, ?, ?)",
                (first_name, telegram_id, "new")
            )
            new_user = query_one("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            session.clear()
            session.permanent = True
            session["user_id"] = new_user["id"]
            return {"success": True}
            
    logging.error("WebApp Auth validation failed")
    return {"success": False, "error": "Invalid auth"}


@app.route("/payment/pay", methods=["POST"])
@login_required
def payment_pay():
    project_id = os.environ.get("ANYPAY_PROJECT_ID")
    secret_key = os.environ.get("ANYPAY_SECRET_KEY")
    
    if not project_id or not secret_key:
        flash("Оплата временно недоступна (касса не настроена).", "error")
        return redirect(url_for("dashboard"))
        
    months_str = request.form.get("months", "1")
    try:
        months = int(months_str)
    except ValueError:
        months = 1
        
    prices = {
        1: 200,
        3: 510,
        6: 960,
        12: 1800
    }
    amount = prices.get(months, 200)
        
    user_id = g.user["id"]
    
    execute("INSERT INTO invoices (user_id, amount, months) VALUES (?, ?, ?)", (user_id, amount, months))
    invoice = query_one("SELECT * FROM invoices WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    pay_id = str(invoice["id"])
    
    currency = "RUB"
    desc = f"Void VPN Subscription ({months} months)"
    
    success_url = ""
    fail_url = ""
    
    sign_string = f"{project_id}:{pay_id}:{amount}:{currency}:{desc}:{success_url}:{fail_url}:{secret_key}"
    sign = hashlib.sha256(sign_string.encode('utf-8')).hexdigest()
    
    import urllib.parse
    query_params = {
        "merchant_id": project_id,
        "pay_id": pay_id,
        "amount": amount,
        "currency": currency,
        "desc": desc,
        "sign": sign
    }
    
    query_string = urllib.parse.urlencode(query_params, quote_via=urllib.parse.quote)
    url = "https://anypay.io/merchant?" + query_string
    
    return redirect(url)

# --- Remnawave API Client ---

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
            "status": "ACTIVE",
            "expireAt": expire_iso
        }
        user_uuid = existing_user["uuid"]
        resp = requests.put(f"https://panel.jointhevoid.ru/api/users/{user_uuid}", headers=headers, json=update_payload, timeout=5)
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

@app.route("/payment/anypay/webhook", methods=["POST", "GET"])
@limiter.exempt
def anypay_webhook():
    project_id = os.environ.get("ANYPAY_PROJECT_ID")
    secret_key = os.environ.get("ANYPAY_SECRET_KEY")
    
    if not project_id or not secret_key:
        return "Not configured", 500
        
    req_data = request.form if request.method == "POST" else request.args
    
    currency = req_data.get('currency', '')
    amount = req_data.get('amount', '')
    pay_id = req_data.get('pay_id', '')
    status = req_data.get('status', '')
    sign_received = req_data.get('sign', '')
    
    sign_string = f"{currency}:{amount}:{pay_id}:{project_id}:{status}:{secret_key}"
    sign_computed = hashlib.sha256(sign_string.encode('utf-8')).hexdigest()
    
    if sign_computed != sign_received:
        return "wrong sign!", 400
        
    if status != 'paid':
        return "OK", 200
        
    invoice = query_one("SELECT * FROM invoices WHERE id = ?", (pay_id,))
    if not invoice:
        return "invoice not found", 404
        
    if invoice["status"] == 'paid':
        return "OK", 200
        
    execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (pay_id,))
    
    user_id = invoice["user_id"]
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    
    if user:
        now = datetime.now()
        months_paid = invoice["months"] if invoice["months"] else 1
        days_to_add = months_paid * 30
        
        if user["expires_at"]:
            try:
                current_expires = datetime.strptime(user["expires_at"], "%Y-%m-%d %H:%M:%S")
                if current_expires > now:
                    new_expires = current_expires + timedelta(days=days_to_add)
                else:
                    new_expires = now + timedelta(days=days_to_add)
            except ValueError:
                new_expires = now + timedelta(days=days_to_add)
        else:
            new_expires = now + timedelta(days=days_to_add)
            
        expires_str = new_expires.strftime("%Y-%m-%d %H:%M:%S")
        
        # Integrate with Remnawave
        # Transliterate cyrillic to latin and sanitize
        cyrillic_translit = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
            'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
            'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
            'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
        }
        
        safe_name = user['full_name'].lower()
        for cyr, lat in cyrillic_translit.items():
            safe_name = safe_name.replace(cyr, lat)
            
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', safe_name)
        rw_username = f"User-{user_id}-{safe_name}"
        rw_username = re.sub(r'-+', '-', rw_username).strip('-')
        
        sub_url = remnawave_create_or_extend_user(rw_username, expires_str)
        
        if sub_url:
            execute("UPDATE users SET status = 'active', expires_at = ?, subscription_url = ?, notified_3d=0, notified_1d=0, notified_10h=0, notified_1h=0 WHERE id = ?", (expires_str, sub_url, user_id))
        else:
            execute("UPDATE users SET status = 'active', expires_at = ?, notified_3d=0, notified_1d=0, notified_10h=0, notified_1h=0 WHERE id = ?", (expires_str, user_id))
        
        telegram_id = user["telegram_id"]
        if telegram_id:
            bot_token = os.environ.get("BOT_TOKEN")
            if bot_token:
                msg = "✅ Подписка успешно оплачена! Доступ к VPN активен.\n"
                if sub_url:
                    msg += f"\nВот ваша ссылка на подключение:\n`{sub_url}`\n"
                msg += "\nСсылка на конфигурацию также доступна в личном кабинете на сайте."
                
                try:
                    requests.post(f"http://91.238.123.4:10080/bot{bot_token}/sendMessage", data={
                        "chat_id": telegram_id,
                        "text": msg
                    }, timeout=5)
                except Exception:
                    pass
                
        # Referral Bonus Processing
        if user["referrer_id"] and not user.get("has_brought_referral_bonus", 0):
            referrer = query_one("SELECT * FROM users WHERE id = ?", (user["referrer_id"],))
            if referrer:
                try:
                    bonus_days = (int(float(amount)) // 200) * 7
                except (ValueError, TypeError):
                    bonus_days = 7
                    
                if bonus_days > 0:
                    ref_now = datetime.now()
                    if referrer["expires_at"] and referrer["expires_at"] != 'Безлимит':
                        try:
                            ref_exp = datetime.strptime(referrer["expires_at"], "%Y-%m-%d %H:%M:%S")
                            ref_new_exp = max(ref_exp, ref_now) + timedelta(days=bonus_days)
                        except ValueError:
                            ref_new_exp = ref_now + timedelta(days=bonus_days)
                    elif referrer["expires_at"] == 'Безлимит':
                        ref_new_exp = None # Don't update unlimited
                    else:
                        ref_new_exp = ref_now + timedelta(days=bonus_days)
                        
                    if ref_new_exp:
                        ref_exp_str = ref_new_exp.strftime("%Y-%m-%d %H:%M:%S")
                        
                        ref_safe_name = referrer['full_name'].lower()
                        for cyr, lat in cyrillic_translit.items():
                            ref_safe_name = ref_safe_name.replace(cyr, lat)
                        ref_safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', ref_safe_name)
                        ref_rw_username = f"User-{referrer['id']}-{ref_safe_name}"
                        ref_rw_username = re.sub(r'-+', '-', ref_rw_username).strip('-')
                        
                        ref_sub_url = remnawave_create_or_extend_user(ref_rw_username, ref_exp_str)
                        if ref_sub_url:
                            execute("UPDATE users SET expires_at = ?, subscription_url = ?, notified_3d=0, notified_1d=0, notified_10h=0, notified_1h=0 WHERE id = ?", (ref_exp_str, ref_sub_url, referrer["id"]))
                        else:
                            execute("UPDATE users SET expires_at = ?, notified_3d=0, notified_1d=0, notified_10h=0, notified_1h=0 WHERE id = ?", (ref_exp_str, referrer["id"]))
                            
                        # Notify referrer
                        ref_tg_id = referrer["telegram_id"]
                        if ref_tg_id and bot_token:
                            ref_msg = f"🎉 <b>Ура! Твой друг оплатил подписку.</b>\n\nТебе начислено <b>+{bonus_days} дней</b> к подписке в качестве бонуса по реферальной программе!\n\nНовая дата окончания: {ref_exp_str}"
                            try:
                                requests.post(f"http://91.238.123.4:10080/bot{bot_token}/sendMessage", data={
                                    "chat_id": ref_tg_id,
                                    "text": ref_msg,
                                    "parse_mode": "HTML"
                                }, timeout=5)
                            except Exception:
                                pass
                                
            execute("UPDATE users SET has_brought_referral_bonus = 1 WHERE id = ?", (user_id,))
                
    return "OK", 200

@app.route("/activate-trial", methods=["POST"])
@login_required
def activate_trial():
    user = g.user
    if user["has_trial_used"]:
        flash("Вы уже использовали пробный период.", "error")
        return redirect(url_for("dashboard"))
        
    if user["status"] == "active" or user["expires_at"]:
        flash("У вас уже есть подписка.", "error")
        return redirect(url_for("dashboard"))
        
    # Give 7 days trial if user was referred, else 5 days
    days_to_add = 7 if user["referrer_id"] else 5
    now = datetime.now()
    new_expires = now + timedelta(days=days_to_add)
    expires_str = new_expires.strftime("%Y-%m-%d %H:%M:%S")
    
    # Transliterate cyrillic to latin and sanitize
    cyrillic_translit = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    safe_name = user['full_name'].lower()
    for cyr, lat in cyrillic_translit.items():
        safe_name = safe_name.replace(cyr, lat)
        
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', safe_name)
    rw_username = f"Trial-{user['id']}-{safe_name}"
    rw_username = re.sub(r'-+', '-', rw_username).strip('-')
    
    sub_url = remnawave_create_or_extend_user(rw_username, expires_str)
    
    if sub_url:
        execute("UPDATE users SET status = 'active', expires_at = ?, subscription_url = ?, has_trial_used = 1, notified_3d=0, notified_1d=0, notified_10h=0, notified_1h=0 WHERE id = ?", 
               (expires_str, sub_url, user["id"]))
               
        telegram_id = user["telegram_id"]
        if telegram_id:
            bot_token = os.environ.get("BOT_TOKEN")
            if bot_token:
                msg = f"🎁 Пробный период на 5 дней активирован!\n\nВот ваша ссылка на подключение:\n`{sub_url}`\n\nПриятного пользования!"
                try:
                    requests.post(f"http://91.238.123.4:10080/bot{bot_token}/sendMessage", data={
                        "chat_id": telegram_id,
                        "text": msg,
                        "parse_mode": "Markdown"
                    }, timeout=5)
                except Exception:
                    pass
        flash("Бесплатный пробный период успешно активирован!", "success")
    else:
        flash("Произошла ошибка при генерации ключа. Пожалуйста, обратитесь в поддержку.", "error")
        
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


import secrets

@app.route("/dashboard")
@login_required
def dashboard():
    user = dict(g.user) if g.user else {}
    if not user["telegram_id"] and not user["tg_link_token"]:
        token = secrets.token_urlsafe(16)
        execute("UPDATE users SET tg_link_token = ? WHERE id = ?", (token, user["id"]))
        user = query_one("SELECT * FROM users WHERE id = ?", (user["id"],))
        
    has_password = bool(user["password_hash"])
    return render_template("dashboard.html", user=user, has_password=has_password)


@app.route("/set-password", methods=["POST"])
@login_required
def set_password():
    new_login = request.form.get("login", "").strip()
    password = request.form.get("password", "")
    
    if len(password) < 6:
        flash("Пароль должен быть не короче 6 символов.", "error")
        return redirect(url_for("dashboard"))
        
    if not new_login or len(new_login) < 3:
        flash("Логин должен быть не короче 3 символов.", "error")
        return redirect(url_for("dashboard"))
        
    # Check if login is unique (excluding current user)
    existing = query_one("SELECT id FROM users WHERE lower(full_name) = lower(?) AND id != ?", (new_login, g.user["id"]))
    if existing:
        flash("Этот логин уже занят другим пользователем. Пожалуйста, придумайте другой (например, добавьте цифры).", "error")
        return redirect(url_for("dashboard"))

    password_hash = generate_password_hash(password)
    execute("UPDATE users SET password_hash = ?, full_name = ? WHERE id = ?", (password_hash, new_login, g.user["id"]))
    flash(f"Отлично! Теперь вы можете входить на сайт по логину «{new_login}» и вашему паролю.", "success")
    return redirect(url_for("dashboard"))


@app.route("/inst-landing")
def instructions():
    return render_template("inst-landing.html")


@app.route("/inst-landing/ios")
def instructions_ios():
    return render_instruction_page(INSTRUCTION_TEMPLATES["ios"])


@app.route("/inst-landing/android")
def instructions_android():
    return render_instruction_page(INSTRUCTION_TEMPLATES["android"])


@app.route("/inst-landing/windows")
def instructions_windows():
    return render_instruction_page(INSTRUCTION_TEMPLATES["windows"])


@app.route("/inst-landing/macos")
def instructions_macos():
    return render_instruction_page(INSTRUCTION_TEMPLATES["macos"])


@app.route("/admin/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def admin_login():
    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password = request.form.get("password", "")

        error = "Неверный логин или пароль."

        if not ADMIN_PASSWORD_HASH:
            flash(
                "ADMIN_PASSWORD_HASH не задан. Сначала добавь переменные окружения.",
                "error",
            )
            return render_template("admin_login.html")

        if login_value == ADMIN_LOGIN and check_password_hash(
            ADMIN_PASSWORD_HASH, password
        ):
            session.clear()
            session.permanent = True
            session["is_admin"] = True
            return redirect(url_for("admin_panel"))

        flash(error, "error")

    return render_template("admin_login.html")


@app.route("/admin/broadcast", methods=["POST"])
def admin_broadcast():
    if "admin_logged_in" not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Empty message"}), 400
        
    bot_token = os.environ.get("BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")
    if not bot_token:
        return jsonify({"success": False, "error": "Bot token not configured"}), 500
        
    users = execute("SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL", fetchall=True)
    
    success_count = 0
    import time
    for u in users:
        tg_id = u["telegram_id"]
        try:
            resp = requests.post(
                f"http://91.238.123.4:10080/bot{bot_token}/sendMessage",
                json={"chat_id": tg_id, "text": text, "parse_mode": "HTML"},
                timeout=5
            )
            if resp.status_code == 200:
                success_count += 1
            time.sleep(0.05) # Prevent rate limiting
        except Exception as e:
            print(f"Failed to send broadcast to {tg_id}: {e}")
            
    flash(f"Рассылка успешно отправлена {success_count} пользователям", "success")
    return redirect(url_for("admin_panel"))

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_panel():
    users = query_all(
        """
        SELECT id, full_name, status, subscription_url, instructions_url, expires_at, created_at
        FROM users
        ORDER BY created_at DESC, id DESC
        """
    )
    return render_template("admin_panel.html", users=users)


@app.route("/admin/user/<int:user_id>/update", methods=["POST"])
@admin_required
def admin_update_user(user_id):
    full_name = request.form.get("full_name", "").strip()
    status = request.form.get("status", "").strip()
    subscription_url = request.form.get("subscription_url", "").strip() or None
    instructions_url = request.form.get("instructions_url", "").strip() or "/inst-landing"
    expires_at = request.form.get("expires_at", "").strip() or None

    allowed_statuses = {"new", "pending", "active", "expired"}
    if status not in allowed_statuses:
        flash("Недопустимый статус.", "error")
        return redirect(url_for("admin_panel"))

    if not full_name:
        flash("ФИО не может быть пустым.", "error")
        return redirect(url_for("admin_panel"))

    execute(
        """
        UPDATE users
        SET full_name = ?, status = ?, subscription_url = ?, instructions_url = ?, expires_at = ?
        WHERE id = ?
        """,
        (full_name, status, subscription_url, instructions_url, expires_at, user_id),
    )
    flash("Пользователь обновлён.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    flash("Пользователь удалён.", "success")
    return redirect(url_for("admin_panel"))


if __name__ == "__main__":
    app.run(debug=True)
