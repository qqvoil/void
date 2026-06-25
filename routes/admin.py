import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import requests
from utils import admin_required, query_one, query_all, execute
import logging

admin_bp = Blueprint('admin', __name__)

ADMIN_LOGIN = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

@admin_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password = request.form.get("password", "")

        error = "Вы ввели неверный логин или пароль."

        if not ADMIN_PASSWORD_HASH:
            flash(
                "Конфигурация сервера неполная. Задай ADMIN_PASSWORD_HASH.",
                "error",
            )
            return render_template("admin_login.html")

        if login_value == ADMIN_LOGIN and check_password_hash(
            ADMIN_PASSWORD_HASH, password
        ):
            session.clear()
            session.permanent = True
            session["is_admin"] = True
            return redirect(url_for("admin.admin_panel"))

        flash(error, "error")

    return render_template("admin_login.html")


@admin_bp.route("/admin/broadcast", methods=["POST"])
@admin_required
def admin_broadcast():
    text = request.form.get("text", "").strip()
    attach_image = request.form.get("attach_image") == "1"
    
    bot_token = os.environ.get("BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")
    if not bot_token:
        flash("Bot token not configured", "danger")
        return redirect(url_for("admin.admin_panel"))
        
    users = query_all("SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL")
    
    success_count = 0
    import time
    for u in users:
        tg_id = u["telegram_id"]
        try:
            if attach_image:
                with open("/opt/void/static/img/fill_bot.jpg", "rb") as f:
                    resp = requests.post(
                        f"http://91.238.123.4:10080/bot{bot_token}/sendPhoto",
                        data={"chat_id": tg_id, "caption": text, "parse_mode": "HTML"},
                        files={"photo": f},
                        timeout=10
                    )
            else:
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
    return redirect(url_for("admin.admin_panel"))

@admin_bp.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin.admin_login"))


@admin_bp.route("/admin")
@admin_required
def admin_panel():
    q = request.args.get('q', '').strip()
    
    # Auto-expire any past due subscriptions for accurate admin display
    execute("UPDATE users SET status = 'expired' WHERE status IN ('active', 'trial') AND expires_at IS NOT NULL AND expires_at != 'Безлимит' AND expires_at < datetime('now')")
    
    query = """
        SELECT 
            u.id, u.full_name, u.status, u.subscription_url, u.instructions_url, 
            u.expires_at, u.created_at, u.is_legacy, u.telegram_id, u.referrer_id,
            (SELECT COUNT(*) FROM users r WHERE r.referrer_id = u.id) as ref_count,
            (SELECT COUNT(*) FROM users r WHERE r.referrer_id = u.id AND r.has_brought_referral_bonus = 1) * 7 as ref_bonus_days
        FROM users u
    """
    params = []
    if q:
        query += " WHERE u.full_name LIKE ? OR u.telegram_id LIKE ? OR u.id = ?"
        params.extend([f"%{q}%", f"%{q}%", q])
        
    query += " ORDER BY u.created_at DESC, u.id DESC"
    
    users = [dict(u) for u in query_all(query, params)]
    
    # Fetch active devices/online status from Remnawave
    api_key = os.environ.get("RW_API_KEY")
    rw_users = {}
    if api_key:
        try:
            resp = requests.get(
                "https://panel.jointhevoid.ru/api/users",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5
            )
            if resp.status_code == 200:
                resp_data = resp.json().get("response", {})
                if isinstance(resp_data, dict):
                    users_list = resp_data.get("users", [])
                elif isinstance(resp_data, list):
                    users_list = resp_data
                else:
                    users_list = []
                    
                for ru in users_list:
                    if isinstance(ru, dict):
                        sub_url = ru.get("subscriptionUrl")
                        online_at = ru.get("userTraffic", {}).get("onlineAt")
                        if sub_url and online_at:
                            # Check if online within last 5 minutes
                            try:
                                online_dt = datetime.fromisoformat(online_at.replace("Z", "+00:00"))
                                if datetime.now(timezone.utc) - online_dt < timedelta(minutes=5):
                                    rw_users[sub_url] = 1 # Consider as 1 active device/online
                            except:
                                pass
        except Exception as e:
            logging.error(f"Error fetching remnawave users for admin: {e}")
            
    # Attach rw_users data
    for u in users:
        sub_url = u.get("subscription_url")
        u["active_devices"] = rw_users.get(sub_url, 0)

    mrr_query = query_one("SELECT SUM(amount) as mrr FROM invoices WHERE status = 'paid' AND created_at >= date('now', '-30 days')")
    mrr = mrr_query["mrr"] if mrr_query and mrr_query["mrr"] else 0
    
    today_rev_query = query_one("SELECT SUM(amount) as rev FROM invoices WHERE status = 'paid' AND date(created_at) = date('now')")
    today_rev = today_rev_query["rev"] if today_rev_query and today_rev_query["rev"] else 0
    
    users_today_query = query_one("SELECT COUNT(*) as count FROM users WHERE date(created_at) = date('now')")
    users_today = users_today_query["count"] if users_today_query else 0
    
    total_users_query = query_one("SELECT COUNT(*) as count FROM users")
    total_users = total_users_query["count"] if total_users_query else 0
    
    paid_users_query = query_one("SELECT COUNT(DISTINCT user_id) as count FROM invoices WHERE status = 'paid'")
    paid_users = paid_users_query["count"] if paid_users_query else 0
    
    conversion = 0
    if total_users > 0:
        conversion = round((paid_users / total_users) * 100, 1)
        
    stats = {
        "mrr": mrr,
        "today_rev": today_rev,
        "users_today": users_today,
        "total_users": total_users,
        "conversion": conversion
    }
    
    promocodes = []
    try:
        promocodes = [dict(p) for p in query_all("SELECT * FROM promocodes ORDER BY id DESC")]
    except:
        pass

    return render_template("admin_panel.html", users=users, stats=stats, promocodes=promocodes)


