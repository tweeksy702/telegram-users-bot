"""
Telegram-бот для сбора @usernames активных участников группы.
Версия 4.0: с ограничением доступа по списку разрешённых юзернеймов.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Set

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
)
from aiogram.filters import Command
from aiogram.types import ChatMember, Message, User
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

BOT_TOKEN: str | None = os.getenv("BOT_TOKEN")
MAX_MESSAGE_LENGTH: int = 4096
REQUEST_DELAY: float = 0.05

# ============================================================
# Список разрешённых пользователей (загружается из .env)
# ============================================================
def load_allowed_usernames() -> Set[str]:
    """
    Загружает список разрешённых @usernames из .env.
    Формат в .env: ALLOWED_USERNAMES=@user1,@user2,@user3
    """
    raw = os.getenv("ALLOWED_USERNAMES", "").strip()
    if not raw:
        logger.warning(
            "⚠️ ALLOWED_USERNAMES не задан — бот не будет отвечать никому!"
        )
        return set()

    usernames = {
        u.strip().lstrip("@").lower()
        for u in raw.split(",")
        if u.strip()
    }
    logger.info(
        "🔐 Загружено %s разрешённых юзернеймов: %s",
        len(usernames),
        ", ".join(f"@{u}" for u in usernames),
    )
    return usernames


ALLOWED_USERNAMES: Set[str] = load_allowed_usernames()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
MEMBERS_FILE = DATA_DIR / "known_members.json"

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не задан.")


class MembersStorage:
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._data: Dict[str, Dict[str, bool]] = {}
        self._load()

    def _load(self) -> None:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                total = sum(len(v) for v in self._data.values())
                logger.info("📂 Загружено %s участников", total)
            except Exception as exc:
                logger.warning("⚠️ Не удалось загрузить: %s", exc)
                self._data = {}
        else:
            logger.info("📂 Хранилище пустое")

    def _save(self) -> None:
        try:
            tmp = self.filepath.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            tmp.replace(self.filepath)
        except OSError as exc:
            logger.error("❌ Ошибка сохранения: %s", exc)

    def add(self, chat_id: int, user_id: int) -> bool:
        chat_key = str(chat_id)
        user_key = str(user_id)
        if chat_key not in self._data:
            self._data[chat_key] = {}
        if user_key not in self._data[chat_key]:
            self._data[chat_key][user_key] = True
            self._save()
            return True
        return False

    def get_user_ids(self, chat_id: int) -> List[int]:
        chat_key = str(chat_id)
        if chat_key not in self._data:
            return []
        return [int(uid) for uid in self._data[chat_key].keys()]


storage = MembersStorage(MEMBERS_FILE)

bot: Bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp: Dispatcher = Dispatcher()
router: Router = Router()
dp.include_router(router)


async def get_user_profile(chat_id: int, user_id: int) -> User | None:
    try:
        chat_member: ChatMember = await bot.get_chat_member(
            chat_id=chat_id,
            user_id=user_id,
        )
        return chat_member.user
    except (TelegramBadRequest, TelegramAPIError):
        return None


def chunk_message(lines: List[str], header: str) -> List[str]:
    chunks: List[str] = []
    current: str = header
    for line in lines:
        candidate: str = current + line + "\n"
        if len(candidate) > MAX_MESSAGE_LENGTH - 50:
            chunks.append(current.rstrip())
            current = line + "\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def is_allowed(message: Message) -> bool:
    """
    Проверяет, разрешён ли пользователь.
    Возвращает True, если список пуст (разрешены все)
    или если username пользователя в списке разрешённых.
    """
    # Если список пуст — разрешаем всем (для обратной совместимости)
    if not ALLOWED_USERNAMES:
        return True

    if not message.from_user or not message.from_user.username:
        return False

    return message.from_user.username.lower() in ALLOWED_USERNAMES


def remember_user(message: Message) -> None:
    """Запоминает user_id отправителя в любой группе."""
    if message.from_user and message.chat:
        if message.chat.type in ("group", "supergroup"):
            added = storage.add(message.chat.id, message.from_user.id)
            if added:
                logger.info(
                    "➕ Запомнил: user_id=%s (@%s) в чате %s",
                    message.from_user.id,
                    message.from_user.username or "no_username",
                    message.chat.id,
                )


# ============================================================
# Команды
# ============================================================

@router.message(Command("get_users"))
async def cmd_get_users(message: Message) -> None:
    """Главная команда: собирает @usernames всех известных."""
    if message.chat.type not in ("group", "supergroup"):
        return

    if not is_allowed(message):
        logger.info(
            "🚫 /get_users отклонено для user_id=%s (@%s)",
            message.from_user.id if message.from_user else None,
            message.from_user.username if message.from_user else None,
        )
        return  # Тихо игнорируем, не отвечаем

    remember_user(message)
    chat_id = message.chat.id
    user_ids = storage.get_user_ids(chat_id)

    if not user_ids:
        await message.reply(
            "❌ <b>Нет данных.</b>\n"
            "Попросите участников написать что-нибудь в чат."
        )
        return

    status = await message.reply("🔄 Собираю @usernames...")

    usernames: List[str] = []
    no_username = 0
    bots = 0
    not_found = 0

    for uid in user_ids:
        user = await get_user_profile(chat_id, uid)
        await asyncio.sleep(REQUEST_DELAY)
        if user is None:
            not_found += 1
            continue
        if user.is_bot:
            bots += 1
            continue
        if user.username:
            usernames.append(f"@{user.username}")
        else:
            no_username += 1

    if not usernames:
        await status.edit_text(
            f"❌ <b>Нет @usernames.</b>\n"
            f"Активных: {len(user_ids)} | Без username: {no_username} | "
            f"Ботов: {bots} | Не найдено: {not_found}"
        )
        return

    header = (
        f"👥 <b>Список активных участников</b>\n"
        f"📊 С username: <b>{len(usernames)}</b> из {len(user_ids)}\n\n"
    )
    chunks = chunk_message(usernames, header)
    await status.edit_text(chunks[0])
    for c in chunks[1:]:
        await message.answer(c)


@router.message(Command("collect_admins"))
async def cmd_collect_admins(message: Message) -> None:
    """Собирает user_id всех админов чата через Telegram API."""
    if message.chat.type not in ("group", "supergroup"):
        return

    if not is_allowed(message):
        logger.info(
            "🚫 /collect_admins отклонено для user_id=%s",
            message.from_user.id if message.from_user else None,
        )
        return

    remember_user(message)
    chat_id = message.chat.id
    status = await message.reply("🔄 Собираю админов чата...")

    try:
        admins = await bot.get_chat_administrators(chat_id)
    except TelegramAPIError as exc:
        await status.edit_text(f"❌ Ошибка: {exc}")
        return

    new_count = 0
    for admin in admins:
        if storage.add(chat_id, admin.user.id):
            new_count += 1

    admin_lines = []
    for a in admins:
        uname = f"@{a.user.username}" if a.user.username else f"<i>{a.user.full_name}</i>"
        admin_lines.append(f"• {uname} — {a.status}")

    await status.edit_text(
        f"✅ <b>Готово!</b>\n\n"
        f"Админов в чате: <b>{len(admins)}</b>\n"
        f"Новых добавлено: <b>{new_count}</b>\n\n"
        f"<b>Список:</b>\n" + "\n".join(admin_lines) + "\n\n"
        f"Теперь /get_users"
    )


@router.message(Command("add_user"))
async def cmd_add_user(message: Message) -> None:
    """Ручное добавление user_id."""
    if message.chat.type not in ("group", "supergroup"):
        return

    if not is_allowed(message):
        logger.info(
            "🚫 /add_user отклонено для user_id=%s",
            message.from_user.id if message.from_user else None,
        )
        return

    remember_user(message)
    args = message.text.split()

    if len(args) < 2:
        await message.reply(
            "⚠️ <b>Использование:</b>\n"
            "<code>/add_user 123456789 987654321</code>\n\n"
            "Узнать свой ID: @userinfobot"
        )
        return

    chat_id = message.chat.id
    added = 0
    errors = 0

    for arg in args[1:]:
        try:
            uid = int(arg)
            user = await get_user_profile(chat_id, uid)
            if user:
                if storage.add(chat_id, uid):
                    added += 1
            else:
                errors += 1
        except ValueError:
            errors += 1

    await message.reply(
        f"✅ <b>Готово!</b>\n"
        f"Добавлено: {added}\n"
        f"Ошибок: {errors}\n\n"
        f"Введите /get_users"
    )


@router.message(Command("debug"))
async def cmd_debug(message: Message) -> None:
    """Показывает, что бот знает о чате."""
    if message.chat.type not in ("group", "supergroup"):
        return

    if not is_allowed(message):
        logger.info(
            "🚫 /debug отклонено для user_id=%s",
            message.from_user.id if message.from_user else None,
        )
        return

    remember_user(message)
    chat_id = message.chat.id
    user_ids = storage.get_user_ids(chat_id)

    if not user_ids:
        await message.reply("❌ Хранилище пустое.")
        return

    lines = [
        f"🔍 <b>Отладка: {message.chat.title}</b>",
        f"Chat ID: <code>{chat_id}</code>",
        f"Известно: <b>{len(user_ids)}</b>\n",
    ]

    for uid in user_ids:
        user = await get_user_profile(chat_id, uid)
        await asyncio.sleep(REQUEST_DELAY)
        if user:
            uname = f"@{user.username}" if user.username else "<i>нет @username</i>"
            lines.append(f"• <code>{uid}</code> — {user.full_name} → {uname}")
        else:
            lines.append(f"• <code>{uid}</code> — ❌ не в чате")

    await message.reply("\n".join(lines))


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    remember_user(message)
    await message.reply(
        "👋 <b>Привет!</b>\n\n"
        "Я бот для сбора @usernames активных участников.\n\n"
        "<b>Команды:</b>\n"
        "• /get_users — список @usernames\n"
        "• /collect_admins — собрать админов\n"
        "• /add_user ID — добавить по user_id\n"
        "• /debug — диагностика\n"
        "• /help — справка"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    remember_user(message)
    await message.reply(
        "📖 <b>Справка</b>\n\n"
        "Telegram Bot API (с декабря 2024) не даёт ботам "
        "полный список участников.\n\n"
        "<b>Как добавить участников:</b>\n"
        "1. Попросите всех написать сообщение в чат\n"
        "2. /collect_admins — добавит админов\n"
        "3. /add_user ID — добавить по user_id\n\n"
        "Узнать свой ID: @userinfobot"
    )


async def main() -> None:
    logger.info("=" * 50)
    logger.info("🚀 Запуск Telegram-бота (v4.0)...")
    logger.info("=" * 50)

    if ALLOWED_USERNAMES:
        logger.info(
            "🔐 Доступ только для: %s",
            ", ".join(f"@{u}" for u in ALLOWED_USERNAMES),
        )
    else:
        logger.warning("⚠️ ALLOWED_USERNAMES пуст — бот отвечает всем!")

    try:
        me = await bot.get_me()
        logger.info("Бот: @%s (%s)", me.username, me.full_name)

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            skip_updates=False,
        )
    finally:
        await bot.session.close()
        logger.info("🛑 Остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Выход...")

