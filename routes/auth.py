import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from utils import query_one, execute, check_telegram_authorization, check_webapp_authorization, login_required
from extensions import limiter, csrf
import logging

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard.dashboard"))
        
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
        ref = request.args.get("ref") or request.form.get("ref") or session.get("ref")
        if ref and str(ref).isdigit():
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
            flash("Ваш аккаунт успешно создан. Пожалуйста, войдите в систему.", "success")
            return redirect(url_for("auth.login"))

        flash(error, "error")

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.dashboard"))
        
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
            return redirect(url_for("dashboard.dashboard"))

        flash(error, "error")

    return render_template("login.html")


@auth_bp.route("/auth/telegram")
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
            return redirect(url_for("dashboard.dashboard"))
        else:
            execute(
                "INSERT INTO users (full_name, telegram_id, status) VALUES (?, ?, ?)",
                (first_name, telegram_id, "new")
            )
            new_user = query_one("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            session.clear()
            session.permanent = True
            session["user_id"] = new_user["id"]
            return redirect(url_for("dashboard.dashboard"))
    
    flash("Ошибка авторизации Telegram", "error")
    return redirect(url_for("auth.login"))


@auth_bp.route("/auth/webapp", methods=["POST"])
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


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))

