import os
import sqlite3
from datetime import timedelta
from functools import wraps

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
        if not session.get("user_id"):
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
            error = "Введите ФИО."
        elif len(full_name) < 5:
            error = "ФИО выглядит слишком коротким."
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
            error = "Пользователь с таким ФИО уже существует."

        if error is None:
            password_hash = generate_password_hash(password)
            execute(
                """
                INSERT INTO users (full_name, password_hash, status, instructions_url)
                VALUES (?, ?, 'pending', ?)
            """,
                (full_name, password_hash, "/inst-landing"),
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
            execute_db(
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


import requests
from datetime import datetime, timedelta

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
    
    execute_db("INSERT INTO invoices (user_id, amount, months) VALUES (?, ?, ?)", (user_id, amount, months))
    invoice = query_one("SELECT * FROM invoices WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    pay_id = str(invoice["id"])
    
    currency = "RUB"
    desc = f"Оплата подписки Void VPN на {months} мес."
    
    success_url = url_for('dashboard', _external=True)
    fail_url = url_for('dashboard', _external=True)
    
    sign_string = f"{project_id}:{pay_id}:{amount}:{currency}:{desc}:{success_url}:{fail_url}:{secret_key}"
    sign = hashlib.sha256(sign_string.encode('utf-8')).hexdigest()
    
    url = f"https://anypay.io/merchant?merchant_id={project_id}&pay_id={pay_id}&amount={amount}&currency={currency}&desc={desc}&success_url={success_url}&fail_url={fail_url}&sign={sign}"
    
    return redirect(url)


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
        
    execute_db("UPDATE invoices SET status = 'paid' WHERE id = ?", (pay_id,))
    
    user_id = invoice["user_id"]
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    
    if user:
        now = datetime.now()
        months_paid = invoice.get("months", 1)
        days_to_add = months_paid * 30
        
        if user["expires_at"]:
            try:
                current_expires = datetime.strptime(user["expires_at"], "%Y-%m-%d")
                if current_expires > now:
                    new_expires = current_expires + timedelta(days=days_to_add)
                else:
                    new_expires = now + timedelta(days=days_to_add)
            except ValueError:
                new_expires = now + timedelta(days=days_to_add)
        else:
            new_expires = now + timedelta(days=days_to_add)
            
        expires_str = new_expires.strftime("%Y-%m-%d")
        execute_db("UPDATE users SET status = 'active', expires_at = ? WHERE id = ?", (expires_str, user_id))
        
        telegram_id = user["telegram_id"]
        if telegram_id:
            bot_token = os.environ.get("BOT_TOKEN")
            if bot_token:
                msg = "✅ Подписка успешно оплачена! Доступ к VPN активен.\nСсылка на конфигурацию доступна в личном кабинете на сайте."
                try:
                    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", data={
                        "chat_id": telegram_id,
                        "text": msg
                    }, timeout=5)
                except Exception:
                    pass
                
    return "OK", 200



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


import secrets

@app.route("/dashboard")
@login_required
def dashboard():
    user = dict(g.user) if g.user else {}
    if not user.get("telegram_id") and not user.get("tg_link_token"):
        # Generate a new token
        token = secrets.token_urlsafe(16)
        execute_db("UPDATE users SET tg_link_token = ? WHERE id = ?", (token, user["id"]))
        user["tg_link_token"] = token
    return render_template("dashboard.html", user=user)


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