@admin_bp.route("/admin/user/<int:user_id>/update", methods=["POST"])
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
        return redirect(url_for("admin.admin_panel"))

    if not full_name:
        flash("ФИО не может быть пустым.", "error")
        return redirect(url_for("admin.admin_panel"))

    execute(
        """
        UPDATE users
        SET full_name = ?, status = ?, subscription_url = ?, instructions_url = ?, expires_at = ?
        WHERE id = ?
        """,
        (full_name, status, subscription_url, instructions_url, expires_at, user_id),
    )
    flash("Пользователь обновлён.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    execute("DELETE FROM users WHERE id = ?", (user_id,))
    flash("Пользователь удалён.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/promocode/add", methods=["POST"])
@admin_required
def admin_add_promocode():
    code = request.form.get("code", "").strip().upper()
    discount = request.form.get("discount_percent", type=int, default=0)
    max_uses = request.form.get("max_uses", type=int, default=0)
    
    if not code or discount <= 0 or discount > 100:
        flash("Некорректные данные для промокода.", "error")
        return redirect(url_for("admin.admin_panel"))
        
    try:
        execute("INSERT INTO promocodes (code, discount_percent, max_uses) VALUES (?, ?, ?)", (code, discount, max_uses))
        flash("Промокод успешно добавлен.", "success")
    except Exception as e:
        flash("Ошибка (возможно, промокод уже существует).", "error")
        
    return redirect(url_for("admin.admin_panel"))

@admin_bp.route("/admin/promocode/<int:promo_id>/delete", methods=["POST"])
@admin_required
def admin_delete_promocode(promo_id):
    try:
        execute("DELETE FROM promocodes WHERE id = ?", (promo_id,))
        flash("Промокод удален.", "success")
    except:
        flash("Ошибка при удалении.", "error")
    return redirect(url_for("admin.admin_panel"))
