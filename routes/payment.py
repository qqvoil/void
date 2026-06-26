import os
import json
import requests
import hashlib
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, redirect, url_for, flash, g
from utils import query_one, execute, login_required, get_remnawave_squad_uuid, remnawave_create_or_extend_user, get_db
from extensions import csrf, limiter
import logging

payment_bp = Blueprint('payment', __name__)

@payment_bp.route("/payment/pay", methods=["POST"])
@login_required
def payment_pay():
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
        
    promo_code = request.form.get("promo_code", "").strip().upper()
    used_promo = None
    if promo_code:
        promo = query_one("SELECT * FROM promocodes WHERE code = ?", (promo_code,))
        if promo:
            if promo["max_uses"] == 0 or promo["current_uses"] < promo["max_uses"]:
                discount = promo["discount_percent"]
                amount = int(amount * (1 - discount / 100.0))
                used_promo = promo["code"]
                execute("UPDATE promocodes SET current_uses = current_uses + 1 WHERE code = ?", (promo["code"],))
            else:
                flash("Лимит использований промокода исчерпан.", "error")
                return redirect(url_for("dashboard.dashboard"))
        else:
            flash("Неверный промокод.", "error")
            return redirect(url_for("dashboard.dashboard"))
            
    user_id = g.user["id"]
    
    execute("INSERT INTO invoices (user_id, amount, months, promo_code) VALUES (?, ?, ?, ?)", (user_id, amount, months, used_promo))
    invoice = query_one("SELECT * FROM invoices WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
    pay_id = str(invoice["id"])
    
    # -------------------------------------------------------------
    # Интеграция Platega.io
    # -------------------------------------------------------------
    try:
        project_id = os.environ.get("PLATEGA_PROJECT_ID")
        secret_key = os.environ.get("PLATEGA_SECRET_KEY")
        
        if not project_id or not secret_key:
            flash("Оплата временно недоступна (касса не настроена).", "error")
            return redirect(url_for("dashboard.dashboard"))

        url = "https://app.platega.io/v2/transaction/process"
        headers = {
            "X-MerchantId": project_id,
            "X-Secret": secret_key,
            "Content-Type": "application/json"
        }
        payload = {
            "paymentDetails": {
                "amount": int(float(amount)),
                "currency": "RUB"
            },
            "description": f"Подписка Void ({months} мес.)",
            "return": "https://jointhevoid.ru/dashboard",
            "failedUrl": "https://jointhevoid.ru/dashboard",
            "payload": pay_id
        }
        
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            payment_url = data.get("url")
            if payment_url:
                return redirect(payment_url)
            else:
                logging.error(f"Platega error response: {data}")
                flash("Касса не вернула ссылку на оплату.", "error")
                return redirect(url_for("dashboard.dashboard"))
        else:
            logging.error(f"Platega API error: {resp.status_code} {resp.text}")
            flash("Ошибка при создании платежа на стороне кассы.", "error")
            return redirect(url_for("dashboard.dashboard"))
            
    except Exception as e:
        logging.error(f"Platega create_invoice error: {e}")
        flash("Ошибка при создании платежа.", "error")
        return redirect(url_for("dashboard.dashboard"))

# --- Remnawave API Client ---

@payment_bp.route("/payment/platega/webhook", methods=["POST"])
@csrf.exempt
def platega_webhook():
    secret_key = os.environ.get("PLATEGA_SECRET_KEY")
    
    incoming_secret = request.headers.get("X-Secret")
    if secret_key and incoming_secret != secret_key:
        return "Unauthorized", 401
        
    try:
        data = request.json
        if not data:
            return "No data", 400
            
        logging.info(f"Platega webhook payload: {data}")
            
        status = data.get("status")
        pay_id = data.get("payload")
        
        if status == "CONFIRMED" and pay_id:
            invoice = query_one("SELECT * FROM invoices WHERE id = ?", (int(pay_id),))
            if invoice and invoice["status"] == "pending":
                execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (invoice["id"],))
                days = invoice["months"] * 30
                add_subscription(invoice["user_id"], days)
                
                from utils import notify_admin
                user_record = query_one("SELECT full_name FROM users WHERE id = ?", (invoice["user_id"],))
                name = user_record["full_name"] if user_record else "Неизвестный"
                notify_admin(f"💰 <b>Успешная оплата!</b>\nПользователь: <code>{name}</code>\nСумма: <b>{invoice['amount']} ₽</b>\nДней: {days}")
                
                # Referral logic
                user_obj = query_one("SELECT referrer_id, has_brought_referral_bonus FROM users WHERE id = ?", (invoice["user_id"],))
                if user_obj and user_obj["referrer_id"] and not user_obj["has_brought_referral_bonus"]:
                    referrer = query_one("SELECT id, telegram_id FROM users WHERE id = ?", (user_obj["referrer_id"],))
                    if referrer:
                        bonus_days = 0
                        amount = invoice["amount"]
                        if amount == 200:
                            bonus_days = 7
                        elif amount == 510:
                            bonus_days = 15
                        elif amount == 910:
                            bonus_days = 30
                        elif amount == 1800:
                            bonus_days = 90
                            
                        if bonus_days > 0:
                            add_subscription(referrer["id"], bonus_days)
                            execute("UPDATE users SET has_brought_referral_bonus = 1 WHERE id = ?", (invoice["user_id"],))
                            logging.info(f"Referral bonus {bonus_days} days added to user {referrer['id']} for paying user {invoice['user_id']}")
                            
                            if referrer["telegram_id"]:
                                bot_token = os.environ.get("BOT_TOKEN")
                                if bot_token:
                                    msg = f"🎉 <b>Бонус за друга!</b>\n\nВаш друг только что оплатил подписку, и вам начислено <b>{bonus_days}</b> бесплатных дней! 🚀"
                                    try:
                                        requests.post(f"http://91.238.123.4:10080/bot{bot_token}/sendMessage", data={
                                            "chat_id": referrer["telegram_id"],
                                            "text": msg,
                                            "parse_mode": "HTML"
                                        }, timeout=5)
                                    except Exception:
                                        pass
                                        
                logging.info(f"Invoice {pay_id} marked as PAID via Platega Webhook.")
                
        return "OK", 200
        
    except Exception as e:
        logging.error(f"Platega webhook error: {e}")
        return "Internal Server Error", 500

