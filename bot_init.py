# bot_init.py
from aiogram import Bot
import os

# Глобальная переменная для бота
bot_instance = None

def init_bot():
    global bot_instance
    token = os.getenv('BOT_TOKEN')
    if token:
        bot_instance = Bot(token=token)
        print("✅ Бот инициализирован")
    else:
        print("❌ Токен бота не найден")

def get_bot():
    return bot_instance