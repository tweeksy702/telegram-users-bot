# 🤖 Telegram Users Bot

Telegram-бот для сбора **@usernames** всех участников группы по команде `/get_users`.

## ✨ Возможности

- ✅ Сбор @usernames всех участников группы
- ✅ Корректная обработка участников без username
- ✅ Исключение ботов из списка
- ✅ Автоматическое разбиение длинных списков на части (≤ 4096 символов)
- ✅ Подробная обработка ошибок (нет прав админа, ошибки API, и т.д.)
- ✅ Полностью асинхронный код (`async/await`)

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