def add_subscription(user_id, days_to_add):
    user = query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        return
        
    now = datetime.now()
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
    # Using 'Void-' prefix for all subscriptions consistently
    rw_username = f"Void-{user['id']}-{safe_name}"
    rw_username = re.sub(r'-+', '-', rw_username).strip('-')
    
    sub_url = remnawave_create_or_extend_user(rw_username, expires_str)
    
    if sub_url:
        execute(
            "UPDATE users SET expires_at = ?, status = ?, subscription_url = ? WHERE id = ?",
            (expires_str, "active", sub_url, user["id"])
        )
        # Notify via bot if tg id is present
        if user["telegram_id"]:
            try:
                import requests
                bot_token = os.environ.get("TG_BOT_TOKEN")
                if bot_token:
                    text = f"✅ Ваша подписка успешно продлена до {expires_str}!"
                    requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                        "chat_id": user["telegram_id"],
                        "text": text
                    }, timeout=5)
            except Exception as e:
                logging.error(f"Failed to notify user {user_id}: {e}")

@payment_bp.route("/activate-trial", methods=["POST"])
@login_required
@limiter.limit("2 per day", error_message="Слишком много попыток. Попробуйте позже.")
def activate_trial():
    user = g.user
    
    if user["status"] == "active" or user["expires_at"]:
        flash("У вас уже есть активная подписка.", "error")
        return redirect(url_for("dashboard.dashboard"))
    db = get_db()
    cursor = db.execute("UPDATE users SET has_trial_used = 1 WHERE id = ? AND has_trial_used = 0", (user["id"],))
    db.commit()
    
    if cursor.rowcount == 0:
        flash("Пробный период уже использован или находится в процессе активации.", "error")
        return redirect(url_for("dashboard.dashboard"))
        
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
    rw_username = f"Void-{user['id']}-{safe_name}"
    rw_username = re.sub(r'-+', '-', rw_username).strip('-')
    
    sub_url = remnawave_create_or_extend_user(rw_username, expires_str)
    
    if sub_url:
        execute("UPDATE users SET status = 'active', expires_at = ?, subscription_url = ?, notified_3d=0, notified_1d=0, notified_10h=0, notified_1h=0 WHERE id = ?", 
               (expires_str, sub_url, user["id"]))
               
        telegram_id = user["telegram_id"]
        if telegram_id:
            bot_token = os.environ.get("BOT_TOKEN")
            if bot_token:
                msg = f"<b>Пробный период активирован.</b>\n\nВам предоставлено {days_to_add} дней доступа.\nКонфигурация для подключения:\n`{sub_url}`"
                try:
                    requests.post(f"http://91.238.123.4:10080/bot{bot_token}/sendMessage", data={
                        "chat_id": telegram_id,
                        "text": msg,
                        "parse_mode": "HTML"
                    }, timeout=5)
                except Exception:
                    pass
        flash("Доступ активирован.", "success")
    else:
        flash("Ошибка генерации ключа. Обратитесь в поддержку.", "error")
        
    return redirect(url_for("dashboard.dashboard"))

