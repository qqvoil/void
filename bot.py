import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import WebAppInfo
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN provided in environment variables")

session = AiohttpSession(
    api=TelegramAPIServer.from_base("http://91.238.123.4:10080")
)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

# Store the last menu message ID for each user to clean up chat
user_menus = {}

def link_account(token: str, telegram_id: int) -> bool:
    """Find user by token and link telegram_id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE tg_link_token = ?", (token,))
    user = cursor.fetchone()
    
    if user:
        try:
            cursor.execute(
                "UPDATE users SET telegram_id = ?, tg_link_token = NULL WHERE id = ?",
                (telegram_id, user[0])
            )
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
    else:
        success = False
        
    conn.close()
    return success

def get_user_by_tg(telegram_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, status, expires_at FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📱 Личный кабинет", web_app=WebAppInfo(url="https://jointhevoid.ru/dashboard?v=2")))
    builder.row(InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="support"))
    return builder.as_markup()

async def send_or_update_menu(chat_id: int, text: str, markup: InlineKeyboardMarkup):
    """Deletes previous menu if it exists, and sends a new one."""
    if chat_id in user_menus:
        try:
            await bot.delete_message(chat_id, user_menus[chat_id])
        except Exception:
            pass # Message might be already deleted by user
            
    msg = await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    user_menus[chat_id] = msg.message_id

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    # Delete the user's /start command to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    args = message.text.split(maxsplit=1)
    payload = args[1] if len(args) > 1 else None
    telegram_id = message.from_user.id

    if payload:
        success = link_account(payload, telegram_id)
        if success:
            await send_or_update_menu(
                telegram_id,
                f"✅ <b>Успешно!</b> Твой Telegram-аккаунт привязан к профилю Void VPN.\n\n"
                f"Теперь ты будешь получать здесь важные уведомления и можешь общаться с поддержкой.",
                get_main_keyboard()
            )
        else:
            await send_or_update_menu(
                telegram_id,
                "❌ Ссылка для привязки недействительна или этот Telegram уже привязан к другому аккаунту.",
                get_main_keyboard()
            )
    else:
        user = get_user_by_tg(telegram_id)
        welcome_text = (
            "🌌 <b>Добро пожаловать в Void VPN!</b>\n\n"
            "Здесь ты можешь управлять своей подпиской, быстро заходить в личный кабинет и обращаться в службу поддержки.\n\n"
        )
        if user:
            name, status, expires = user
            welcome_text += f"👤 <b>Пользователь:</b> {name}\n"
            welcome_text += f"📊 <b>Статус:</b> {status}\n"
            if expires:
                welcome_text += f"⏳ <b>Истекает:</b> {expires}\n"
        else:
            welcome_text += (
                "<i>Твой аккаунт пока не привязан к Telegram. Перейди в личный кабинет на сайте и нажми кнопку «Привязать Telegram».</i>"
            )
            
        await send_or_update_menu(telegram_id, welcome_text, get_main_keyboard())

@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery):
    await callback.answer("Просто напиши свой вопрос прямо в этот чат, и наша поддержка тебе ответит!", show_alert=True)

import re

@dp.message()
async def handle_all_messages(message: types.Message) -> None:
    if message.text and message.text.startswith('/'):
        return

    admin_id_str = os.environ.get("ADMIN_TG_ID")
    if not admin_id_str:
        return
        
    admin_id = int(admin_id_str)
    
    if message.from_user.id == admin_id and message.reply_to_message:
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        match = re.search(r"ID:\s*(\d+)", replied_text)
        if match:
            user_id = int(match.group(1))
            try:
                if message.text:
                    await bot.send_message(user_id, f"👨‍💻 <b>Служба поддержки:</b>\n\n{message.text}", parse_mode="HTML")
                else:
                    original_caption = message.caption or ""
                    new_caption = f"👨‍💻 <b>Служба поддержки:</b>\n\n{original_caption}"
                    if len(new_caption) > 1024:
                        new_caption = new_caption[:1020] + "..."
                    await message.copy_to(user_id, caption=new_caption, parse_mode="HTML")
            except Exception as e:
                await message.answer(f"❌ Не удалось отправить ответ пользователю: {e}")
            return
            
    if message.from_user.id != admin_id:
        username = f"@{message.from_user.username}" if message.from_user.username else "Без юзернейма"
        user_info = f"От: {message.from_user.full_name} ({username})\nID: {message.from_user.id}"
        
        try:
            if message.text:
                await bot.send_message(admin_id, f"💬 <b>Новое обращение:</b>\n\n{user_info}\n\n{message.text}", parse_mode="HTML")
            else:
                original_caption = message.caption or ""
                new_caption = f"💬 <b>Новое обращение:</b>\n{user_info}\n\n{original_caption}"
                if len(new_caption) > 1024:
                    new_caption = new_caption[:1020] + "..."
                await message.copy_to(admin_id, caption=new_caption, parse_mode="HTML")
            
            # Send confirmation and delete user's message to keep chat clean
            msg = await message.answer("✅ Ваше сообщение передано в техподдержку. Мы скоро ответим!")
            await asyncio.sleep(3)
            try:
                await message.delete()
                await msg.delete()
            except Exception:
                pass
        except Exception as e:
            logging.error(f"Failed to forward message to admin: {e}")

async def notification_worker():
    """Background task to check for expiring subscriptions and send reminders."""
    while True:
        try:
            now = datetime.now()
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, telegram_id, expires_at, notified_3d, notified_1d, notified_10h, notified_1h FROM users WHERE status = 'active' AND expires_at IS NOT NULL AND telegram_id IS NOT NULL AND expires_at != 'Безлимит'")
            users = cursor.fetchall()
            
            for u in users:
                try:
                    exp_dt = datetime.strptime(u["expires_at"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    # Fallback for old format just in case
                    try:
                        exp_dt = datetime.strptime(u["expires_at"], "%Y-%m-%d")
                    except Exception:
                        continue
                        
                time_left = exp_dt - now
                hours_left = time_left.total_seconds() / 3600
                
                # Check 3 days
                if 24 < hours_left <= 72 and not u["notified_3d"]:
                    await bot.send_message(u["telegram_id"], "⚠️ Твоя подписка истекает через 3 дня. Продли её сейчас в личном кабинете, чтобы не остаться без интернета!", reply_markup=get_main_keyboard())
                    cursor.execute("UPDATE users SET notified_3d = 1 WHERE id = ?", (u["id"],))
                    
                # Check 1 day
                elif 10 < hours_left <= 24 and not u["notified_1d"]:
                    await bot.send_message(u["telegram_id"], "⏳ Твоя подписка истекает уже завтра! Успей продлить.", reply_markup=get_main_keyboard())
                    cursor.execute("UPDATE users SET notified_1d = 1 WHERE id = ?", (u["id"],))
                    
                # Check 10 hours
                elif 1 < hours_left <= 10 and not u["notified_10h"]:
                    await bot.send_message(u["telegram_id"], "❗️ Твоя подписка истекает менее чем через 10 часов! Продли доступ.", reply_markup=get_main_keyboard())
                    cursor.execute("UPDATE users SET notified_10h = 1 WHERE id = ?", (u["id"],))
                    
                # Check 1 hour
                elif 0 < hours_left <= 1 and not u["notified_1h"]:
                    await bot.send_message(u["telegram_id"], "🔴 ВНИМАНИЕ: Подписка истекает менее чем через час! Доступ к VPN будет приостановлен.", reply_markup=get_main_keyboard())
                    cursor.execute("UPDATE users SET notified_1h = 1 WHERE id = ?", (u["id"],))

            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error in notification worker: {e}")
            
        await asyncio.sleep(300) # Check every 5 minutes

async def main() -> None:
    # Start background task
    asyncio.create_task(notification_worker())
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
