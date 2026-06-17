import asyncio
import logging
import os
import sqlite3
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
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
    cursor.execute("SELECT id, full_name, status, expires_at FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        # Return as dict for easier access
        return {"id": user[0], "full_name": user[1], "status": user[2], "expires_at": user[3]}
    return None

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Личный кабинет", web_app=WebAppInfo(url="https://jointhevoid.ru/dashboard?v=2")))
    builder.row(InlineKeyboardButton(text="Приглашение", callback_data="referral"))
    builder.row(InlineKeyboardButton(text="Поддержка", callback_data="support"))
    return builder.as_markup()

async def send_or_update_menu(chat_id: int, text: str, markup: InlineKeyboardMarkup, is_welcome: bool = False):
    """Deletes previous menu if it exists, and sends a new one."""
    if chat_id in user_menus:
        try:
            await bot.delete_message(chat_id, user_menus[chat_id])
        except Exception:
            pass # Message might be already deleted by user
            
    if is_welcome:
        img_path = os.path.join(os.path.dirname(__file__), "static", "img", "logo_square.jpg")
        try:
            msg = await bot.send_photo(chat_id, photo=FSInputFile(img_path), caption=text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            msg = await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    else:
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
                f"Ваш Telegram-аккаунт успешно синхронизирован с профилем Void VPN.\n\n"
                f"Теперь вы будете получать здесь все уведомления и сможете напрямую обращаться в службу поддержки.",
                get_main_keyboard(),
                is_welcome=True
            )
        else:
            await send_or_update_menu(
                telegram_id,
                "К сожалению, ссылка для авторизации устарела или этот Telegram-аккаунт уже используется.",
                get_main_keyboard()
            )
    else:
        user = get_user_by_tg(telegram_id)
        welcome_text = (
            "<b>Void VPN</b>\n\n"
            "Добро пожаловать в панель управления, где вы можете управлять своей подпиской и получать оперативную помощь.\n\n"
        )
        if user:
            name, status, expires = user["full_name"], user["status"], user["expires_at"]
            welcome_text += f"Пользователь: {name}\n"
            welcome_text += f"Статус: {status}\n"
            if expires:
                welcome_text += f"Действует до: {expires}\n"
        else:
            welcome_text += (
                "<i>Ваш профиль пока не синхронизирован. Пожалуйста, привяжите Telegram в личном кабинете на сайте.</i>"
            )
            
        await send_or_update_menu(telegram_id, welcome_text, get_main_keyboard(), is_welcome=True)

@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery):
    await callback.answer("Вы можете написать свой вопрос прямо в этот чат, и мы вам поможем.", show_alert=True)

@dp.callback_query(F.data == "referral")
async def referral_callback(callback: types.CallbackQuery):
    telegram_id = callback.from_user.id
    user = get_user_by_tg(telegram_id)
    if not user:
        await callback.answer("Сначала привяжи аккаунт к Telegram!", show_alert=True)
        return
        
    ref_link = f"https://jointhevoid.ru/register?ref={user['id']}"
    msg = (
        "<b>Реферальная программа</b>\n\n"
        "Вы можете поделиться своей персональной ссылкой с друзьями. При их первой оплате вы автоматически получите дополнительные 7 дней подписки за каждые 200 ₽ их заказа.\n\n"
        "Ваш друг также получит расширенный семидневный пробный период.\n\n"
        f"Ваша ссылка:\n`{ref_link}`"
    )
    
    # Check if this menu is already displaying referral text
    try:
        await bot.edit_message_text(msg, chat_id=callback.message.chat.id, message_id=callback.message.message_id, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception:
        # Message hasn't changed
        pass
    await callback.answer()

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
                    await bot.send_message(user_id, f"<b>Служба поддержки:</b>\n\n{message.text}", parse_mode="HTML")
                else:
                    original_caption = message.caption or ""
                    new_caption = f"<b>Служба поддержки:</b>\n\n{original_caption}"
                    if len(new_caption) > 1024:
                        new_caption = new_caption[:1020] + "..."
                    await message.copy_to(user_id, caption=new_caption, parse_mode="HTML")
            except Exception as e:
                await message.answer(f"Ошибка отправки: {e}")
            return
            
    if message.from_user.id != admin_id:
        username = f"@{message.from_user.username}" if message.from_user.username else "Без юзернейма"
        user_info = f"От: {message.from_user.full_name} ({username})\nID: {message.from_user.id}"
        
        try:
            if message.text:
                await bot.send_message(admin_id, f"<b>Обращение:</b>\n\n{user_info}\n\n{message.text}", parse_mode="HTML")
            else:
                original_caption = message.caption or ""
                new_caption = f"<b>Обращение:</b>\n{user_info}\n\n{original_caption}"
                if len(new_caption) > 1024:
                    new_caption = new_caption[:1020] + "..."
                await message.copy_to(admin_id, caption=new_caption, parse_mode="HTML")
            
            # Send confirmation and delete user's message to keep chat clean
            msg = await message.answer("Ваше обращение передано в службу поддержки. Мы ответим вам в ближайшее время.")
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
                    try:
                        await bot.send_message(u["telegram_id"], "Обращаем ваше внимание, что срок действия вашей подписки истекает через 3 дня. Вы можете продлить ее в личном кабинете.", reply_markup=get_main_keyboard())
                    except Exception:
                        pass
                    cursor.execute("UPDATE users SET notified_3d = 1 WHERE id = ?", (u["id"],))
                    
                # Check 1 day
                elif 10 < hours_left <= 24 and not u["notified_1d"]:
                    try:
                        await bot.send_message(u["telegram_id"], "Напоминаем, что ваша подписка истекает уже завтра. Пожалуйста, продлите ее для сохранения доступа.", reply_markup=get_main_keyboard())
                    except Exception:
                        pass
                    cursor.execute("UPDATE users SET notified_1d = 1 WHERE id = ?", (u["id"],))
                    
                # Check 10 hours
                elif 1 < hours_left <= 10 and not u["notified_10h"]:
                    try:
                        await bot.send_message(u["telegram_id"], "Срок действия вашей подписки подходит к концу и истечет менее чем через 10 часов.", reply_markup=get_main_keyboard())
                    except Exception:
                        pass
                    cursor.execute("UPDATE users SET notified_10h = 1 WHERE id = ?", (u["id"],))
                    
                # Check 1 hour
                elif 0 < hours_left <= 1 and not u["notified_1h"]:
                    try:
                        await bot.send_message(u["telegram_id"], "Ваш доступ к VPN будет приостановлен менее чем через час, так как срок действия подписки завершается.", reply_markup=get_main_keyboard())
                    except Exception:
                        pass
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
