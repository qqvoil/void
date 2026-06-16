import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart

# Configure logging
logging.basicConfig(level=logging.INFO)

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from dotenv import load_dotenv

load_dotenv()

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

def link_account(token: str, telegram_id: int) -> bool:
    """Find user by token and link telegram_id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE tg_link_token = ?", (token,))
    user = cursor.fetchone()
    
    if user:
        # Update user's telegram_id and clear the token
        try:
            cursor.execute(
                "UPDATE users SET telegram_id = ?, tg_link_token = NULL WHERE id = ?",
                (telegram_id, user[0])
            )
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            # This telegram_id is already linked to another account
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

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import WebAppInfo

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📱 Личный кабинет", web_app=WebAppInfo(url="https://jointhevoid.ru/dashboard")))
    builder.row(InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="support"))
    return builder.as_markup()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    args = message.text.split(maxsplit=1)
    payload = args[1] if len(args) > 1 else None
    telegram_id = message.from_user.id

    if payload:
        success = link_account(payload, telegram_id)
        if success:
            await message.answer(
                f"✅ <b>Успешно!</b> Твой Telegram-аккаунт привязан к профилю Void VPN.\n\n"
                f"Теперь ты будешь получать здесь важные уведомления и можешь общаться с поддержкой.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                "❌ Ссылка для привязки недействительна или этот Telegram уже привязан к другому аккаунту.",
                reply_markup=get_main_keyboard()
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
            
        await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "support")
async def support_callback(callback: types.CallbackQuery):
    await callback.answer("Просто напиши свой вопрос прямо в этот чат, и наша поддержка тебе ответит!", show_alert=True)

import re
from aiogram import F

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_text_messages(message: types.Message) -> None:
    admin_id_str = os.environ.get("ADMIN_TG_ID")
    if not admin_id_str:
        return
        
    admin_id = int(admin_id_str)
    
    if message.from_user.id == admin_id and message.reply_to_message:
        replied_text = message.reply_to_message.text or ""
        match = re.search(r"ID:\s*(\d+)", replied_text)
        if match:
            user_id = int(match.group(1))
            try:
                await bot.send_message(user_id, f"👨‍💻 <b>Служба поддержки:</b>\n\n{message.text}", parse_mode="HTML")
            except Exception as e:
                await message.answer(f"❌ Не удалось отправить ответ пользователю: {e}")
            return
            
    if message.from_user.id != admin_id:
        username = f"@{message.from_user.username}" if message.from_user.username else "Без юзернейма"
        forward_text = f"💬 <b>Новое обращение:</b>\n\nОт: {message.from_user.full_name} ({username})\nID: {message.from_user.id}\n\n{message.text}"
        
        try:
            await bot.send_message(admin_id, forward_text, parse_mode="HTML")
            await message.answer("✅ Ваше сообщение передано в техподдержку. Мы скоро ответим!")
        except Exception as e:
            logging.error(f"Failed to forward message to admin: {e}")

async def main() -> None:
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
