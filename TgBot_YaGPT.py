# =========================================================
# 1. Установка библиотек
# =========================================================
!pip install -q pyTelegramBotAPI requests

import telebot
import requests
import json
import time
from google.colab import userdata

# =========================================================
# 2. Загрузка секретов из Colab Secrets
# =========================================================
TELEGRAM_BOT_TOKEN = userdata.get('TELEGRAM_BOT_TOKEN')
YANDEX_GPT_API_KEY = userdata.get('YANDEX_GPT_API_KEY')
YANDEX_FOLDER_ID   = userdata.get('YANDEX_FOLDER_ID')

# =========================================================
# 3. Системный промт (из задания)
# =========================================================
SYSTEM_PROMPT = """Ты — «Гастро-Стихотворец», виртуальный шеф-повар и эксперт исключительно в области кулинарии и приготовления пищи. Твоя база знаний ограничена только рецептами, техниками готовки, сочетанием продуктов и историей блюд.

Твои строгие правила:
1. НИКОГДА не обсуждай темы, связанные с медициной, лечением, лекарствами, здоровьем (кроме базовых кулинарных советов, например, "как выбрать свежую рыбу"), и политикой. Если пользователь спрашивает об этом, вежливо откажись и верни разговор к еде.
2. Отвечай ТОЛЬКО в форме стихотворения (рифма, ритм). Старайся подражать стилю Корнея Чуковского или Самуила Маршака — сказочный, добрый, немного ироничный тон.
3. Не выходи за рамки кулинарии. Если спрашивают о погоде, космосе или психологии — отвечай, что это не твоя стихия, и предлагай обсудить, что приготовить.
4. Длина ответа: не более 8-10 строк (двустиший или четверостиший), чтобы не утомлять пользователя.
5. Если пользователь пишет "начать заново", "сброс", "очистить" или "новый диалог", поздоровайся, как будто вы видитесь впервые, и спроси, что он хочет приготовить сегодня.
6. Не используй markdown-разметку, отвечай чистым текстом.

Твоя цель — вдохновлять пользователя на кулинарные подвиги через рифму."""

# =========================================================
# 4. Инициализация бота и хранилища истории
# =========================================================
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Словарь: chat_id -> список сообщений (история диалога)
user_history = {}

# Максимальная длина истории (чтобы не превысить лимит токенов YandexGPT)
MAX_HISTORY_TURNS = 10

# =========================================================
# 5. Функция запроса к YandexGPT API
# =========================================================
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

def ask_yandex_gpt(chat_id: int, user_message: str) -> str:
    """Отправляет запрос в YandexGPT с учётом истории диалога."""
    
    # Формируем массив сообщений: system + история + текущее сообщение
    messages = [{"role": "system", "text": SYSTEM_PROMPT}]
    
    # Добавляем историю (не более последних N реплик)
    history = user_history.get(chat_id, [])
    messages.extend(history[-MAX_HISTORY_TURNS * 2:])
    
    # Добавляем текущее сообщение пользователя
    messages.append({"role": "user", "text": user_message})
    
    # modelUri для YandexGPT
    model_uri = f"gpt://{YANDEX_FOLDER_ID}/yandexgpt/latest"
    
    payload = {
        "modelUri": model_uri,
        "completionOptions": {
            "stream": False,
            "temperature": 0.7,   # баланс между креативом стиха и соблюдением правил
            "maxTokens": "1500"   # ограничиваем длину ответа
        },
        "messages": messages
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Api-Key {YANDEX_GPT_API_KEY}",
        "x-folder-id": YANDEX_FOLDER_ID
    }
    
    try:
        response = requests.post(YANDEX_GPT_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        # Извлекаем текст ответа
        answer = data["result"]["alternatives"][0]["message"]["text"]
        
        # Сохраняем в историю (user + assistant)
        if chat_id not in user_history:
            user_history[chat_id] = []
        user_history[chat_id].append({"role": "user", "text": user_message})
        user_history[chat_id].append({"role": "assistant", "text": answer})
        
        return answer
    
    except requests.exceptions.HTTPError as e:
        return f"⚠️ Ошибка API YandexGPT: {e}\n{response.text if 'response' in locals() else ''}"
    except Exception as e:
        return f"⚠️ Произошла ошибка: {e}"

# =========================================================
# 6. Обработчики команд и сообщений
# =========================================================

@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    text = (
        "🍳 Привет! Я — «Гастро-Стихотворец»!\n\n"
        "Я — шеф-повар, который отвечает ТОЛЬКО стихами\n"
        "и ТОЛЬКО про кулинарию (рецепты, техники, продукты).\n\n"
        "📝 Команды:\n"
        "/reset — очистить историю и начать заново\n"
        "/help — показать эту справку\n\n"
        "Спроси меня, что приготовить! 🥘"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['reset'])
def cmd_reset(message):
    chat_id = message.chat.id
    if chat_id in user_history:
        del user_history[chat_id]
    bot.send_message(chat_id, "🧹 История очищена! Давай начнём новый кулинарный разговор. Что будем готовить?")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    user_text = message.text.strip()
    
    # Локальная обработка сброса (на случай, если команда без слэша)
    reset_triggers = ["начать заново", "сброс", "очистить", "новый диалог", "забудь всё"]
    if user_text.lower() in reset_triggers:
        if chat_id in user_history:
            del user_history[chat_id]
        bot.send_message(chat_id, "🧹 Память очищена! Привет, повар! Что будем готовить сегодня?")
        return
    
    # Показываем "бот печатает..."
    bot.send_chat_action(chat_id, 'typing')
    
    # Запрос к YandexGPT
    answer = ask_yandex_gpt(chat_id, user_text)
    
    # Telegram ограничивает сообщение 4096 символами
    if len(answer) > 4000:
        answer = answer[:4000] + "\n\n…(обрезано)"
    
    bot.send_message(chat_id, answer)

# =========================================================
# 7. Запуск бота
# =========================================================
if __name__ == "__main__":
    print("✅ Бот запущен! Открой Telegram и напиши боту /start")
    print("⏹ Чтобы остановить — нажми кнопку Stop в Colab")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"Ошибка polling: {e}")
        time.sleep(3)
