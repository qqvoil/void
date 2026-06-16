import asyncio
import logging
import os
import sqlite3

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN provided in environment variables")

bot = Bot(token=BOT_TOKEN)
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

@dp.message(CommandStart())
async def command_start_handler(message: types.Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    # Extract payload if any (e.g. /start token123 -> token123)
    args = message.text.split(maxsplit=1)
    payload = args[1] if len(args) > 1 else None

    telegram_id = message.from_user.id

    if payload:
        success = link_account(payload, telegram_id)
        if success:
            await message.answer(
                f"✅ Успешно! Твой Telegram-аккаунт привязан к профилю на сайте.\n"
                f"Теперь ты будешь получать здесь уведомления о подписке и свежие новости о Void VPN."
            )
        else:
            await message.answer(
                "❌ Ссылка для привязки недействительна или этот Telegram уже привязан к другому аккаунту."
            )
    else:
        user = get_user_by_tg(telegram_id)
        if user:
            name, status, expires = user
            text = f"Привет, {name}! Твой аккаунт привязан.\nСтатус: {status}"
            if expires:
                text += f"\nИстекает: {expires}"
            await message.answer(text)
        else:
            await message.answer(
                "Привет! Добро пожаловать в Void VPN.\n"
                "Твой аккаунт пока не привязан к Telegram. Перейди в личный кабинет на сайте jointhevoid.ru и нажми кнопку «Привязать Telegram»."
            )

async def main() -> None:
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
