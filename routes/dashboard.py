import os
from flask import Blueprint, render_template, request, session, redirect, url_for, g, flash
from werkzeug.security import generate_password_hash
import secrets
from utils import login_required, query_one, execute
from extensions import limiter

dashboard_bp = Blueprint('dashboard', __name__)

TEMPLATES_DIR = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "templates")
def render_instruction_page(template_name):
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    if os.path.exists(template_path):
        return render_template(template_name)
    return render_template("inst-landing.html")


@dashboard_bp.route("/webapp")
def webapp():
    # Telegram Android WebApp sometimes gets stuck on 302 redirects.
    # We return a 200 OK page that redirects via JS.
    target_url = url_for("dashboard.dashboard") if session.get("user_id") else url_for("auth.login")
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


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    user = dict(g.user) if g.user else {}
    if not user["telegram_id"] and not user["tg_link_token"]:
        token = secrets.token_urlsafe(16)
        execute("UPDATE users SET tg_link_token = ? WHERE id = ?", (token, user["id"]))
        user = query_one("SELECT * FROM users WHERE id = ?", (user["id"],))
        
    has_password = bool(user["password_hash"])
    return render_template("dashboard.html", user=user, has_password=has_password)


@dashboard_bp.route("/set-password", methods=["POST"])
@login_required
def set_password():
    new_login = request.form.get("login", "").strip()
    password = request.form.get("password", "")
    
    if len(password) < 6:
        flash("Ваш пароль слишком короткий.", "error")
        return redirect(url_for("dashboard.dashboard"))
        
    if not new_login or len(new_login) < 3:
        flash("Ваш логин слишком короткий.", "error")
        return redirect(url_for("dashboard.dashboard"))
        
    # Check if login is unique (excluding current user)
    existing = query_one("SELECT id FROM users WHERE lower(full_name) = lower(?) AND id != ?", (new_login, g.user["id"]))
    if existing:
        flash("Этот логин уже занят.", "error")
        return redirect(url_for("dashboard.dashboard"))

    password_hash = generate_password_hash(password)
    execute("UPDATE users SET password_hash = ?, full_name = ? WHERE id = ?", (password_hash, new_login, g.user["id"]))
    flash("Данные обновлены.", "success")
    return redirect(url_for("dashboard.dashboard"))


@dashboard_bp.route("/inst-landing")
def instructions():
    return render_template("inst-landing.html")


@dashboard_bp.route("/inst-landing/ios")
def instructions_ios():
    return render_instruction_page(INSTRUCTION_TEMPLATES["ios"])


@dashboard_bp.route("/inst-landing/android")
def instructions_android():
    return render_instruction_page(INSTRUCTION_TEMPLATES["android"])


@dashboard_bp.route("/inst-landing/windows")
def instructions_windows():
    return render_instruction_page(INSTRUCTION_TEMPLATES["windows"])


@dashboard_bp.route("/inst-landing/macos")
def instructions_macos():
    return render_instruction_page(INSTRUCTION_TEMPLATES["macos"])


