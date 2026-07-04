# 🤖 Telegram Users Bot

Telegram-бот для сбора **@usernames** всех участников группы по команде `/get_users`.

> ⚠️ **Важно:** Этот репозиторий содержит **две реализации** в одном проекте,
> так как `aiogram` не работает на Cloudflare Workers. См. таблицу ниже.

| Реализация | Файл | Стек | Платформа деплоя |
|------------|------|------|------------------|
| **A. Python** (основная) | `src/bot.py` | Python 3.11+ / aiogram 3.x | Railway, Render, Fly.io, VPS |
| **B. Cloudflare Workers** (альтернатива) | `src/worker.js` | JavaScript / grammY | Cloudflare Workers |

---

## ✨ Возможности

- ✅ Сбор @usernames всех участников группы
- ✅ Корректная обработка участников без username
- ✅ Исключение ботов из списка
- ✅ Автоматическое разбиение длинных списков на части (≤ 4096 символов)
- ✅ Подробная обработка ошибок (нет прав админа, ошибки API, и т.д.)
- ✅ Полностью асинхронный код (`async/await`)
- ✅ Безопасное хранение секретов через `.env` / Cloudflare Secrets

---

## 🚀 Локальный запуск (Python-вариант)

### 1. Требования
- Python 3.10+
- Git
- Токен бота от [@BotFather](https://t.me/BotFather)

### 2. Клонирование и установка

```bash
git clone https://github.com/<your-username>/telegram-users-bot.git
cd telegram-users-bot

# Создайте виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows

# Установите зависимости
pip install --upgrade pip
pip install -r requirements.txt
