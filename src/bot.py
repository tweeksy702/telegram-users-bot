"""
Telegram-бот для сбора @usernames участников группы.
Команда: /get_users
Платформа: Render.com (Background Worker)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import List

from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    AiogramError,
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
)
from aiogram.filters import Command
from aiogram.types import ChatMember, Message
from dotenv import load_dotenv

# Загрузка .env (для локального запуска)
load_dotenv()

# Логирование
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN: str | None = os.getenv("BOT_TOKEN")
MAX_MESSAGE_LENGTH: int = 4096
TELEGRAM_API_MEMBER_LIMIT: int = 10_000
PAGE_SIZE: int = 200

# Проверка токена
if not BOT_TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN не задан.\n"
        "Локально: создайте .env (см. .env.example).\n"
        "На Render: задайте переменную BOT_TOKEN в Environment Variables."
    )

# Инициализация
bot: Bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp: Dispatcher = Dispatcher()
router: Router = Router()
dp.include_router(router)


async def fetch_all_members(chat_id: int) -> List[ChatMember]:
    """Получает всех участников чата с пагинацией."""
    members: List[ChatMember] = []
    offset: int = 0

    while True:
        try:
            batch: List[ChatMember] = await bot.get_chat_members(
                chat_id=chat_id,
                offset=offset,
                limit=PAGE_SIZE,
            )
        except TelegramAPIError as exc:
            logger.error("Ошибка при получении участников (offset=%s): %s", offset, exc)
            raise

        if not batch:
            break

        members.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        offset += PAGE_SIZE
        if offset >= TELEGRAM_API_MEMBER_LIMIT:
            logger.warning(
                "⚠️ Достигнут лимит Telegram API в %s участников для чата %s",
                TELEGRAM_API_MEMBER_LIMIT,
                chat_id,
            )
            break

    return members


def chunk_message(lines: List[str], header: str) -> List[str]:
    """Разбивает список строк на части, не превышающие лимит Telegram."""
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


@router.message(Command("get_users"))
async def cmd_get_users(message: Message) -> None:
    """Обработчик команды /get_users."""
    if message.chat.type not in ("group", "supergroup"):
        await message.reply(
            "⚠️ <b>Эта команда работает только в группах.</b>\n\n"
            "Добавьте бота в группу и предоставьте ему права администратора."
        )
        return

    status_msg: Message = await message.reply("🔄 Собираю список участников...")

    try:
        members: List[ChatMember] = await fetch_all_members(message.chat.id)
        logger.info(
            "Получено %s участников из чата %s (%s)",
            len(members),
            message.chat.id,
            message.chat.title,
        )

        usernames: List[str] = []
        no_username_count: int = 0
        bots_count: int = 0

        for member in members:
            user = member.user
            if user.is_bot:
                bots_count += 1
                continue
            if user.username:
                usernames.append(f"@{user.username}")
            else:
                no_username_count += 1

        if not usernames:
            await status_msg.edit_text(
                "❌ <b>Участников с публичным @username не найдено.</b>\n\n"
                f"📊 Всего участников: <b>{len(members)}</b>\n"
                f"👤 Без юзернейма: <b>{no_username_count}</b>\n"
                f"🤖 Ботов: <b>{bots_count}</b>"
            )
            return

        header: str = (
            "👥 <b>Список участников с @username</b>\n"
            f"📊 Всего: <b>{len(members)}</b> | "
            f"С юзернеймом: <b>{len(usernames)}</b> | "
            f"Без: <b>{no_username_count}</b> | "
            f"Ботов: <b>{bots_count}</b>\n\n"
        )

        chunks: List[str] = chunk_message(usernames, header)
        logger.info(
            "Отправка %s юзернеймов в %s сообщении(ях)",
            len(usernames),
            len(chunks),
        )

        await status_msg.edit_text(chunks[0])
        for chunk in chunks[1:]:
            await message.answer(chunk)

    except TelegramForbiddenError:
        await status_msg.edit_text(
            "❌ <b>Ошибка доступа.</b>\n\n"
            "Бот должен быть <b>администратором</b> группы, "
            "чтобы иметь доступ к списку участников."
        )
        logger.warning("Запрещён доступ к участникам чата %s", message.chat.id)

    except TelegramBadRequest as exc:
        await status_msg.edit_text(f"❌ <b>Ошибка запроса Telegram:</b>\n{exc}")
        logger.error("TelegramBadRequest в чате %s: %s", message.chat.id, exc)

    except TelegramNetworkError as exc:
        await status_msg.edit_text(
            "❌ <b>Сетевая ошибка Telegram.</b>\n"
            "Попробуйте повторить запрос позже."
        )
        logger.error("TelegramNetworkError: %s", exc)

    except TelegramAPIError as exc:
        await status_msg.edit_text(f"❌ <b>Ошибка Telegram API:</b>\n{exc}")
        logger.error("TelegramAPIError: %s", exc)

    except AiogramError as exc:
        await status_msg.edit_text(
            "❌ <b>Внутренняя ошибка бота.</b>\nПопробуйте позже."
        )
        logger.exception("AiogramError: %s", exc)

    except Exception as exc:
        await status_msg.edit_text(
            "❌ <b>Произошла непредвиденная ошибка.</b>\n"
            "Попробуйте позже или обратитесь к администратору бота."
        )
        logger.exception("Unexpected error in /get_users: %s", exc)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start."""
    await message.reply(
        "👋 <b>Привет!</b>\n\n"
        "Я бот для сбора <b>@usernames</b> участников группы.\n\n"
        "<b>Доступные команды:</b>\n"
        "• /get_users — получить список @usernames\n"
        "• /help — подробная справка\n\n"
        "⚠️ Бот должен быть добавлен в группу "
        "с правами <b>администратора</b>."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработчик команды /help."""
    await message.reply(
        "📖 <b>Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "• <code>/get_users</code> — собрать @usernames всех участников\n"
        "• <code>/start</code> — приветствие\n"
        "• <code>/help</code> — эта справка\n\n"
        "<b>Требования:</b>\n"
        "• Бот добавлен в группу\n"
        "• Бот имеет права администратора\n"
        "• У участника есть публичный <code>@username</code>\n\n"
        "<b>Ограничения:</b>\n"
        "• Telegram API отдаёт максимум 10 000 участников\n"
        "• Боты исключаются из списка\n"
        "• Пользователи без username не попадают в список\n"
        "• Длинные списки автоматически разбиваются на части"
    )


async def main() -> None:
    """Главная функция запуска бота."""
    logger.info("=" * 50)
    logger.info("🚀 Запуск Telegram-бота...")
    logger.info("=" * 50)

    try:
        me = await bot.get_me()
        logger.info("Бот авторизован как: @%s (%s)", me.username, me.full_name)

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            skip_updates=True,
        )
    finally:
        await bot.session.close()
        logger.info("🛑 Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал завершения. Выход...")
