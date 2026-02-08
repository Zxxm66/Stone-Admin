# ======== ИМПОРТЫ ========

from aiogram.types import InputMediaPhoto
import aiofiles
import os
import asyncio
import time
import sqlite3
from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import json
import logging
from datetime import datetime, timedelta
import re
from ast import literal_eval
from typing import Optional
import html
from aiogram.exceptions import TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import aiohttp
from aiogram.types import WebAppInfo
# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
from dotenv import load_dotenv
import os
ADMIN_PANEL_URL = "https://adminstone.ru"
load_dotenv('.env')  # Загружаем переменные из .env

bot = Bot(
    token=os.getenv("BOT_TOKEN"),  # Используем токен из переменной окружения
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
# ======== КОНСТАНТЫ ДЛЯ КАТЕГОРИЙ ========
SHOES_CATEGORY_NAME = "Кроссовки"
CLOTHES_CATEGORY_NAME = "Одежда"
accessories_subcategories = ['Сумки','Коллекционное','Кепки и шапки','Очки','Носки','Другое']
ACCESSORIES_CATEGORY_NAME = "Аксессуары"
# ======== НАСТРОЙКИ ========
pending_orders = {}

ADMIN_IDS = literal_eval(os.getenv('ADMIN_ID'))  # ID администратора
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")  # ID группы для уведомлений


class ProductStates(StatesGroup):
    CHOOSING_CLOTHES_SUBCATEGORY = State()
    CHOOSING_SIZE = State()
class ProductStates(StatesGroup):
    CHOOSING_CLOTHES_SUBCATEGORY = State()
    CHOOSING_ACCESSORIES_CATEGORY = State()  # Новое состояние
    CHOOSING_SIZE = State()

# Инициализация бота


storage = MemoryStorage()
dp = Dispatcher(storage=storage)
last_messages = {}  # Для отслеживания последних сообщений
orders_cache = {}  # Временное хранилище заказов


# ======== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ========


# ======== СИСТЕМА ОТСЛЕЖИВАНИЯ ОНЛАЙН-ПОЛЬЗОВАТЕЛЕЙ ========

# Словарь для хранения времени последней активности пользователей
user_activity = {}


def update_user_activity(user_id: int):
    """Обновляет время последней активности пользователя"""
    user_activity[user_id] = time.time()


def get_online_users_count():
    """Получает количество пользователей онлайн (активных за последние 5 минут)"""
    current_time = time.time()
    online_count = 0

    for user_id, last_activity in user_activity.items():
        if current_time - last_activity <= 300:  # 5 минут в секундах
            online_count += 1

    return online_count


def cleanup_inactive_users():
    """Очищает неактивных пользователей (не активны более 1 часа)"""
    current_time = time.time()
    inactive_users = []

    for user_id, last_activity in user_activity.items():
        if current_time - last_activity > 3600:  # 1 час
            inactive_users.append(user_id)

    for user_id in inactive_users:
        del user_activity[user_id]


# Запускаем периодическую очистку неактивных пользователей
async def start_cleanup_task():
    while True:
        cleanup_inactive_users()
        await asyncio.sleep(3600)  # Проверяем каждый час

def generate_shift_report() -> str:
    """Генерирует отчет о закрытии смены"""
    today = datetime.now().strftime("%d.%m.%Y")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Общая статистика
    cursor.execute('''
                   SELECT COUNT(DISTINCT o.id)        AS order_count,
                          SUM(oi.quantity)            AS total_items,
                          SUM(oi.quantity * oi.price) AS total_revenue
                   FROM orders o
                            JOIN order_items oi ON o.id = oi.order_id
                   WHERE DATE (o.confirmed_at) = DATE ('now')
                     AND o.status = 'confirmed'
                   ''')
    stats = cursor.fetchone()
    order_count = stats[0]
    total_items = stats[1]
    total_revenue = stats[2]    # Конвертируем из копеек в рубли

    # 2. Топ продаж
    cursor.execute('''
                   SELECT p.name,
                          s.value AS size,
            SUM(oi.quantity) AS sold_quantity,
            SUM(oi.quantity * oi.price) AS item_revenue
                   FROM order_items oi
                       JOIN products p
                   ON oi.product_id = id
                       LEFT JOIN sizes s ON oi.size_id = s.id
                       JOIN orders o ON oi.order_id = o.id
                   WHERE DATE (o.confirmed_at) = DATE ('now')
                     AND o.status = 'confirmed'
                   GROUP BY oi.product_id, oi.size_id
                   ORDER BY sold_quantity DESC, item_revenue DESC
                       LIMIT 5
                   ''')
    top_products = cursor.fetchall()

    conn.close()

    # 3. Формирование отчета
    report = f"⏰ <b>ОТЧЕТ О ЗАКРЫТИИ СМЕНЫ</b>\n"
    report += f"{today}\n\n"

    report += "📊 <b>Общая статистика:</b>\n"
    report += f"• Заказов: {order_count}\n"
    report += f"• Товаров: {total_items} шт.\n"
    report += f"• Выручка: {total_revenue:,} ₽\n\n"

    report += "🏆 <b>Топ продаж дня:</b>\n"
    for i, (name, size, quantity, revenue) in enumerate(top_products, 1):
        revenue_rub = revenue   # Конвертируем из копеек в рубли
        size_display = f" ({size})" if size else ""
        report += (
            f"{i}. {name}{size_display}\n"
            f"   → Продано: {quantity} шт.\n"
            f"   → Сумма: {revenue_rub:,} ₽\n"
        )

    if not top_products:
        report += "ℹ️ Сегодня не было продаж\n"

    report += "\n🌙 Отличная работа! Желаем хорошего отдыха!"

    return report


async def send_shift_report():
    """Отправляет отчет о закрытии смены"""
    report = generate_shift_report()

    # Отправляем всем администраторам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=report,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка отправки отчета админу {admin_id}: {e}")

    # Отправляем в группу, если указана
    if GROUP_CHAT_ID:
        try:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=report,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка отправки отчета в группу: {e}")


# ======== ИНИЦИАЛИЗАЦИЯ ПЛАНИРОВЩИКА ========
scheduler = AsyncIOScheduler()


async def on_startup():
    """Действия при запуске бота"""
    # Запускаем планировщик для ежедневного отчета в 20:00
    scheduler.add_job(
        send_shift_report,
        CronTrigger(hour=20, minute=00, timezone="Europe/Moscow")
    )
    scheduler.start()






# Для админ-панели добавьте функцию обновления количества:
def update_product_quantity(product_id: int, size_id: int, new_quantity: int) -> bool:
    """
    Обновляет количество товара конкретного размера
    Возвращает True при успехе, False при ошибке
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("""
                       UPDATE products
                       SET quantity = ?
                       WHERE id = ?
                         AND size_id = ?
                       """, (new_quantity, product_id, size_id))
        conn.commit()
        return cursor.rowcount > 0  # Возвращаем True если обновили хотя бы одну строку
    except sqlite3.Error as e:
        logger.error(f"Ошибка обновления количества: {e}")
        return False
    finally:
        conn.close()


def format_price(price):
    """Форматирование цены с разделением тысяч пробелом"""
    if price is None:
        return "0 ₽"
    rubles = price  # переводим копейки в рубли
    return f"{rubles:,} ₽".replace(',', ' ') if rubles else "0 ₽"


# Проверка, является ли пользователь администратором
def is_admin(user_id: int) -> bool:
    # Логируем проверку
    logger.info(f"Проверка прав админа: user_id={user_id}, разрешенные админы: {ADMIN_IDS}")

    # Добавьте свой ID вручную для теста
    if user_id == 1940348187:  # Замените на ваш реальный ID
        return True

    return user_id in ADMIN_IDS


# Определение путей
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'shop.db')

# Создаем папку для БД, если её нет
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# Функция для получения подключения к БД
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ======== ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ========
def init_db():
    """Инициализация базы данных с правильной структурой"""
    if Path(DB_PATH).exists():
        logger.info("База данных уже существует")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Создаем таблицы
    cursor.execute("""
                   CREATE TABLE categories
                   (
                       id        INTEGER PRIMARY KEY AUTOINCREMENT,
                       name      TEXT NOT NULL UNIQUE,
                       parent_id INTEGER REFERENCES categories (id) ON DELETE CASCADE
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE sizes
                   (
                       id          INTEGER PRIMARY KEY AUTOINCREMENT,
                       value       TEXT    NOT NULL,
                       category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE CASCADE
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE products
                   (
                       id          INTEGER PRIMARY KEY AUTOINCREMENT,
                       name        TEXT    NOT NULL,
                       price       INTEGER NOT NULL,
                       sku         TEXT    NOT NULL,
                       category_id INTEGER NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
                       image_url   TEXT    NOT NULL
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE product_variants
                   (
                       product_id INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
                       size_id    INTEGER REFERENCES sizes (id) ON DELETE CASCADE,
                       quantity   INTEGER NOT NULL DEFAULT 0,
                       PRIMARY KEY (product_id, size_id)
                   )
                   """)

    cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                telegram_chat_id BIGINT
            )
        """)

    cursor.execute("""
                   CREATE TABLE carts
                   (
                       id         INTEGER PRIMARY KEY AUTOINCREMENT,
                       user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                   )
                   """)

    cursor.execute("""
                   CREATE TABLE cart_items
                   (
                       id         INTEGER PRIMARY KEY AUTOINCREMENT,
                       cart_id    INTEGER NOT NULL REFERENCES carts (id) ON DELETE CASCADE,
                       product_id INTEGER NOT NULL REFERENCES products (id) ON DELETE CASCADE,
                       size_id    INTEGER REFERENCES sizes (id) ON DELETE CASCADE,
                       quantity   INTEGER NOT NULL DEFAULT 1
                   )
                   """)



    # Добавляем основные категории
    cursor.execute("INSERT INTO categories (name, parent_id) VALUES ('Кроссовки', NULL)")
    cursor.execute("INSERT INTO categories (name, parent_id) VALUES ('Одежда', NULL)")
    # Добавляем основную категорию "Аксессуары"
    cursor.execute("INSERT OR IGNORE INTO categories (name, parent_id) VALUES ('Аксессуары', NULL)")

    # Получаем ID категории "Аксессуары"
    cursor.execute("SELECT id FROM categories WHERE name = 'Аксессуары'")
    accessories_id = cursor.fetchone()[0]

    # Добавляем подкатегории для аксессуаров
    accessories_subcategories = [
        'Кепки и шапки',
        'Сумки',
        'Носки',
        'Очки',
        'Коллекционное',
        'Другое'
    ]

    for name in accessories_subcategories:
        cursor.execute("INSERT OR IGNORE INTO categories (name, parent_id) VALUES (?, ?)", (name, accessories_id))

    # Получаем ID категорий
    cursor.execute("SELECT id FROM categories WHERE name = 'Кроссовки'")
    shoes_id = cursor.fetchone()[0]
    cursor.execute("SELECT id FROM categories WHERE name = 'Одежда'")
    clothes_id = cursor.fetchone()[0]

    # Добавляем подкатегории одежды
    subcategories = [
        ('Футболки', clothes_id),
        ('Штаны и шорты', clothes_id),
        ('Верхняя одежда', clothes_id),
        ('Аксессуары', clothes_id)
    ]

    for name, parent_id in subcategories:
        cursor.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (name, parent_id))

    # Добавляем размеры для кроссовок
    sizes = [str(size).rstrip('0').rstrip('.') for size in [36 + i * 0.5 for i in range(0, 23)]]
    for size in sizes:
        cursor.execute("INSERT INTO sizes (value, category_id) VALUES (?, ?)", (size, shoes_id))

    # Добавляем размеры для одежды
    clothes_sizes = ['XS', 'S', 'M', 'L', 'XL', 'XXL']
    for size in clothes_sizes:
        cursor.execute("INSERT INTO sizes (value, category_id) VALUES (?, ?)", (size, clothes_id))

    # Добавляем тестовые товары
    # Кроссовки
    cursor.execute("""
                   INSERT INTO products (name, price, sku, category_id, image_url)
                   VALUES (?, ?, ?, ?, ?, ?)
                   """, (
                       'Nike Air Max 90',
                       'Легендарные кроссовки Nike',
                       1299000,  # 12 990 руб.
                       'nike-airmax90-001',
                       shoes_id,
                       'https://example.com/nike_airmax90.jpg'
                   ))

    # Связываем кроссовки с размерами
    product_id = cursor.lastrowid
    cursor.execute("""
                   SELECT id
                   FROM sizes
                   WHERE category_id = ?
                     AND value IN ('40', '40.5', '41', '41.5', '42')
                   """, (shoes_id,))
    size_ids = [row[0] for row in cursor.fetchall()]
    for size_id in size_ids:
        cursor.execute("INSERT INTO products (product_id, size_id) VALUES (?, ?)", (product_id, size_id))

    # Футболка
    cursor.execute("SELECT id FROM categories WHERE name = 'Футболки'")
    tshirts_id = cursor.fetchone()[0]

    cursor.execute("""
                   INSERT INTO products (name, price, sku, category_id, image_url)
                   VALUES (?, ?, ?, ?, ?, ?)
                   """, (
                       'Футболка Nike Sport',
                       'Хлопковая футболка',
                       499000,  # 4 990 руб.
                       'nike-tshirt-2023',
                       tshirts_id,
                       'https://example.com/nike_tshirt.jpg'
                   ))

    # Связываем футболку с размерами
    product_id = cursor.lastrowid
    cursor.execute("""
                   SELECT id
                   FROM sizes
                   WHERE category_id = (SELECT id FROM categories WHERE name = 'Одежда')
                     AND value IN ('S', 'M', 'L')
                   """)
    size_ids = [row[0] for row in cursor.fetchall()]
    for size_id in size_ids:
        cursor.execute("INSERT INTO products (product_id, size_id) VALUES (?, ?)", (product_id, size_id))

    conn.commit()
    conn.close()
    logger.info("✅ База данных успешно инициализирована")


# Инициализируем базу при старте


from aiogram.exceptions import TelegramBadRequest


async def delete_previous_message(chat_id: int, user_id: int):
    if user_id in last_messages:
        messages_to_delete = last_messages[user_id]

        if not isinstance(messages_to_delete, list):
            messages_to_delete = [messages_to_delete]

        for msg_id in messages_to_delete:
            try:
                await bot.delete_message(chat_id, msg_id)
            except TelegramBadRequest as e:
                # Игнорируем ошибку "Сообщение не найдено"
                if "message to delete not found" not in str(e).lower():
                    print(f"Ошибка при удалении сообщения: {e}")

        del last_messages[user_id]


# Функция для создания главного меню
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="🎱 Каталог"))
    builder.add(types.KeyboardButton(text="🛒 Корзина"))
    builder.add(types.KeyboardButton(text="💠 Помощь"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


# ======== КОНСТАНТЫ ДЛЯ КАТЕГОРИЙ ========
SHOES_CATEGORY_NAME = "Кроссовки"
CLOTHES_CATEGORY_NAME = "Одежда"


# ======== ФУНКЦИИ ДЛЯ РАБОТЫ С КАТЕГОРИЯМИ ========

def get_user_stats():
    """Получает статистику пользователей для админки"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        # Общее количество активных пользователей
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        total_users = cursor.fetchone()[0]

        # Новые пользователи за сегодня
        cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')")
        today_users = cursor.fetchone()[0]

        # Активные пользователи (заходили за последние 7 дней)
        cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(last_login) >= DATE('now', '-7 days')")
        active_users = cursor.fetchone()[0]

        # Всего зарегистрировано
        cursor.execute("SELECT COUNT(*) FROM users")
        all_users = cursor.fetchone()[0]

        return {
            'total_users': total_users,
            'today_users': today_users,
            'active_users': active_users,
            'all_users': all_users
        }
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения статистики пользователей: {e}")
        return {'total_users': 0, 'today_users': 0, 'active_users': 0, 'all_users': 0}
    finally:
        conn.close()


def get_active_users():
    """Получает список активных пользователей для рассылки"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_chat_id FROM users WHERE is_active = TRUE AND telegram_chat_id IS NOT NULL")
        users = [row[0] for row in cursor.fetchall()]
        return users
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения активных пользователей: {e}")
        return []
    finally:
        conn.close()

def register_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(
        handle_size_selection,
        F.data.startswith("size_"),
        state=ProductStates.CHOOSING_SIZE
    )

    dp.register_callback_query_handler(
        handle_back_to_subcategories,
        F.data == "back_to_subcategories",
        state=ProductStates.CHOOSING_SIZE
    )


# Две основные категории Кроссовки и Одежда
def get_main_categories():
    """Получаем только основные категории (Кроссовки и Одежда)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем все корневые категории (без родителя)
    cursor.execute("SELECT id, name FROM categories WHERE parent_id IS NULL")
    root_categories = cursor.fetchall()

    # Фильтруем только нужные категории
    main_categories = [
        (id, name) for id, name in root_categories
        if name in [SHOES_CATEGORY_NAME, CLOTHES_CATEGORY_NAME,ACCESSORIES_CATEGORY_NAME]
    ]

    conn.close()
    return main_categories


# Субкатегории:Верхняя одежда,Штаны,Футболки,Аксессуары
def get_clothes_subcategories():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем ID категории "Одежда" по имени
    cursor.execute("SELECT id FROM categories WHERE name = ?", (CLOTHES_CATEGORY_NAME,))
    clothes_category = cursor.fetchone()

    if not clothes_category:
        conn.close()
        return []

    clothes_id = clothes_category[0]

    # Теперь получаем подкатегории по ID родительской категории
    cursor.execute("SELECT id, name FROM categories WHERE parent_id = ?", (clothes_id,))
    subcategories = [
        {"id": row[0], "name": row[1]}
        for row in cursor.fetchall()
    ]

    conn.close()
    return subcategories


def send_clothes_product(context, chat_id, product):
    # Форматирование цены
    formatted_price = format_price(product["price"])

    caption = (
        f"<b>{product['name']}</b>\n"
        f"💵 Цена: <b>{formatted_price}</b>\n"
        f"📏 Размер: <b>{product['size_value']}</b>\n"
        f"📦 В наличии: <b>{product['quantity']} шт.</b>\n"
    )

    # Кнопки размеров
    keyboard = []
    conn = get_db_connection()
    sizes = conn.execute('''
                         SELECT s.id, s.value
                         FROM products ps
                                  JOIN sizes s ON ps.size_id = s.id
                         WHERE ps.product_id = ?
                           AND ps.quantity > 0
                         ''', (product['id'],)).fetchall()
    conn.close()

    # Группируем кнопки по 2 в ряд
    for i in range(0, len(sizes), 2):
        row = []
        for size in sizes[i:i + 2]:
            row.append(InlineKeyboardButton(
                size['value'],
                callback_data=f'add_clothes_{product["id"]}_{size["id"]}'
            ))
        keyboard.append(row)

    # Отправляем сообщение с кнопками размеров
    context.bot.send_photo(
        chat_id=chat_id,
        photo=open('placeholder.jpg', 'rb'),  # Заглушка для фото
        caption=caption,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Кроссовки
def get_shoe_sizes():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM sizes WHERE category_id = 1")
    sizes = [row[0] for row in cursor.fetchall()]
    conn.close()
    return sizes


# Получаем доступные кроссовки
def get_products_by_size(size):
    """Получает товары по размеру с указанием доступного количества"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Для доступа к полям по имени
    cursor = conn.cursor()

    try:
        # Получаем ID категории "Кроссовки"
        cursor.execute("SELECT id FROM categories WHERE name = 'Кроссовки'")
        shoes_id = cursor.fetchone()[0]

        # Получаем ID размера
        cursor.execute("""
                       SELECT id
                       FROM sizes
                       WHERE value = ?
                         AND category_id = ?
                       """, (size, shoes_id))
        size_id = cursor.fetchone()

        if not size_id:
            return []

        size_id = size_id[0]

        # Получаем товары с количеством
        cursor.execute("""
                       SELECT p.id,
                              p.name,
                              p.price,
                              p.image_url,
                              ps.quantity as available_quantity
                       FROM products p
                                JOIN products ps ON p.id = ps.product_id
                       WHERE p.category_id = ?
                         AND ps.size_id = ?
                         AND ps.quantity > 0 # Только товары в наличии
                       ORDER BY p.name
                       """, (shoes_id, size_id))

        products = []
        for row in cursor.fetchall():
            products.append(dict(row))  # Преобразуем Row в словарь

        return products

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    finally:
        conn.close()


# Получаем доступную одежду
def get_clothes_sizes():
    """Получаем размеры для одежды"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        # 1. Получаем ID категории "Одежда"
        cursor.execute("SELECT id FROM categories WHERE name = ?", (CLOTHES_CATEGORY_NAME,))
        clothes_category = cursor.fetchone()

        if not clothes_category:
            print("Категория 'Одежда' не найдена в БД")
            return []

        clothes_id = clothes_category[0]

        # 2. Получаем размеры для этой категории
        cursor.execute("""
                       SELECT id, value
                       FROM sizes
                       WHERE category_id = ?
                       """, (clothes_id,))

        sizes = []
        for row in cursor.fetchall():
            sizes.append({
                'id': row[0],
                'value': row[1]
            })

        return sizes
    except sqlite3.Error as e:
        print(f"Ошибка при получении размеров одежды: {e}")
        return []
    finally:
        conn.close()


# Получаем ID категории "Футболки"
def get_t_shirts_category_id():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Находим ID категории "Одежда" (предполагаем, что у нее нет parent_id)
    cursor.execute("SELECT id FROM categories WHERE name = 'Одежда' AND parent_id IS NULL")
    clothes_category = cursor.fetchone()

    if clothes_category:
        clothes_id = clothes_category[0]
        # Находим ID подкатегории "Футболки"
        cursor.execute("SELECT id FROM categories WHERE name = 'Футболки' AND parent_id = ?", (clothes_id,))
        t_shirts_category = cursor.fetchone()
        if t_shirts_category:
            return t_shirts_category[0]

    conn.close()
    return None

# ======== ДОБАВЛЯЕМ В ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ========
def get_products_by_category(category_id: int) -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                p.id, p.name, p.price, p.discount_price, p.discount_percent,
                p.sku, p.image_url, p.quantity,
                c.discount_percent as category_discount_percent,
                c.discount_end_date as category_discount_end_date
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE p.category_id = ?
            AND p.size_id IS NULL
            AND p.quantity > 0
        """, (category_id,))

        products = []
        for row in cursor.fetchall():
            product = dict(row)
            # Рассчитываем актуальную цену
            product['actual_price'] = calculate_actual_price(
                product['price'],
                product['discount_price'],
                product['discount_percent'],
                product['category_discount_percent'],
                product['category_discount_end_date']
            )
            products.append(product)

        return products
    except Exception as e:
        logger.error(f"Ошибка в get_products_by_category: {e}")
        return []
    finally:
        conn.close()


# Функция для получения цены товара
def get_product_price(product_id):
    """Получает актуальную цену товара с учетом скидки"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT price, discount_price 
        FROM products 
        WHERE id = ?
    """, (product_id,))
    result = cursor.fetchone()
    conn.close()

    if result and result[1] is not None:  # Если есть скидочная цена
        return result[1], result[0]  # discount_price, original_price
    elif result:
        return result[0], None  # ordinary_price
    return None, None


# Пример использования в боте
async def send_product_info(chat_id, product_id):
    price, discount_price = get_product_price(product_id)

    if discount_price:  # Если есть оригинальная цена (значит есть скидка)
        message = f"💰 Цена: <s>{discount_price}₽</s> {price}₽\n🎉 Скидка: {int((1 - price / discount_price) * 100)}%"
    else:
        message = f"💰 Цена: {price}₽"

    # Отправляем сообщение с информацией о товаре
    await bot.send_message(chat_id, message, parse_mode='HTML')

def get_available_sizes(category_id: int) -> list:
    """Получает только размеры с наличием товаров"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT s.id, s.value
FROM sizes s
JOIN products p ON s.id = p.size_id
WHERE p.category_id = ?
  AND p.quantity > 0

        ''', (category_id,))
        return [{'id': row[0], 'value': row[1]} for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении доступных размеров: {e}")
        return []
    finally:
        conn.close()


# ======== ДОБАВИМ ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ СООБЩЕНИЯМИ ========
async def delete_product_messages(chat_id: int, message_ids: list[int]):
    """Удаляет сообщения с товарами пачками (до 100 за раз)"""
    if not message_ids:
        return

    # Разбиваем список идентификаторов на группы по 100
    for i in range(0, len(message_ids), 100):
        chunk = message_ids[i:i + 100]
        try:
            await bot.delete_messages(chat_id, chunk)
        except TelegramBadRequest as e:
            # Игнорируем "message not found" ошибки
            if "message to delete not found" not in str(e).lower():
                logger.warning(f"Ошибка удаления сообщений: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при удалении сообщений: {e}")

async def save_product_message(state: FSMContext, message_id: int):
    """Сохраняет ID сообщения с товаром в состоянии"""
    data = await state.get_data()
    product_messages = data.get('product_messages', [])
    product_messages.append(message_id)
    await state.update_data(product_messages=product_messages)



# Получение товаров по категории и размеру
def get_products_by_category_and_size(category_id: int, size_id: int) -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                p.id, p.name, p.price, p.discount_price, p.discount_percent,
                p.sku, p.image_url, p.quantity, s.value AS size_value,
                c.discount_percent as category_discount_percent,
                c.discount_end_date as category_discount_end_date,
                p.size_id
            FROM products p
            JOIN sizes s ON p.size_id = s.id
            JOIN categories c ON p.category_id = c.id
            WHERE p.category_id = ?
            AND p.size_id = ?
            AND p.quantity > 0
        """, (category_id, size_id))

        products = []
        for row in cursor.fetchall():
            product = dict(row)
            # Рассчитываем актуальную цену
            product['actual_price'] = calculate_actual_price(
                product['price'],
                product['discount_price'],
                product['discount_percent'],
                product['category_discount_percent'],
                product['category_discount_end_date']
            )
            products.append(product)

        return products
    except Exception as e:
        logger.error(f"Ошибка в get_products_by_category_and_size: {e}")
        return []
    finally:
        conn.close()


async def create_order(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Создаем заказ
        cursor.execute("INSERT INTO orders (user_id) VALUES (?)", (user_id,))
        order_id = cursor.lastrowid

        # Переносим товары из корзины в заказ
        cursor.execute("""
                       INSERT INTO order_items (order_id, product_id, size_id, quantity, price)
                       SELECT ?, ci.product_id, ci.size_id, ci.quantity, p.price
FROM cart_items ci
JOIN products p ON ci.product_id = p.id AND ci.size_id = p.size_id

                       WHERE ci.cart_id = (SELECT id FROM cart WHERE user_id = ?)
                       """, (order_id, user_id))

        # Очищаем корзину
        cursor.execute("DELETE FROM cart_items WHERE cart_id = (SELECT id FROM cart WHERE user_id = ?)", (user_id,))

        conn.commit()
        return order_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ======== ФУНКЦИИ ДЛЯ СОЗДАНИЯ КЛАВИАТУР ========
def category_keyboard():
    builder = InlineKeyboardBuilder()
    categories = get_main_categories()

    # Создаем словарь категорий для удобства
    category_dict = {name: id for id, name in categories}

    # Большая кнопка "Кроссовки"
    builder.row(types.InlineKeyboardButton(
        text="Кроссовки",
        callback_data=f"category_{category_dict['Кроссовки']}"
    ))

    # Две маленькие кнопки в одном ряду
    builder.row(
        types.InlineKeyboardButton(
            text="Одежда",
            callback_data=f"category_{category_dict['Одежда']}"
        ),
        types.InlineKeyboardButton(
            text="Аксессуары",
            callback_data=f"category_{category_dict['Аксессуары']}"
        ),
        width=2  # Две кнопки в ряду
    )

    return builder.as_markup()


def accessories_subcategory_keyboard():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем ID категории "Аксессуары"
    cursor.execute("SELECT id FROM categories WHERE name = 'Аксессуары'")
    accessories_id = cursor.fetchone()[0]

    # Получаем подкатегории
    cursor.execute("SELECT id, name FROM categories WHERE parent_id = ?", (accessories_id,))
    subcategories = cursor.fetchall()
    conn.close()

    builder = InlineKeyboardBuilder()
    for sub_id, sub_name in subcategories:
        # Для носков добавляем описание размеров
        if sub_name == "Носки":
            sub_name = "Носки"

        builder.add(types.InlineKeyboardButton(
            text=sub_name,
            callback_data=f"subcategory_{sub_id}"
        ))

    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_categories"
    ))

    builder.adjust(2, 2, 2, 1)  # Распределяем кнопки по 2 в ряд
    return builder.as_markup()


@dp.callback_query(F.data.startswith('subcategory_'), ProductStates.CHOOSING_ACCESSORIES_CATEGORY)
async def handle_accessories_subcategory(callback: CallbackQuery, state: FSMContext):

    subcategory_id = int(callback.data.split('_')[1])

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE id = ?", (subcategory_id,))
    subcategory_name = cursor.fetchone()[0]
    conn.close()

    # Сохраняем информацию о выбранной подкатегории
    await state.update_data(
        subcategory_id=subcategory_id,
        subcategory_name=subcategory_name
    )

        # Для других аксессуаров сразу показываем товары
    await show_products_without_size(callback, subcategory_id, state)

    await callback.answer()


@dp.callback_query(F.data == "back_to_accessories_subcategory")
async def handle_back_to_accessories_subcategory(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()

        # Удаляем сообщения с товарами
        if 'product_messages' in data:
            await delete_product_messages(callback.message.chat.id, data['product_messages'])

        # Получаем сохраненное сообщение с подкатегориями
        subcategory_message_id = data.get('accessories_subcategory_message_id')

        if subcategory_message_id:
            # Пытаемся отредактировать существующее сообщение
            try:
                await bot.edit_message_text(
                    chat_id=callback.message.chat.id,
                    message_id=subcategory_message_id,
                    text="Куда идём дальше?",
                    reply_markup=accessories_subcategory_keyboard()
                )
                # Удаляем текущее сообщение с кнопкой "Назад"
                try:
                    await callback.message.delete()
                except TelegramBadRequest:
                    pass
            except TelegramBadRequest:
                # Если не удалось отредактировать, отправляем новое
                new_msg = await callback.message.answer(
                    "Куда идём дальше?",
                    reply_markup=accessories_subcategory_keyboard()
                )
                await state.update_data(accessories_subcategory_message_id=new_msg.message_id)

            await state.update_data(accessories_subcategory_message_id=new_msg.message_id)

        await state.set_state(ProductStates.CHOOSING_ACCESSORIES_CATEGORY)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при возврате к подкатегориям аксессуаров: {e}")
        await callback.answer("⚠️ Произошла ошибка, попробуйте снова")




@dp.callback_query(F.data.startswith('sock_size_'))
async def handle_sock_size_selection(callback: CallbackQuery, state: FSMContext):
    size_code = callback.data.split('_')[-1]

    # Получаем данные о подкатегории
    data = await state.get_data()
    subcategory_id = data.get('subcategory_id')

    # Показываем товары для носков с учетом выбранного размера
    await show_products_without_size(callback, subcategory_id, state)
    await callback.answer()

def clothes_size_keyboard(category_id: int):
    """Клавиатура размеров для одежды с сортировкой"""
    sizes = get_available_sizes(category_id)
    sorted_sizes = sort_sizes(sizes, category_id)

    builder = InlineKeyboardBuilder()
    for size in sorted_sizes:
        builder.add(types.InlineKeyboardButton(
            text=size['value'],
            callback_data=f"size_{size['id']}"
        ))

    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_subcategories"
    ))

    builder.adjust(3, 3)
    return builder.as_markup()


# Общая функция для получения размера по значению
def get_size_id_by_value(size_value: str, category_id: int) -> Optional[int]:
    try:
        # Если пришло число - преобразуем в строку
        if isinstance(size_value, int):
            size_value = str(size_value)

        # Для кроссовок заменяем точку на запятую
        if category_id == 1:
            size_value = size_value.replace('.', ',')

        query = "SELECT id FROM sizes WHERE value = ? AND category_id = ?"
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query, (size_value, category_id))
        result = cursor.fetchone()
        conn.close()

        return result[0] if result else None
    except Exception as e:
        logger.error(f"Ошибка в get_size_id_by_value: {e}")
        return None


def shoe_size_keyboard(category_id: int):
    """Клавиатура размеров для кроссовок с сортировкой"""
    sizes = get_available_sizes(category_id)
    sorted_sizes = sort_sizes(sizes, category_id)

    builder = InlineKeyboardBuilder()
    for size in sorted_sizes:
        builder.add(types.InlineKeyboardButton(
            text=size['value'],
            callback_data=f"size_{size['id']}"
        ))

    builder.add(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_categories"
    ))

    builder.adjust(4, 4, 4, 4, 4, 4, 1)
    return builder.as_markup()


# Функция для получения размеров из БД
def get_sizes_by_category(category_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, value FROM sizes WHERE category_id = ?", (category_id,))
    sizes = [{'id': row[0], 'value': row[1]} for row in cursor.fetchall()]
    conn.close()
    return sizes


# ======== ДОБАВИМ ФУНКЦИИ ДЛЯ СОРТИРОВКИ РАЗМЕРОВ ========
def sort_sizes(sizes: list, category_id: int) -> list:
    """Сортирует размеры в зависимости от категории"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
        category_row = cursor.fetchone()
        category_name = category_row[0] if category_row else ""
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения категории: {e}")
        return sizes
    finally:
        if conn:
            conn.close()

    if not category_name:
        return sizes

    if category_name == SHOES_CATEGORY_NAME:
        # Для кроссовок: сортируем числовые размеры
        try:
            return sorted(
                sizes,
                key=lambda x: float(x['value'].replace(',', '.')))
        except ValueError:
            logger.warning("Ошибка преобразования размера в число")
            return sizes
    elif category_name == CLOTHES_CATEGORY_NAME:
        # Для одежды: сортируем по стандартной сетке размеров
        size_order = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        return sorted(
            sizes,
            key=lambda x: size_order.index(x['value']) if x['value'] in size_order else len(size_order)
        )
    else:
        return sizes

# 2. Клавиатура для подкатегорий одежды
def clothes_subcategory_keyboard():
    subcategories = get_clothes_subcategories()

    builder = InlineKeyboardBuilder()
    for subcategory in subcategories:
        builder.button(
            text=subcategory['name'],
            callback_data=f"subcategory_{subcategory['id']}"
        )

    # Измените callback_data на "back_to_categories"
    builder.button(text="🔙 Назад", callback_data="back_to_categories")
    builder.adjust(2)  # По 2 кнопки в ряд

    return builder.as_markup()


def cart_empty_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton(text=" Перейти в каталог", callback_data="back_to_categories"))
    return keyboard


def calculate_actual_price(product_price, product_discount_price,
                           product_discount_percent, category_discount_percent,
                           category_discount_end_date):
    """
    Расчет актуальной цены с учетом всех скидок
    Приоритет: 1. discount_price, 2. product_discount_percent, 3. category_discount_percent
    """
    from datetime import datetime

    # Если указана явная скидочная цена
    if product_discount_price is not None:
        return product_discount_price

    # Если есть процентная скидка на товар
    if product_discount_percent is not None:
        return product_price * (100 - product_discount_percent) // 100

    # Если есть активная скидка на категорию
    if (category_discount_percent is not None and
            (category_discount_end_date is None or
             datetime.strptime(category_discount_end_date, '%Y-%m-%d') >= datetime.now())):
        return product_price * (100 - category_discount_percent) // 100

    # Без скидки
    return product_price


async def send_product_info(chat_id: int, product: dict):
    """Отправляет информацию о товаре с актуальной ценой"""
    try:
        # Используем актуальную цену
        actual_price = product.get('actual_price', product.get('price', 0))
        original_price = product.get('price', 0)

        caption = (
            f"<b>{product['name']}</b>\n"
            f"💵 Цена: <b>{format_price(actual_price)}</b>\n"
        )

        # Показываем старую цену если есть скидка
        if actual_price < original_price:
            discount_percent = round((1 - actual_price / original_price) * 100)
            caption += f"🚫 <s>{format_price(original_price)}</s> (-{discount_percent}%)\n"

        caption += (
            f"📏 Размер: <b>{product.get('size_value', 'N/A')}</b>\n"
            f"📦 В наличии: <b>{product.get('quantity', 0)} шт.</b>\n"
        )

        # Кнопка "Добавить в корзину"
        size_id = product.get('size_id', 0)
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🛒 Добавить в корзину",
                callback_data=f"add_{product['id']}_{size_id}"
            )
        ]])

        # Отправляем фото или текст
        image_url = product.get("image_url")
        if image_url and image_url != "[]":
            try:
                # Пробуем распарсить JSON
                images = json.loads(image_url)
                if images:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=images[0],
                        caption=caption,
                        reply_markup=markup,
                        parse_mode=ParseMode.HTML
                    )
                    return
            except:
                # Если не JSON, отправляем как строку
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=caption,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML
                )
                return

        # Если фото нет, отправляем текст
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=markup,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Ошибка отправки товара: {e}")


# Для аксессуаров
async def show_products_without_size(callback: CallbackQuery, category_id: int, state: FSMContext):
    """Показывает товары без запроса размера (для аксессуаров) с параллельной отправкой"""
    try:
        products = get_products_by_category(category_id)
        data = await state.get_data()

        if not products:
            await callback.answer("😢 Товаров в этой категории пока нет")
            return

        sent_messages = []

        # Создаем задачи для параллельной отправки
        tasks = []
        for product in products:
            task = asyncio.create_task(send_single_product(callback.message.chat.id, product))
            tasks.append(task)

        # Параллельно отправляем все товары
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Собираем успешные message_id
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Ошибка отправки товара: {result}")
            elif result:
                sent_messages.append(result)

        # Сохраняем ID отправленных сообщений
        await state.update_data(product_messages=sent_messages)

        # Добавляем кнопку "Назад"
        back_button = InlineKeyboardButton(
            text="← Назад к выбору",
            callback_data="back_to_accessories_subcategory"
        )
        back_markup = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
        back_message = await callback.message.answer(
            "Выберите действие:",
            reply_markup=back_markup
        )
        sent_messages.append(back_message.message_id)
        await state.update_data(product_messages=sent_messages)

    except Exception as e:
        logger.error(f"Ошибка при показе товаров без размера: {e}")
        await callback.answer("⚠️ Произошла ошибка при загрузке товаров")


async def send_single_product(chat_id: int, product: dict) -> Optional[int]:
    """Отправляет один товар и возвращает message_id"""
    try:
        # Получаем цены и преобразуем их к числам
        actual_price = product.get('actual_price', product.get('price', 0))
        original_price = product.get('price', 0)

        # Преобразуем к float для корректного сравнения
        try:
            actual_price_num = float(actual_price) if actual_price else 0
            original_price_num = float(original_price) if original_price else 0
        except (ValueError, TypeError):
            actual_price_num = 0
            original_price_num = 0

        caption = (
            f"<b>{product['name']}</b>\n\n"
            f"💵 <b>Цена:</b> {format_price(actual_price)}\n"
        )

        # Показываем старую цену если есть скидка (сравниваем числа)
        if actual_price_num < original_price_num:
            discount_percent = round((1 - actual_price_num / original_price_num) * 100)
            caption += f"🚫 <s>{format_price(original_price)}</s> (-{discount_percent}%)\n"

        caption += f"📦 <b>В наличии:</b> {product.get('quantity', 0)} шт."

        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🛒 Добавить в корзину",
                callback_data=f"add_{product['id']}_0"  # 0 для безразмерных товаров
            )
        ]])

        if product.get('image_url'):
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=product['image_url'],
                caption=caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )

        return msg.message_id

    except Exception as e:
        logger.error(f"Ошибка отправки товара {product.get('name', 'Unknown')}: {e}")
        return None


async def delete_previous_messages(user_id: int, chat_id: int):
    """Удаляет все предыдущие сообщения бота для пользователя"""
    if user_id in last_messages:
        message_ids = last_messages[user_id]
        if not isinstance(message_ids, list):
            message_ids = [message_ids]

        for msg_id in message_ids:
            try:
                await bot.delete_message(chat_id, msg_id)
            except TelegramBadRequest as e:
                if "message to delete not found" not in str(e).lower():
                    logger.debug(f"Ошибка удаления сообщения {msg_id}: {e}")
            except Exception as e:
                logger.debug(f"Неизвестная ошибка при удалении сообщения {msg_id}: {e}")

        del last_messages[user_id]


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем предыдущие сообщения
    await delete_previous_messages(user_id, chat_id)

    # Сбрасываем состояние
    data = await state.get_data()
    if 'product_messages' in data:
        await delete_product_messages(chat_id, data['product_messages'])
    await state.clear()

    # Регистрация/обновление пользователя в БД
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        user = message.from_user
        chat_id = message.chat.id

        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (user.id,))
        existing_user = cursor.fetchone()

        if not existing_user:
            cursor.execute("""
                INSERT INTO users (telegram_id, username, telegram_chat_id, created_at, last_login, is_active)
                VALUES (?, ?, ?, datetime('now'), datetime('now'), TRUE)
            """, (
                user.id,
                user.username or "",
                chat_id
            ))
            welcome_text = "👋 Добро пожаловать!"
        else:
            cursor.execute("""
                UPDATE users 
                SET last_login = datetime('now'), 
                    is_active = TRUE,
                    username = ?,
                    telegram_chat_id = ?
                WHERE telegram_id = ?
            """, (
                user.username or "",
                chat_id,
                user.id
            ))
            welcome_text = "👋 С возвращением!"

        conn.commit()

    except sqlite3.Error as e:
        logger.error(f"Database error in /start: {e}")
        welcome_text = "👋 С возвращением!"  # fallback
    finally:
        conn.close()

    # Отправляем ПЕРВОЕ сообщение - приветствие
    welcome_msg = await message.answer(welcome_text)

    # Отправляем ВТОРОЕ сообщение - описание и меню
    description_msg = await message.answer(
        "В Stone собрано много брендовой одежды и обуви по лучшим ценам.\n\n"
        f"БОТ поможет тебе просмотреть весь ассортимент. \n",
        reply_markup=main_menu()
    )

    # Сохраняем ОБА ID сообщений для последующего удаления
    last_messages[user_id] = [welcome_msg.message_id, description_msg.message_id]

@dp.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_menu()
    )


@dp.callback_query(F.data == 'back_to_categories')
async def handle_back_to_categories(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    try:
        # Удаляем текущее сообщение и все предыдущие
        await delete_previous_messages(user_id, chat_id)

        # Очищаем состояние
        data = await state.get_data()
        if 'product_messages' in data:
            await delete_product_messages(chat_id, data['product_messages'])
        await state.clear()

        # Отправляем новое сообщение с категориями
        category_msg = await callback.message.answer(
            "О, новый клиент! В какую категорию идём 🧩",
            reply_markup=category_keyboard()
        )

        # Сохраняем ID нового сообщения
        last_messages[user_id] = [category_msg.message_id]

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка в обработчике back_to_categories: {e}")
        await callback.answer("⚠️ Произошла ошибка, попробуйте снова")

# Обработчик команды /help
@dp.message(lambda message: message.text == '💠 Помощь')
async def show_help(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем предыдущие сообщения (оба: приветствие и описание)
    await delete_previous_messages(user_id, chat_id)

    update_user_activity(message.from_user.id)

    help_text = (
        "🤖 Доступные команды:\n"
        "/start - Начать диалог\n"
        "/help - Получить справку\n"
        "/cart - Твоя корзина\n\n"
        "Основные функции:\n"
        "🎱 Каталог - Просмотр товаров по категориям\n"
        "🛒 Корзина - Просмотр вашей корзины\n"
        "💠 Помощь - Вызов этого сообщения\n"
        "📬 Для связи с технической поддержкой:@StoneZakhar\n"
    )
    msg = await message.answer(help_text, reply_markup=main_menu())
    last_messages[user_id] = [msg.message_id]


# Обработчик "Корзины" в главном меню
@dp.message(lambda message: message.text in ['🛒 Корзина', 'Корзина', 'корзина', '/cart'])
async def show_cart(message: types.Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем предыдущие сообщения (оба: приветствие и описание)
    await delete_previous_messages(user_id, chat_id)

    update_user_activity(message.from_user.id)
    conn = get_db_connection()

    try:
        # Удаляем предыдущие сообщения бота
        if user_id in last_messages:
            try:
                await bot.delete_message(message.chat.id, last_messages[user_id])
            except Exception:
                pass

        with conn:
            cursor = conn.cursor()
            # Получаем корзину пользователя
            cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
            cart_data = cursor.fetchone()

            if not cart_data:
                # Если корзина пуста
                msg = await message.answer(
                    "🛒 Ваша корзина пуста",
                    reply_markup=cart_empty_keyboard()
                )
                last_messages[user_id] = msg.message_id
                return

            cart_id = cart_data[0]

            # Получаем товары в корзине (ИСПРАВЛЕННЫЙ ЗАПРОС)
            cursor.execute("""
                SELECT 
                    p.name, 
                    s.value, 
                    ci.quantity, 
                    p.price,
                    p.discount_price,
                    p.discount_percent,
                    cat.discount_percent as category_discount_percent,
                    cat.discount_end_date as category_discount_end_date
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.id
                LEFT JOIN sizes s ON ci.size_id = s.id
                JOIN cart c ON ci.cart_id = c.id
                JOIN categories cat ON p.category_id = cat.id
                WHERE c.user_id = ?
            """, (user_id,))
            cart_items = cursor.fetchall()

            if not cart_items:
                # Если корзина пуста
                msg = await message.answer(
                    "🛒 Ваша корзина пуста",
                    reply_markup=cart_empty_keyboard()
                )
                last_messages[user_id] = msg.message_id
                return

            # Формируем сообщение с содержимым корзины
            cart_text = "🛒 <b>Ваша корзина:</b>\n\n"
            total = 0
            total_items = 0

            for i, item in enumerate(cart_items, 1):
                name, size, quantity, price, discount_price, discount_percent, category_discount_percent, category_discount_end_date = item

                # Рассчитываем актуальную цену
                actual_price = calculate_actual_price(
                    price,
                    discount_price,
                    discount_percent,
                    category_discount_percent,
                    category_discount_end_date
                )

                item_total = actual_price * quantity
                total += item_total
                total_items += quantity

                size_display = f" (Размер: {size})" if size else ""
                cart_text += (
                    f"{i}. {name}{size_display}\n"
                    f"   Кол-во: {quantity} × {format_price(actual_price)} = {format_price(item_total)}\n\n"
                )

            # Создаем клавиатуру для корзины
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="❌ Очистить корзину", callback_data="clear_cart"),
                        InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_shop")
                    ]
                ]
            )

            # Отправляем сообщение с содержимым корзины
            msg = await message.answer(
                cart_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            last_messages[user_id] = [msg.message_id]

    except sqlite3.Error as e:
        logger.error(f"Ошибка БД при показе корзины: {e}")
        await message.answer("⚠️ Произошла ошибка при загрузке корзины")
    except Exception as e:
        logger.exception(f"Неожиданная ошибка: {e}")
        await message.answer("⚠️ Произошла непредвиденная ошибка")
    finally:
        if conn:
            conn.close()


def cart_empty_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=" Перейти в каталог", callback_data="back_to_shop")]
        ]
    )


# Обработчик кнопки "Магазин"
@dp.message(lambda message: message.text in ['🎱 Каталог', 'Каталог', 'каталог', '/catalog'])
async def show_categories(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем предыдущие сообщения (оба: приветствие и описание)
    await delete_previous_messages(user_id, chat_id)
    await state.clear()

    update_user_activity(message.from_user.id)

    # Отправляем новое сообщение с категориями
    category_msg = await message.answer(
        "О, новый клиент! В какую категорию идём? 🧩",
        reply_markup=category_keyboard()
    )

    # Сохраняем ID нового сообщения
    last_messages[user_id] = [category_msg.message_id]


# Обработчик кнопки "Помощь"
@dp.message(lambda message: message.text == '💠 Помощь')
async def show_help(message: types.Message):
    await cmd_help(message)


# Обработчик выбора категории
def category_has_products(category_id: int) -> bool:
    """Проверяет, есть ли товары в категории (включая подкатегории)"""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        # Рекурсивно получаем все подкатегории
        cursor.execute("""
            WITH RECURSIVE subcategories(id) AS (
                SELECT id FROM categories WHERE id = ?
                UNION ALL
                SELECT c.id FROM categories c
                JOIN subcategories s ON c.parent_id = s.id
                )
                SELECT EXISTS (
                SELECT 1
                FROM products p
                WHERE p.category_id IN (SELECT id FROM subcategories)
                  AND p.quantity > 0
                LIMIT 1
)

            
        """, (category_id,))

        return cursor.fetchone()[0] == 1
    finally:
        conn.close()


@dp.callback_query(F.data.startswith('category_'))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    category_id = int(callback.data.split('_')[1])

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM categories WHERE id = ?", (category_id,))
    category_name = cursor.fetchone()[0]
    conn.close()

    # Проверяем наличие товаров в категории
    if not category_has_products(category_id):
        await callback.answer("😢 Товаров в этой категории пока нет", show_alert=True)
        return

    await state.update_data(
        category_id=category_id,
        category_name=category_name
    )

    # Удаляем предыдущее сообщение с категориями
    try:
        await bot.delete_message(callback.message.chat.id, callback.message.message_id)
    except Exception as e:
        logger.debug(f"Ошибка удаления сообщения категорий: {e}")

    if category_name == SHOES_CATEGORY_NAME:
        size_msg = await callback.message.answer(
            "Какой размер кроссовок?",
            reply_markup=shoe_size_keyboard(category_id)
        )
        await state.update_data(size_message_id=size_msg.message_id)
        last_messages[callback.from_user.id] = [size_msg.message_id]
        await state.set_state(ProductStates.CHOOSING_SIZE)

    elif category_name == CLOTHES_CATEGORY_NAME:
        size_msg = await callback.message.answer(
            "Куда идём дальше?",
            reply_markup=clothes_subcategory_keyboard()
        )
        await state.update_data(size_message_id=size_msg.message_id)
        last_messages[callback.from_user.id] = [size_msg.message_id]
        await state.set_state(ProductStates.CHOOSING_CLOTHES_SUBCATEGORY)

    elif category_name == "Аксессуары":
        size_msg = await callback.message.answer(
            "Куда идём дальше?",
            reply_markup=accessories_subcategory_keyboard()
        )
        await state.update_data(size_message_id=size_msg.message_id)
        last_messages[callback.from_user.id] = [size_msg.message_id]
        await state.set_state(ProductStates.CHOOSING_ACCESSORIES_CATEGORY)

    await callback.answer()


@dp.callback_query(F.data.startswith('subcategory_'), ProductStates.CHOOSING_CLOTHES_SUBCATEGORY)
async def handle_subcategory_selection(callback: CallbackQuery, state: FSMContext):
    try:
        subcategory_id = int(callback.data.split('_')[1])

        # Проверяем наличие товаров в подкатегории
        if not category_has_products(subcategory_id):
            await callback.answer("😢 Товаров в этой категории пока нет", show_alert=True)
            return

        # Удаляем предыдущее сообщение
        try:
            await bot.delete_message(callback.message.chat.id, callback.message.message_id)
        except Exception as e:
            logger.debug(f"Ошибка удаления сообщения подкатегорий: {e}")

        # Получаем название подкатегории
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories WHERE id = ?", (subcategory_id,))
        subcategory_name = cursor.fetchone()[0]
        conn.close()

        # Сохраняем информацию в состоянии
        await state.update_data(
            subcategory_id=subcategory_id,
            subcategory_name=subcategory_name
        )

        # Отправляем новое сообщение с выбором размера
        size_msg = await callback.message.answer(
            "Какой размер?",
            reply_markup=clothes_size_keyboard(subcategory_id)
        )

        # Сохраняем ID нового сообщения
        await state.update_data(size_message_id=size_msg.message_id)
        last_messages[callback.from_user.id] = [size_msg.message_id]

        await state.set_state(ProductStates.CHOOSING_SIZE)
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка обработки подкатегории: {e}")
        await callback.answer("⚠️ Произошла ошибка при загрузке категории", show_alert=True)


@dp.callback_query(F.data.startswith('size_'), ProductStates.CHOOSING_SIZE)
async def handle_size_selection(callback: CallbackQuery, state: FSMContext):
    try:
        # Удаляем сообщение с размерами
        try:
            await bot.delete_message(callback.message.chat.id, callback.message.message_id)
        except Exception as e:
            logger.debug(f"Ошибка удаления сообщения размеров: {e}")

        # Получаем новый размер
        size_id = int(callback.data.split('_')[1])
        data = await state.get_data()
        target_id = data.get('subcategory_id') or data.get('category_id')

        # Получаем товары для нового размера
        products = get_products_by_category_and_size(target_id, size_id)

        if not products:
            await callback.answer("😢 Товаров этого размера нет в наличии", show_alert=True)
            # Возвращаем к выбору размеров
            size_msg = await callback.message.answer(
                "Какой размер?",
                reply_markup=clothes_size_keyboard(target_id) if data.get('subcategory_id') else shoe_size_keyboard(
                    target_id)
            )
            last_messages[callback.from_user.id] = [size_msg.message_id]
            return

        # Отправляем уведомление о загрузке
        loading_msg = await callback.message.answer(f"👁️‍🗨️ Нашел {len(products)} товаров. Загружаю...")

        # Параллельная отправка товаров
        sent_messages = []
        tasks = []

        for product in products:
            task = asyncio.create_task(send_single_product_with_size(callback.message.chat.id, product, size_id))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Ошибка отправки товара: {result}")
            elif result:
                sent_messages.append(result)

        # Удаляем сообщение о загрузке
        await bot.delete_message(callback.message.chat.id, loading_msg.message_id)

        # Добавляем кнопку "Назад"
        back_button = InlineKeyboardButton(
            text="← Назад к выбору размеров",
            callback_data="back_to_size_selection"
        )
        back_markup = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
        back_message = await callback.message.answer(
            "Выберите действие:",
            reply_markup=back_markup
        )
        sent_messages.append(back_message.message_id)

        # Сохраняем все ID сообщений
        last_messages[callback.from_user.id] = sent_messages
        await state.update_data(product_messages=sent_messages)

        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка обработки размера: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)


async def send_single_product_with_size(chat_id: int, product: dict, size_id: int) -> Optional[int]:
    """Отправляет один товар с размером и возвращает message_id"""
    try:
        # Формируем caption с учетом скидок
        actual_price = product.get('actual_price', product.get('price', 0))
        original_price = product.get('price', 0)

        caption = (
            f"<b>{product['name']}</b>\n\n"
            f"💵 <b>Цена:</b> {format_price(actual_price)}\n"
        )

        # Показываем старую цену если есть скидка
        if actual_price < original_price:
            discount_percent = round((1 - actual_price / original_price) * 100)
            caption += f"🚫 <s>{format_price(original_price)}</s> (-{discount_percent}%)\n"

        caption += (
            f"🎱 <b>Размер:</b> {product.get('size_value', 'N/A')}\n"
            f"📦 <b>В наличии:</b> {product.get('quantity', 0)} шт.\n"
        )

        # Создаем кнопку "Добавить в корзину"
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="🛒 Добавить в корзину",
                callback_data=f"add_{product['id']}_{size_id}"
            )
        ]])

        # Оптимизация обработки изображений
        image_url = product.get('image_url')
        try:
            # Пробуем распарсить JSON если это список изображений
            if image_url and image_url.startswith('['):
                images = json.loads(image_url)
                image_url = images[0] if images else None
        except:
            image_url = None

        # Отправляем сообщение
        if image_url:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )
        else:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=markup,
                parse_mode=ParseMode.HTML
            )

        return msg.message_id

    except Exception as e:
        logger.error(f"Ошибка отправки товара {product.get('name', 'Unknown')}: {e}")
        return None


@dp.callback_query(F.data == "back_to_size_selection")
async def handle_back_to_size_selection(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()

        # Удаляем все сообщения с товарами
        if 'product_messages' in data:
            await delete_product_messages(callback.message.chat.id, data['product_messages'])

        # Удаляем текущее сообщение с кнопкой "Назад"
        try:
            await bot.delete_message(callback.message.chat.id, callback.message.message_id)
        except Exception as e:
            logger.debug(f"Ошибка удаления сообщения назад: {e}")

        # Получаем ID текущей категории
        target_id = data.get('subcategory_id') or data.get('category_id')

        # Определяем тип клавиатуры
        if data.get('subcategory_id'):  # Одежда
            keyboard = clothes_size_keyboard(target_id)
        else:  # Кроссовки
            keyboard = shoe_size_keyboard(target_id)

        # Отправляем новое сообщение с размерами
        size_msg = await callback.message.answer(
            "Какой размер?",
            reply_markup=keyboard
        )

        # Обновляем последние сообщения
        last_messages[callback.from_user.id] = [size_msg.message_id]
        await state.update_data(product_messages=[])

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при возврате к выбору размера: {e}")
        await callback.answer("⚠️ Произошла ошибка, попробуйте снова")



# # 5. Функция показа футболок
# async def show_tshirts(callback: types.CallbackQuery):
#     conn = get_db_connection()
#     products = conn.execute('''
#                             SELECT p.id, p.name, p.price, p.sku
#                             FROM products p
#                             WHERE p.category_id = 3
#                             ''').fetchall()
#     conn.close()
#
#     for product in products:
#         await send_clothes_product(callback.bot, callback.message.chat.id, product)

@dp.callback_query(F.data == 'back_to_subcategories')
async def handle_back_to_subcategories(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()

        # Удаляем сообщения с товарами
        if 'product_messages' in data:
            await delete_product_messages(callback.message.chat.id, data['product_messages'])

        # Редактируем текущее сообщение вместо создания нового
        await callback.message.edit_text(
            "Куда идём дальше?",
            reply_markup=clothes_subcategory_keyboard()
        )

        # Обновляем состояние
        await state.set_state(ProductStates.CHOOSING_CLOTHES_SUBCATEGORY)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при возврате к подкатегориям: {e}")
        await callback.answer("⚠️ Произошла ошибка, попробуйте снова")
# Назад
@dp.callback_query(F.data == "back_to_accessories_subcategory")
async def handle_back_to_accessories_subcategory(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()

        # Удаляем сообщения с товарами
        if 'product_messages' in data:
            await delete_product_messages(callback.message.chat.id, data['product_messages'])

        # Редактируем текущее сообщение вместо создания нового
        await callback.message.edit_text(
            "Куда идём дальше?",
            reply_markup=accessories_subcategory_keyboard()
        )

        # Обновляем состояние
        await state.set_state(ProductStates.CHOOSING_ACCESSORIES_CATEGORY)
        await callback.answer()

    except TelegramBadRequest as e:
        if "message to edit not found" in str(e):
            # Если сообщение не найдено, отправляем новое
            await callback.message.answer(
                "Куда идём дальше?",
                reply_markup=accessories_subcategory_keyboard()
            )
            await state.set_state(ProductStates.CHOOSING_ACCESSORIES_CATEGORY)
        else:
            logger.error(f"Ошибка Telegram при возврате к подкатегориям аксессуаров: {e}")
            await callback.answer("⚠️ Произошла ошибка, попробуйте снова")
    except Exception as e:
        logger.error(f"Ошибка при возврате к подкатегориям аксессуаров: {e}")
        await callback.answer("⚠️ Произошла ошибка, попробуйте снова")

# Вспомогательная функция для массового удаления сообщений
async def delete_messages(chat_id: int, message_ids: list[int]):
    for msg_id in message_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
        except TelegramBadRequest:
            continue


# КОРЗИНА
# Обработчик добавления в корзину
# @dp.callback_query(F.data.startswith('add_'))
# async def handle_add_to_cart(callback: types.CallbackQuery):
#     try:
#         # Парсим данные из callback
#         parts = callback.data.split('_')
#         product_id = int(parts[1])
#         size_id = int(parts[2]) if len(parts) > 2 else None
#
#         user_id = callback.from_user.id
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         # Для товаров без размера (аксессуары)
#         if size_id is None:
#             # Проверяем, требует ли товар размера
#             cursor.execute("SELECT category_id FROM products WHERE id = ?", (product_id,))
#             category_id = cursor.fetchone()[0]
#
#             if category_id != 8:  # 8 - ID для аксессуаров
#                 await callback.answer(
#                     "🚫 Для этого товара нужно выбрать размер!\n"
#                     "Вернитесь к товару и выберите нужный размер.",
#                     show_alert=True
#                 )
#                 return
#
#         # Создаем/получаем корзину
#         cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
#         cart = cursor.fetchone()
#
#         if cart:
#             cart_id = cart[0]
#         else:
#             cursor.execute("INSERT INTO cart (user_id) VALUES (?)", (user_id,))
#             cart_id = cursor.lastrowid
#
#         # Добавляем товар в корзину
#         cursor.execute("""
#                        INSERT INTO cart_items (cart_id, product_id, size_id, quantity)
#                        VALUES (?, ?, ?, 1) ON CONFLICT(cart_id, product_id, size_id)
#             DO
#                        UPDATE SET quantity = quantity + 1
#                        """, (cart_id, product_id, size_id))
#
#         conn.commit()
#
#         # Обновляем сообщение с товаром
#         await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
#             inline_keyboard=[
#                 [InlineKeyboardButton(text="🛒 Посмотреть корзину", callback_data="view_cart")],
#                 [InlineKeyboardButton(text="❌Очистить корзину", callback_data="clear_cart")],
#
#             ]
#         ))
#
#         await callback.answer("💠 Товар добавлен в корзину!")
#
#     except sqlite3.Error as e:
#         await callback.answer(f"❌ Ошибка базы данных: {str(e)}", show_alert=True)
#     except Exception as e:
#         logger.exception(f"Ошибка добавления в корзину: {e}")
#         await callback.answer("❌ Произошла ошибка при добавлении в корзину", show_alert=True)
#     finally:
#         if conn:
#             conn.close()


# Обработчик для кнопки "Назад в главное меню"
@dp.callback_query(F.data.startswith("back_to_shop"))
async def handle_back_to_shop(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    try:
        # Удаляем текущее сообщение с корзиной
        await bot.delete_message(chat_id, callback.message.message_id)
    except Exception as e:
        logger.debug(f"Ошибка при удалении сообщения корзины: {e}")

    # Полностью очищаем состояние
    await state.clear()

    # Удаляем все предыдущие сообщения бота
    if user_id in last_messages:
        try:
            if isinstance(last_messages[user_id], list):
                for msg_id in last_messages[user_id]:
                    try:
                        await bot.delete_message(chat_id, msg_id)
                    except Exception:
                        continue
            else:
                await bot.delete_message(chat_id, last_messages[user_id])
        except Exception as e:
            logger.debug(f"Ошибка при удалении предыдущих сообщений: {e}")
        finally:
            del last_messages[user_id]

    # Показываем категории заново
    await show_categories_handler(callback.message, state)
    await callback.answer()


async def show_categories_handler(message: types.Message, state: FSMContext):
    """Показ категорий с полной очисткой состояния"""
    await state.clear()
    update_user_activity(message.from_user.id)

    # Удаляем предыдущие сообщения
    user_id = message.from_user.id
    if user_id in last_messages:
        try:
            if isinstance(last_messages[user_id], list):
                for msg_id in last_messages[user_id]:
                    try:
                        await bot.delete_message(message.chat.id, msg_id)
                    except Exception:
                        continue
            else:
                await bot.delete_message(message.chat.id, last_messages[user_id])
        except Exception as e:
            logger.debug(f"Ошибка при удалении сообщений: {e}")

    # Отправляем новое сообщение с категориями
    category_msg = await message.answer(
        "О, новый клиент! В какую категорию идём? 🧩",
        reply_markup=category_keyboard()
    )

    # Сохраняем только ID сообщения с категориями
    last_messages[user_id] = [category_msg.message_id]

# Функция для создания размера, если его нет
async def create_size_if_not_exists(cursor, size_value, category_name):
    # Проверяем существование размера
    cursor.execute("SELECT id FROM sizes WHERE value = ?", (size_value,))
    if cursor.fetchone():
        return

    # Получаем или создаем категорию
    cursor.execute("SELECT id FROM size_categories WHERE name = ?", (category_name,))
    category_result = cursor.fetchone()

    if not category_result:
        cursor.execute("INSERT INTO size_categories (name) VALUES (?)", (category_name,))
        category_id = cursor.lastrowid
    else:
        category_id = category_result[0]

    # Создаем размер
    cursor.execute("""
                   INSERT INTO sizes (value, category_id)
                   VALUES (?, ?)
                   """, (size_value, category_id))


# ======== АДМИНСКИЕ ФУНКЦИИ ========
# ADMIN Обработчик Панели Админа
@dp.message(Command("admin"))
async def send_admin_panel(message: types.Message):
    # Проверяем, является ли пользователь администратором
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав доступа к этой команде🌚")
        return

    # Создаем кнопку с WebApp
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(
                text="Открыть панель управления",
                web_app=WebAppInfo(url=ADMIN_PANEL_URL)
            )]
        ],
        resize_keyboard=True
    )

    # Отправляем сообщение с кнопкой
    await message.answer(
        "Добро пожаловать в панель управления Stone Shop!",
        reply_markup=keyboard
    )


@dp.message(Command("test_connection"))
async def cmd_test_connection(message: Message):
    # Проверяем связь товара с размером
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Для футболки Oakley размера S
    cursor.execute("""
                   SELECT p.name,
                          s.value AS size
                   FROM products p
                       JOIN sizes L
                   ON p.size_id = s.id
                   WHERE p.sku = '0069-FOA406535-S'
                   """)

    result = cursor.fetchone()
    response = f"Товар: {result[0]}, Размер: {result[1]}" if result else "Запись не найдена"

    await message.answer(response)
    conn.close()


# ADMIN Проверка ID
@dp.message(Command("check_ids"))
async def cmd_check_ids(message: Message):
    if not is_admin(message.from_user.id):
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем ID категории "Футболки"
    cursor.execute("SELECT id FROM categories WHERE name = 'Футболки'")
    tshirts_id_row = cursor.fetchone()

    if not tshirts_id_row:
        await message.answer("Категория 'Футболки' не найдена")
        return

    tshirts_id = tshirts_id_row[0]

    # Получаем все товары в категории "Футболки" с их размерами
    cursor.execute("""
                   SELECT p.id    AS product_id,
                          p.name  AS product_name,
                          s.id    AS size_id,
                          s.value AS size_value,
                          ps.quantity
                   FROM products p
                            JOIN products ps ON p.id = ps.product_id
                            JOIN sizes s ON ps.size_id = s.id
                   WHERE p.category_id = ?
                   ORDER BY p.id, s.value
                   """, (tshirts_id,))

    products = {}
    for row in cursor.fetchall():
        product_id = row[0]
        product_name = row[1]
        size_id = row[2]
        size_value = row[3]
        quantity = row[4]

        if product_id not in products:
            products[product_id] = {
                'name': product_name,
                'sizes': []
            }

        products[product_id]['sizes'].append({
            'id': size_id,
            'value': size_value,
            'quantity': quantity
        })

    # Формируем ответ
    response = f"🗂 Категория 'Футболки' (ID: {tshirts_id})\n\n"
    response += f"🔢 Всего товаров: {len(products)}\n\n"

    for product_id, data in products.items():
        response += f"🆔 Товар ID: {product_id}\n"
        response += f"📝 Название: {data['name']}\n"
        response += "📏 Размеры:\n"

        for size in data['sizes']:
            response += f"  • {size['value']} (ID: {size['id']}): {size['quantity']} шт.\n"

    # Если сообщение слишком длинное, разбиваем на части
    max_length = 4000
    if len(response) > max_length:
        parts = [response[i:i + max_length] for i in range(0, len(response), max_length)]
        for part in parts:
            await message.answer(part)
            await asyncio.sleep(0.5)  # Задержка между сообщениями
    else:
        await message.answer(response)

    conn.close()


# ADMIN Проверьте наличие товаров в базе данных:
# Временная команда для проверки товаров
@dp.message(Command("check_products"))
async def cmd_check_products(message: Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, name, category_id, size_id, quantity FROM products")
    products = cursor.fetchall()

    response = "📦 Товары в базе:\n\n"
    for p in products:
        response += f"ID: {p[0]}, {p[1]}, Cat: {p[2]}, Size: {p[3]}, Qty: {p[4]}\n"

    max_length = 4000
    if len(response) > max_length:
        parts = [response[i:i + max_length] for i in range(0, len(response), max_length)]
        for part in parts:
            await message.answer(part)
            await asyncio.sleep(0.5)  # Задержка между сообщениями
    else:
        await message.answer(response)
    await message.answer(response)
    conn.close()


# ADMIN Просмотр всех товаров
@dp.callback_query(F.data == "admin_products")
async def admin_view_products(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, image_url FROM products")
    products = cursor.fetchall()
    conn.close()

    if not products:
        await callback.message.answer("ℹ️ Нет товаров в базе данных")
        await callback.answer()
        return

    response = "📦 <b>Список товаров:</b>\n\n"
    for product in products:
        product_id, name, price, image_url = product
        response += (
            f"🆔 ID: {product_id}\n"
            f"📝 Название: {name}\n"
            f"💰 Цена: {price} руб.\n"
            f"🖼 Фото: {image_url}\n"
            "═══════════════════\n"
        )
    max_length = 4096
    if len(response) > max_length:
        parts = [response[i:i + max_length] for i in range(0, len(response), max_length)]
        for part in parts:
            await callback.message.answer(part)
            await asyncio.sleep(0.5)  # Задержка между сообщениями
    else:
        await callback.message.answer(response)
    conn.close()


# ADMIN Просмотр всех доступных команд
@dp.callback_query(F.data == "admin_commands")
async def admin_commands(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return

    commands = (
        "<b>📋 Доступные команды:</b>\n\n"
        "• /admin - Панель администратора\n"
        "• /add_product - Добавить новый товар\n"
        "• /update_quantity - Обновить количество товара\n\n"
        "⚙️ <i>Для управления используйте панель администратора</i>"
    )

    await callback.message.answer(commands, parse_mode=ParseMode.HTML)
    await callback.answer()


# ADMIN Добавление количества товара
@dp.message(Command("update_quantity"))
async def cmd_update_quantity(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    # Формат команды: /update_quantity product_id size_id new_quantity
    try:
        _, product_id, size_id, new_quantity = message.text.split()
        product_id = int(product_id)
        size_id = int(size_id)
        new_quantity = int(new_quantity)
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды\n\n"
            "Используйте:\n"
            "<code>/update_quantity product_id size_id new_quantity</code>\n\n"
            "Пример:\n"
            "<code>/update_quantity 123 5 10</code>"
        )
        return

    success = update_product_quantity(product_id, size_id, new_quantity)

    if success:
        await message.answer(f"✅ Количество товара {product_id} (размер {size_id}) обновлено: {new_quantity} шт.")
    else:
        await message.answer("❌ Не удалось обновить количество. Проверьте ID товара и размера.")


# ADMIN Просмотр заказов
@dp.callback_query(F.data == "admin_orders")
async def admin_view_orders(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем заказы с информацией о пользователе
    cursor.execute("""
                   SELECT o.id,
                          COALESCE(u.username, 'Без username') AS username,
                          o.total_amount,
                          o.created_at,
                          o.status
                   FROM orders o
                            LEFT JOIN users u ON o.user_id = u.id
                   ORDER BY o.created_at DESC
                   """)
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        await callback.message.answer("ℹ️ Нет заказов в базе данных")
        await callback.answer()
        return

    response = "📊 <b>Список заказов:</b>\n\n"
    for order in orders:
        order_id, username, total_amount, created_at, status = order
        status_icon = "✅" if status == "confirmed" else "❌" if status == "cancelled" else "🕒"
        response += (
            f"{status_icon} Заказ: <b>#{order_id}</b>\n"
            f"👤 Клиент: {username}\n"
            f"💰 Сумма: {total_amount} ₽\n"
            f"🕒 Дата: {created_at}\n"
            f"🔹 Статус: {status}\n"
            "══════════════\n"
        )

    await callback.message.answer(response, parse_mode=ParseMode.HTML)
    await callback.answer()


PER_PAGE = 10  # Количество товаров на страницу


@dp.callback_query(F.data == "admin_sales")
async def admin_view_sales(callback: CallbackQuery):
    await _show_sales_page(callback, 1)


@dp.callback_query(F.data.startswith("sales_page_"))
async def handle_sales_page(callback: CallbackQuery):
    page = int(callback.data.split('_')[-1])
    await _show_sales_page(callback, page)


@dp.callback_query(F.data.startswith("sales_detail_"))
async def handle_sales_detail(callback: CallbackQuery):
    # Исправленный разбор параметров
    parts = callback.data.split('_')
    if len(parts) < 4:
        await callback.answer("Ошибка формата запроса", show_alert=True)
        return

    try:
        # Парсим параметры с учетом структуры "sales_detail_{product_id}_{size_id}_{page}"
        product_id = int(parts[2])
        size_id = int(parts[3])
        page = int(parts[4]) if len(parts) >= 5 else 1
    except (ValueError, IndexError):
        await callback.answer("Ошибка обработки запроса", show_alert=True)
        return

    await _show_sales_detail_page(callback, product_id, size_id, page)


async def _show_sales_page(callback: CallbackQuery, page: int):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем общее количество уникальных товаров с размерами
    cursor.execute("""
                   SELECT COUNT(*)
                   FROM (SELECT p.id, sp.size_id
                         FROM sold_products sp
                                  JOIN products p ON sp.product_id = p.id
                         GROUP BY p.id, sp.size_id)
                   """)
    total_items = cursor.fetchone()[0]
    total_pages = max(1, (total_items + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PER_PAGE

    # Получаем статистику продаж
    cursor.execute("""
                   SELECT p.id AS product_id,
                          p.name,
                          s.id AS size_id,
                          s.value AS size,
            SUM(sp.quantity) AS total_quantity,
            SUM(p.price * sp.quantity) AS total_revenue,
            COUNT(DISTINCT sp.user_id) AS buyers_count
                   FROM sold_products sp
                       JOIN products p
                   ON sp.product_id = p.id
                       LEFT JOIN sizes s ON sp.size_id = s.id
                   GROUP BY p.id, sp.size_id
                   ORDER BY total_quantity DESC
                       LIMIT ?
                   OFFSET ?
                   """, (PER_PAGE, offset))
    sales = cursor.fetchall()

    # Общие суммы по всем продажам
    cursor.execute("""
                   SELECT SUM(sp.quantity)           AS total_items,
                          SUM(p.price * sp.quantity) AS total_revenue,
                          COUNT(DISTINCT sp.user_id) AS total_buyers
                   FROM sold_products sp
                            JOIN products p ON sp.product_id = p.id
                   """)
    total_data = cursor.fetchone()
    conn.close()

    total_items_all = total_data[0] or 0
    total_revenue_all = total_data[1] or 0
    total_buyers = total_data[2] or 0

    # Формирование ответа
    response = (
        f"📊 <b>Общая статистика продаж (страница {page}/{total_pages})</b>\n"
        f"----------------------------------------\n\n"
    )

    if not sales:
        response += "ℹ️ Нет данных о продажах"
    else:
        for sale in sales:
            product_id, name, size_id, size, quantity, revenue, buyers_count = sale
            size_info = f" ({size})" if size else ""
            response += (
                f"📦 <b>{name}{size_info}</b>\n"
                f"├ Продано: <b>{quantity} шт.</b>\n"
                f"├ Покупателей: <b>{buyers_count}</b>\n"
                f"└ Выручка: <b>{revenue} ₽</b>\n\n"
            )

    response += (
        f"----------------------------------------\n"
        f"💳 <b>Общая выручка: {total_revenue_all} ₽</b>\n"
        f"📦 <b>Товаров продано: {total_items_all} шт.</b>\n"
        f"👥 <b>Уникальных покупателей: {total_buyers}</b>"
    )

    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    # Кнопки детализации для каждого товара
    for sale in sales:
        product_id, name, size_id, size, *_ = sale
        size_id = size_id if size_id else 0

        btn_text = f"🔍 {name}"
        if size:
            btn_text += f" ({size})"

        # Исправленный формат callback_data
        callback_data = f"sales_detail_{product_id}_{size_id}_1"

        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=btn_text[:30] + "..." if len(btn_text) > 30 else btn_text,
                callback_data=callback_data
            )
        ])

    # Кнопки пагинации
    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(
            text="⬅️ Назад", callback_data=f"sales_page_{page - 1}"
        ))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(
            text="Вперед ➡️", callback_data=f"sales_page_{page + 1}"
        ))

    if pagination_row:
        keyboard.inline_keyboard.append(pagination_row)

    # Обновление сообщения
    if page == 1:
        await callback.message.answer(response, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await callback.message.edit_text(response, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    await callback.answer()


async def _show_sales_detail_page(callback: CallbackQuery, product_id: int, size_id: int, page: int):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Получаем информацию о товаре
    cursor.execute("""
                   SELECT p.name, COALESCE(s.value, 'Без размера')
                   FROM products p
                            LEFT JOIN sizes s ON s.id = ?
                   WHERE p.id = ?
                   """, (size_id if size_id != 0 else None, product_id))
    product_info = cursor.fetchone()
    product_name = product_info[0]
    size_name = product_info[1]

    # Считаем общее количество записей
    cursor.execute("""
                   SELECT COUNT(*)
                   FROM sold_products
                   WHERE product_id = ?
                     AND (size_id = ? OR (? IS NULL AND size_id IS NULL))
                   """, (product_id, size_id if size_id != 0 else None, size_id if size_id != 0 else None))
    total_items = cursor.fetchone()[0]
    total_pages = max(1, (total_items + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PER_PAGE

    # Получаем детализацию продаж
    cursor.execute("""
                   SELECT u.username,
                          sp.quantity,
                          (p.price * sp.quantity)                AS amount,
                          strftime('%d.%m.%Y %H:%M', sp.sold_at) AS sold_date
                   FROM sold_products sp
                            JOIN users u ON sp.user_id = u.id
                            JOIN products p ON sp.product_id = p.id
                   WHERE sp.product_id = ?
                     AND (sp.size_id = ? OR (? IS NULL AND sp.size_id IS NULL))
                   ORDER BY sp.sold_at DESC LIMIT ?
                   OFFSET ?
                   """, (
                       product_id,
                       size_id if size_id != 0 else None,
                       size_id if size_id != 0 else None,
                       PER_PAGE,
                       offset
                   ))
    details = cursor.fetchall()
    conn.close()

    # Формирование ответа
    size_info = f" ({size_name})" if size_name != 'Без размера' else ""
    response = (
        f"🔍 <b>Детализация по товару:</b> {product_name}{size_info}\n"
        f"📅 <b>Продажи (страница {page}/{total_pages}):</b>\n\n"
    )

    if not details:
        response += "ℹ️ Нет данных о продажах этого товара\n"
    else:
        for detail in details:
            username,quantity, amount, sold_date = detail
            user_info = f"@{username}"
            response += (
                f"👤 <b>Покупатель:</b> {user_info}\n"
                f"├ Дата: {sold_date}\n"
                f"├ Количество: {quantity} шт.\n"
                f"└ Сумма: {amount} ₽\n\n"
            )

    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])


    # Кнопки пагинации
    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(
            # Исправленный формат
            text="⬅️ Назад",
            callback_data=f"sales_detail_{product_id}_{size_id}_{page - 1}"
        ))
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(
            # Исправленный формат
            text="Вперед ➡️",
            callback_data=f"sales_detail_{product_id}_{size_id}_{page + 1}"
        ))

    # Кнопка возврата
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="↩️ К общей статистике",
            callback_data=f"sales_page_1"
        )
    ])

    await callback.message.edit_text(response, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await callback.answer()


# ======== КОРЗИНА И ЗАКАЗЫ ========


@dp.callback_query(F.data == "view_cart")
async def view_cart(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Удаляем сообщение с кнопками корзины
        try:
            await bot.delete_message(chat_id, callback.message.message_id)
        except TelegramBadRequest as e:
            if "message to delete not found" not in str(e):
                logger.error(f"Ошибка при удалении сообщения: {e}")

        # 2. Получаем содержимое корзины
        cursor.execute("""
            SELECT 
                p.name, 
                s.value, 
                ci.quantity, 
                p.price,
                p.discount_price,
                p.discount_percent,
                cat.discount_percent as category_discount_percent,
                cat.discount_end_date as category_discount_end_date
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            LEFT JOIN sizes s ON ci.size_id = s.id
            JOIN cart c ON ci.cart_id = c.id
            JOIN categories cat ON p.category_id = cat.id
            WHERE c.user_id = ?
        """, (user_id,))

        cart_items = cursor.fetchall()

        if not cart_items:
            await callback.message.answer("📎 Твоя корзина пуста")
            return

        # 3. Формируем сообщение с содержимым корзины
        total = 0
        total_items = 0
        message = "📎 <b>Твоя корзина:</b>\n\n"

        for i, item in enumerate(cart_items, 1):
            name, size, quantity, price, discount_price, discount_percent, category_discount_percent, category_discount_end_date = item

            # Рассчитываем актуальную цену
            actual_price = calculate_actual_price(
                price,
                discount_price,
                discount_percent,
                category_discount_percent,
                category_discount_end_date
            )

            item_total = actual_price * quantity
            total += item_total
            total_items += quantity

            size_info = f" (размер: {size})" if size else ""
            message += f"{i}. {name}{size_info}\n"
            message += f"   Кол-во: {quantity} × {format_price(actual_price)} = {format_price(item_total)}\n\n"

        message += f" <b>Итого товаров:</b> {total_items} шт.\n"
        message += f" <b>Общая сумма:</b> {format_price(total)}\n\n"
        message += "Выберите действие:"

        # 4. Создаем клавиатуру для корзины
        cart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Оформить заказ", callback_data="checkout")],
            [InlineKeyboardButton(text="❌ Очистить корзину", callback_data="clear_cart")],
            [InlineKeyboardButton(text="← Продолжить покупки", callback_data="back_to_categories")]
        ])

        # 5. Отправляем новое сообщение с корзиной
        await callback.message.answer(
            message,
            reply_markup=cart_keyboard,
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Ошибка в view_cart: {e}")
        await callback.answer(f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()


# Обработчик очистки корзины
@dp.callback_query(lambda c: c.data == 'clear_cart')
async def handle_clear_cart(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Находим корзину пользователя
    cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
    cart = cursor.fetchone()

    if cart:
        cart_id = cart[0]
        # Удаляем все товары из корзины
        cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
        conn.commit()

    conn.close()

    await callback.answer("Корзина очищена!", show_alert=True)
    await callback.message.delete()

    # Показываем обновленную корзину
    msg = await callback.message.answer("🛒 Твоя корзина пуста", reply_markup=main_menu())
    last_messages[user_id] = msg.message_id


from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler


async def handle_order_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Парсим данные из callback
    action, order_id = query.data.split('_')[0], int(query.data.split('_')[-1])
    admin = query.from_user
    admin_username = f"@{admin.username}" if admin.username else f"ID:{admin.id}"
    action_time = datetime.now().strftime('%d.%m.%Y | %H:%M')

    # Получаем данные заказа из БД
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
                   SELECT group_chat_id, group_message_id
                   FROM orders
                   WHERE id = ?
                   """, (order_id,))
    order_data = cursor.fetchone()

    if not order_data:
        await query.edit_message_text("⚠️ Ошибка: заказ не найден в базе")
        return

    group_chat_id, group_message_id = order_data
    conn.close()

    # Формируем новый текст сообщения по вашему образцу
    if action == "confirm":
        status_header = "ЗАКАЗ ПОДТВЕРЖДЕН"
        status_line = "Статус: ПОДТВЕРЖДЕН"
    else:
        status_header = "ЗАКАЗ ОТМЕНЕН"
        status_line = "Статус: ОТМЕНЕН"

    # Получаем текущее сообщение в группе
    try:
        group_message = await context.bot.get_message(
            chat_id=group_chat_id,
            message_id=group_message_id
        )
        original_text = group_message.text

        # Убираем HTML теги из оригинального текста
        clean_text = html.unescape(original_text)

        # Находим позицию первого переноса строки после заголовка
        header_end = clean_text.find("\n", clean_text.find("ЗАКАЗ"))

        # Формируем новый текст по вашему образцу
        new_text = (
            f"Stone’s Order\n"
            f"✔ {status_header} | #{order_id}\n"
            f"{clean_text[header_end + 1:]}\n\n"
            f"Заказ подтвердил администратор {admin_username}\n"
            f"{status_line}\n"
            f"Время: {action_time}"
        )

        # Редактируем сообщение в группе
        await context.bot.edit_message_text(
            chat_id=group_chat_id,
            message_id=group_message_id,
            text=new_text,
            reply_markup=None  # Убираем кнопки
        )
        logger.info(f"Заказ #{order_id} обновлен в группе. Действие: {action}")

    except Exception as e:
        logger.error(f"Ошибка обновления сообщения: {str(e)}")
        await query.edit_message_text(f"⚠️ Ошибка обновления заказа: {str(e)}")
        return

    # Обновляем сообщение у админа (в личке)
    await query.edit_message_text(
        text=f"{query.message.text}\n\n✅ Вы успешно {status_line.lower()} заказ #{order_id}",
        parse_mode=ParseMode.HTML
    )


# Функция обновления сообщений
async def update_order_messages(order_id: int, status: str, admin_username: str):
    """
    Обновляет все сообщения о заказе (админы и группа) при подтверждении/отмене.
    Убирает кнопки и добавляет статус.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем информацию о заказе
        cursor.execute("""
            SELECT user_id, user_name, total_amount
            FROM orders 
            WHERE id = ?
        """, (order_id,))
        order_data = cursor.fetchone()

        if not order_data:
            logger.error(f"Заказ #{order_id} не найден для обновления")
            return

        user_id, user_name, total_amount = order_data

        # Текст для подтвержденного заказа
        if status == "confirmed":
            status_text = f"✅ <b>ЗАКАЗ ПОДТВЕРЖДЕН | #{order_id}</b>\n\n"
            action_text = f"Администратор @{admin_username} подтвердил заказ #{order_id}\n"
            status_emoji = "✅"
        elif status == "cancelled":
            status_text = f"❌ <b>ЗАКАЗ ОТМЕНЕН | #{order_id}</b>\n\n"
            action_text = f"Администратор @{admin_username} отменил заказ #{order_id}\n"
            status_emoji = "❌"
        else:
            logger.error(f"Неизвестный статус для обновления: {status}")
            return

        # Получаем информацию о товарах в заказе
        cursor.execute("""
            SELECT oi.quantity, p.name, p.sku, oi.price, s.value as size
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            LEFT JOIN sizes s ON oi.size_id = s.id
            WHERE oi.order_id = ?
        """, (order_id,))
        items = cursor.fetchall()

        # Формируем обновленный текст
        updated_text = status_text
        updated_text += f"<b>👤 КЛИЕНТ</b>\n"
        updated_text += f"• Пользователь: <code>{user_name}</code>\n"
        updated_text += f"• ID: <code>{user_id}</code>\n\n"

        updated_text += f"<b>📦 СОСТАВ ЗАКАЗА</b>\n"
        total_quantity = 0

        for i, item in enumerate(items, 1):
            quantity, name, sku, price, size = item
            size_name = size if size else "без размера"
            item_total = quantity * price
            total_quantity += quantity

            updated_text += (
                f"{i}. <b>{name}</b>\n"
                f"   • Размер: {size_name}\n"
                f"   • Артикул: <code>{sku}</code>\n"
                f"   • Кол-во: {quantity} шт.\n"
                f"   • Цена: {int(price)} ₽\n"
                f"   • Сумма: {int(item_total)} ₽\n\n"
            )

        updated_text += (
            f"<b>💸 ИТОГО</b>\n"
            f"• Общее кол-во: {total_quantity} шт.\n"
            f"• Сумма заказа: {int(total_amount)} ₽\n\n"
            f"<b>{status_emoji} СТАТУС: {action_text}</b>"
        )

        conn.close()

        # Обновляем сообщения у всех админов (группу не трогаем - там только уведомления)
        # Для этого нужно хранить message_id заказов для каждого админа
        # Пока просто логируем, что нужно обновить
        logger.info(f"Заказ #{order_id} обновлен: {status} администратором @{admin_username}")

        # Можно реализовать механизм обновления конкретных сообщений через БД,
        # если хранить chat_id и message_id для каждого уведомления о заказе

    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщений заказа #{order_id}: {e}")


# Функция уведомления администратора и группы
import html

import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import logging

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# def calculate_actual_price(price: float, discount_price: float = None, discount_percent: float = None) -> tuple:
#     """
#     Рассчитывает актуальную цену с учетом всех скидок.
#     Возвращает кортеж: (актуальная_цена, применяемая_скидка_в_процентах)
#     """
#     try:
#         price = float(price)
#
#         # Инициализируем цены с разными типами скидок
#         price_with_percent = price
#         price_with_fixed = price
#
#         # Рассчитываем цену с процентной скидкой
#         if discount_percent and float(discount_percent) > 0:
#             discount_percent_val = float(discount_percent)
#             price_with_percent = price * (1 - discount_percent_val / 100)
#
#         # Рассчитываем цену с фиксированной скидкой
#         if discount_price and float(discount_price) > 0:
#             discount_price_val = float(discount_price)
#             if discount_price_val < price:
#                 price_with_fixed = discount_price_val
#
#         # Выбираем минимальную цену
#         actual_price = min(price_with_percent, price_with_fixed)
#
#         # Рассчитываем фактический процент скидки
#         if actual_price < price:
#             actual_discount_percent = int((1 - actual_price / price) * 100)
#         else:
#             actual_discount_percent = 0
#
#         return round(actual_price, 2), actual_discount_percent
#     except Exception as e:
#         logger.error(f"Ошибка расчета цены: {e}")
#         return float(price), 0


def calculate_min_price(price, discount_price=None, discount_percent=None):
    """
    Рассчитывает минимальную цену из обычной цены, цены со скидкой и цены с процентной скидкой.
    Возвращает кортеж: (минимальная_цена, фактический_процент_скидки)
    """
    try:
        price_val = float(price)
        min_price = price_val
        actual_discount = 0

        # Рассчитываем цену с процентной скидкой
        if discount_percent is not None:
            try:
                discount_percent_val = float(discount_percent)
                if discount_percent_val > 0:
                    price_with_percent = price_val * (1 - discount_percent_val / 100)
                    if price_with_percent < min_price:
                        min_price = price_with_percent
                        actual_discount = discount_percent_val
            except (ValueError, TypeError):
                pass

        # Проверяем фиксированную скидку
        if discount_price is not None:
            try:
                discount_price_val = float(discount_price)
                if 0 < discount_price_val < min_price:
                    min_price = discount_price_val
                    # Пересчитываем фактический процент скидки
                    if price_val > 0:
                        actual_discount = int((1 - min_price / price_val) * 100)
            except (ValueError, TypeError):
                pass

        return round(min_price, 2), actual_discount
    except Exception as e:
        logger.error(f"Ошибка расчета минимальной цены: {e}")
        return float(price), 0


async def notify_order(
        user: types.User,
        cart_items: list,
        total_amount: int,
        order_id: int,
        cursor=None
):
    conn = None
    try:
        if cursor is None:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

        current_time = datetime.now().strftime('%d.%m.%Y | %H:%M')

        logger.debug(f"Уведомление о заказе #{order_id}")
        logger.debug(f"Пользователь: @{user.username}, ID: {user.id}")

        # ================== ОБЩИЙ ШАБЛОН УВЕДОМЛЕНИЯ ==================
        common_text = (
            f"<b>🌟 НОВЫЙ ЗАКАЗ | #{order_id}</b>\n\n"
            f"<b>👤 КЛИЕНТ</b>\n"
            f"• Пользователь: @{html.escape(str(user.username) if user.username else 'нет username')}\n"
            f"• ID: <code>{user.id}</code>\n"
            f"• Время заказа: <code>{current_time}</code>\n\n"
            f"<b>📦 СОСТАВ ЗАКАЗА</b>\n"
        )

        total_quantity = 0
        recalculated_total = 0

        for i, item in enumerate(cart_items, 1):
            # Структура item: (product_id, size_id, quantity, name, sku, price, discount_price, discount_percent)
            product_id, size_id, quantity, name, sku, price, discount_price, discount_percent = item

            # Рассчитываем минимальную цену с учетом всех скидок
            actual_price, actual_discount = calculate_min_price(price, discount_price, discount_percent)

            # Приводим типы к int
            try:
                quantity = int(quantity)
                price_val = float(price)
                actual_price = float(actual_price)
            except (ValueError, TypeError) as e:
                logger.error(f"Ошибка преобразования типов для товара {product_id}: {e}")
                continue

            # Получаем название размера
            size_name = "без размера"
            if size_id and size_id != 0:
                cursor.execute("SELECT value FROM sizes WHERE id = ?", (size_id,))
                size_data = cursor.fetchone()
                if size_data and size_data[0]:
                    size_name = size_data[0]

            item_total = quantity * actual_price
            total_quantity += quantity
            recalculated_total += item_total

            # Формируем строку с ценой
            price_display = f"{int(actual_price)} ₽"
            price_note = ""

            if actual_discount > 0:
                price_note = f" (скидка {int(actual_discount)}% от {int(price_val)} ₽)"

            common_text += (
                f"{i}. <b>{name}</b>\n"
                f"   • Размер: {size_name}\n"
                f"   • Артикул: <code>{sku}</code>\n"
                f"   • Кол-во: {quantity} шт.\n"
                f"   • Цена: {price_display}{price_note}\n"
                f"   • Сумма: {int(item_total)} ₽\n\n"
            )

        # Проверяем расчеты
        if recalculated_total != total_amount:
            logger.warning(f"Расчет не совпадает: recalculated_total={recalculated_total}, total_amount={total_amount}")
            total_amount = recalculated_total

        # Итог
        common_text += (
            f"<b>💸 ИТОГО</b>\n"
            f"• Общее кол-во: {total_quantity} шт.\n"
            f"• <b>Итого к оплате: {int(total_amount)} ₽</b>\n\n"
            f"<i>⚠️ Не забудьте связаться с клиентом!</i>"
        )

        # Клавиатура для управления заказом
        order_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"confirm_order_{order_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_order_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📞 Связаться с клиентом",
                    url=f"tg://user?id={user.id}"
                )
            ]
        ])

        logger.debug(f"Текст уведомления сформирован, total_quantity={total_quantity}, total_amount={total_amount}")

        # Отправляем уведомление всем администраторам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=common_text,
                    reply_markup=order_keyboard,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Уведомление отправлено админу {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")

        # Отправляем в группу, если указана
        if GROUP_CHAT_ID:
            try:
                await bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=common_text,
                    reply_markup=order_keyboard,
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Уведомление отправлено в группу {GROUP_CHAT_ID}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления в группу: {e}")

    except Exception as e:
        logger.error(f"Ошибка в функции notify_order: {e}", exc_info=True)
        raise
    finally:
        if conn and cursor is None:
            conn.close()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Включаем доступ по имени
    return conn


def check_product_availability(product_id: int, size_id: int = None) -> int:
    """
    Проверяет доступное количество товара
    Возвращает количество в наличии
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()

        # Для товаров с размером
        if size_id and size_id > 0:
            cursor.execute("""
                           SELECT quantity
                           FROM products
                           WHERE id = ?
                             AND size_id = ?
                           """, (product_id, size_id))
        # Для товаров без размера (аксессуары)
        else:
            cursor.execute("""
                           SELECT quantity
                           FROM products
                           WHERE id = ?
                             AND size_id IS NULL
                           """, (product_id,))

        result = cursor.fetchone()
        return result[0] if result else 0
    except sqlite3.Error as e:
        logger.error(f"Ошибка проверки наличия: {e}")
        return 0
    finally:
        conn.close()

# Обработчик оформления заказа
# Обработчик оформления заказа
@dp.callback_query(lambda c: c.data == 'checkout')
async def process_checkout(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_name = callback.from_user.username or f"{callback.from_user.first_name} {callback.from_user.last_name}".strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Получаем корзину пользователя
        cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
        cart_data = cursor.fetchone()
        if not cart_data:
            await callback.answer("❌ Корзина не найдена!", show_alert=True)
            return

        cart_id = cart_data[0]

        # 2. Получаем товары в корзине с ценами и скидками
        cursor.execute("""
            SELECT 
                ci.id,
                ci.product_id,
                ci.size_id,
                ci.quantity,
                p.name,
                p.sku,
                p.price,
                p.discount_price,
                p.discount_percent
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.cart_id = ?
        """, (cart_id,))

        cart_items = cursor.fetchall()

        if not cart_items:
            await callback.answer("Ваша корзина пуста!", show_alert=True)
            return

        # 3. Проверка доступности товаров
        for item in cart_items:
            item_id, product_id, size_id, quantity, name, sku, price, discount_price, discount_percent = item

            # Проверяем доступность
            available = check_product_availability(product_id, size_id)

            if quantity > available:
                # Удаляем недоступный товар из корзины
                cursor.execute("DELETE FROM cart_items WHERE id = ?", (item_id,))
                conn.commit()

                await callback.answer(
                    f"❌ Недостаточно товара: {name}\n"
                    f"Запрошено: {quantity} шт., доступно: {available} шт.\n"
                    "Товар удален из корзины.",
                    show_alert=True
                )
                # Обновляем корзину
                await show_cart(callback.message)
                return

        # 4. Создание заказа (используем минимальную цену с учетом всех скидок)
        total = 0
        order_items_with_prices = []
        cart_items_data = []  # Для хранения данных о товарах с рассчитанными ценами

        for item in cart_items:
            item_id, product_id, size_id, quantity, name, sku, price, discount_price, discount_percent = item
            actual_price, actual_discount = calculate_min_price(price, discount_price, discount_percent)
            item_total = actual_price * quantity
            total += item_total

            order_items_with_prices.append((product_id, size_id, quantity, actual_price))
            cart_items_data.append({
                'id': item_id,
                'product_id': product_id,
                'size_id': size_id,
                'quantity': quantity,
                'name': name,
                'sku': sku,
                'price': float(price),
                'discount_price': float(discount_price) if discount_price else None,
                'discount_percent': float(discount_percent) if discount_percent else None,
                'actual_price': actual_price,
                'actual_discount': actual_discount,
                'item_total': item_total
            })

        cursor.execute("""
            INSERT INTO orders (user_id, user_name, total_amount, status)
            VALUES (?, ?, ?, 'pending')
        """, (user_id, user_name, total))
        order_id = cursor.lastrowid

        # 5. Добавление позиций заказа (сохраняем актуальную цену)
        for item_data in order_items_with_prices:
            product_id, size_id, quantity, actual_price = item_data
            cursor.execute("""
                INSERT INTO order_items (order_id, product_id, size_id, quantity, price)
                VALUES (?, ?, ?, ?, ?)
            """, (order_id, product_id, size_id, quantity, actual_price))

        # 6. Формирование чека для клиента
        receipt_text = f"📎 <b>Твой заказ: №{order_id}</b>\n\n"
        total_items = 0
        total_amount = 0

        for i, item_data in enumerate(cart_items_data, 1):
            actual_price = item_data['actual_price']
            actual_discount = item_data['actual_discount']
            quantity = item_data['quantity']
            name = item_data['name']
            item_total = item_data['item_total']

            size_name = "без размера"
            if item_data['size_id']:
                cursor.execute("SELECT value FROM sizes WHERE id = ?", (item_data['size_id'],))
                size_data = cursor.fetchone()
                size_name = size_data[0] if size_data else "неизвестный размер"

            total_items += quantity
            total_amount += item_total

            # Форматируем цену для отображения
            price_display = f"{int(actual_price)} ₽"
            if actual_discount > 0:
                price_display = f"{int(actual_price)} ₽ (скидка {int(actual_discount)}%)"

            receipt_text += (
                f"{i}. {name} (размер: {size_name})\n"
                f"   Кол-во: {quantity} × {price_display} = {int(item_total)}₽\n\n"
            )

        receipt_text += (
            f"🔹 Итого товаров: {total_items} шт.\n"
            f"🔹 Общая сумма: {int(total_amount)} ₽\n"
            f"🔹 Номер заказа: <b>#{order_id}</b>\n\n"
            "🔹 Заказ оформлен! Скоро с тобой свяжутся для подтверждения и оплаты."
        )

        # 7. Очистка корзины
        cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
        conn.commit()

        # 8. Отправка результата клиенту
        await callback.message.edit_text(
            receipt_text,
            parse_mode=ParseMode.HTML
        )

        # 9. Уведомление администраторов с правильными данными
        # Подготавливаем данные для уведомления
        cart_items_for_notify = []
        for item_data in cart_items_data:
            cart_items_for_notify.append((
                item_data['product_id'],
                item_data['size_id'],
                item_data['quantity'],
                item_data['name'],
                item_data['sku'],
                item_data['price'],
                item_data['discount_price'],
                item_data['discount_percent']
            ))

        await notify_order(
            user=callback.from_user,
            cart_items=cart_items_for_notify,
            total_amount=total_amount,
            order_id=order_id,
            cursor=cursor
        )

    except sqlite3.Error as e:
        logger.error(f"SQL error: {e}")
        conn.rollback()
        await callback.answer("⚠️ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
    finally:
        conn.close()
# @dp.callback_query(F.data == 'checkout')
# async def process_checkout(callback: types.CallbackQuery, state: FSMContext):
#     user_id = callback.from_user.id
#     chat_id = callback.message.chat.id
#
#     # Получаем данные пользователя для чека
#     conn = get_db_connection()
#     cursor = conn.cursor()
#
#     try:
#         # Получаем корзину пользователя
#         cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
#         cart_data = cursor.fetchone()
#
#         if not cart_data:
#             await callback.answer("❌ Корзина пуста!", show_alert=True)
#             return
#
#         cart_id = cart_data[0]
#
#         # Получаем товары в корзине
#         cursor.execute("""
#             SELECT
#                 ci.product_id,
#                 ci.size_id,
#                 ci.quantity,
#                 p.price,
#                 p.name,
#                 p.discount_price,
#                 p.discount_percent,
#                 cat.discount_percent as category_discount_percent,
#                 cat.discount_end_date as category_discount_end_date
#             FROM cart_items ci
#             JOIN products p ON ci.product_id = p.id
#             JOIN categories cat ON p.category_id = cat.id
#             WHERE ci.cart_id = ?
#         """, (cart_id,))
#
#         cart_items = cursor.fetchall()
#
#         if not cart_items:
#             await callback.answer("Ваша корзина пуста!", show_alert=True)
#             return
#
#         # Рассчитываем итоговую сумму
#         total_amount = 0
#         for item in cart_items:
#             product_id, size_id, quantity, price, name, discount_price, discount_percent, category_discount_percent, category_discount_end_date = item
#
#             actual_price = calculate_actual_price(
#                 price,
#                 discount_price,
#                 discount_percent,
#                 category_discount_percent,
#                 category_discount_end_date
#             )
#
#             item_total = actual_price * quantity
#             total_amount += item_total
#
#         # Создаем заказ в БД
#         cursor.execute("""
#             INSERT INTO orders (user_id, total_amount, status, created_at)
#             VALUES (?, ?, 'pending', CURRENT_TIMESTAMP)
#         """, (user_id, total_amount))
#
#         order_id = cursor.lastrowid
#
#         # Сохраняем товары заказа
#         for item in cart_items:
#             product_id, size_id, quantity, price, name = item
#             cursor.execute("""
#                 INSERT INTO order_items (order_id, product_id, size_id, quantity, price)
#                 VALUES (?, ?, ?, ?, ?)
#             """, (order_id, product_id, size_id, quantity, price))
#
#         # Создаем платеж в ЮKassa
#         payment_data = await payment_system.create_payment(
#             order_id=order_id,
#             amount=total_amount,
#             user_id=user_id,
#             description=f"Заказ #{order_id} в магазине Stone",
#             email=None,  # Можно запросить у пользователя
#             phone=None  # Можно запросить у пользователя
#         )
#
#         if not payment_data["success"]:
#             await callback.answer("❌ Ошибка создания платежа", show_alert=True)
#             return
#
#         # Генерируем QR-код
#         if payment_data.get("qr_url"):
#             qr_path = await payment_system.generate_qr_code(
#                 payment_data["qr_url"],
#                 payment_data["payment_id"]
#             )
#         else:
#             qr_path = None
#
#         # Формируем сообщение с инструкцией
#         payment_message = f"""
# 💳 <b>ОПЛАТА ЗАКАЗА #{order_id}</b>
#
# 💰 Сумма к оплате: <b>{total_amount} ₽</b>
#
# 📱 <b>СПОСОБЫ ОПЛАТЫ:</b>
#
# 1. <b>По QR-коду</b> (👇 ниже)
#    • Откройте приложение вашего банка
#    • Нажмите "Оплатить по QR-коду"
#    • Наведите камеру на код
#
# 2. <b>По ссылке</b>
#    [Нажмите здесь для оплаты]({payment_data.get('confirmation_url', '#')})
#
# ⏱ Ссылка и QR-код действительны <b>15 минут</b>
# 🔄 После оплаты статус обновится автоматически
#
# <i>Номер платежа: {payment_data['payment_id']}</i>
# """
#
#         # Отправляем сообщение с QR-кодом
#         if qr_path and os.path.exists(qr_path):
#             # Отправляем фото с QR-кодом
#             photo = FSInputFile(qr_path)
#             await bot.send_photo(
#                 chat_id=chat_id,
#                 photo=photo,
#                 caption=payment_message,
#                 parse_mode=ParseMode.HTML
#             )
#         else:
#             # Отправляем только текст со ссылкой
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text=payment_message,
#                 parse_mode=ParseMode.HTML,
#                 disable_web_page_preview=True
#             )
#
#         # Обновляем заказ данными о платеже
#         cursor.execute("""
#             UPDATE orders
#             SET payment_id = ?, payment_status = ?
#             WHERE id = ?
#         """, (payment_data['payment_id'], payment_data['status'], order_id))
#
#         # Очищаем корзину
#         cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
#
#         conn.commit()
#
#         # Запускаем отслеживание статуса платежа
#         asyncio.create_task(
#             track_payment_status(
#                 payment_id=payment_data['payment_id'],
#                 order_id=order_id,
#                 user_id=user_id,
#                 chat_id=chat_id
#             )
#         )
#
#         await callback.answer()
#
#     except Exception as e:
#         logger.error(f"Ошибка при оформлении заказа: {e}")
#         await callback.answer("❌ Произошла ошибка при оформлении заказа", show_alert=True)
#     finally:
#         conn.close()
#
#
# async def track_payment_status(payment_id: str, order_id: int, user_id: int, chat_id: int):
#     """
#     Отслеживает статус платежа и уведомляет пользователя
#     """
#     max_checks = 30  # Максимум 30 проверок (15 минут)
#     check_interval = 30  # Проверять каждые 30 секунд
#
#     for check in range(max_checks):
#         try:
#             # Проверяем статус платежа
#             payment_status = await payment_system.check_payment_status(payment_id)
#
#             if payment_status["success"]:
#                 status = payment_status["status"]
#
#                 if status == "succeeded":
#                     # Платеж успешен
#                     await notify_payment_success(
#                         user_id=user_id,
#                         chat_id=chat_id,
#                         order_id=order_id,
#                         payment_id=payment_id,
#                         amount=payment_status["amount"]
#                     )
#                     break
#
#                 elif status in ["canceled", "failed"]:
#                     # Платеж отменен или не прошел
#                     await notify_payment_failed(
#                         user_id=user_id,
#                         chat_id=chat_id,
#                         order_id=order_id,
#                         payment_id=payment_id
#                     )
#                     break
#
#             # Ждем перед следующей проверкой
#             await asyncio.sleep(check_interval)
#
#         except Exception as e:
#             logger.error(f"Ошибка отслеживания платежа {payment_id}: {e}")
#             await asyncio.sleep(check_interval)
#
#     else:
#         # Если платеж не прошел за отведенное время
#         await notify_payment_timeout(user_id, chat_id, order_id, payment_id)
#
#
# async def notify_payment_success(user_id: int, chat_id: int, order_id: int, payment_id: str, amount: float):
#     """
#     Уведомляет об успешной оплате
#     """
#     try:
#         # Обновляем статус заказа
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#         cursor.execute("""
#             UPDATE orders
#             SET payment_status = 'paid', status = 'confirmed'
#             WHERE id = ?
#         """, (order_id,))
#         conn.commit()
#         conn.close()
#
#         # Отправляем уведомление пользователю
#         success_message = f"""
# ✅ <b>ОПЛАТА ПРОШЛА УСПЕШНО!</b>
#
# 🎉 Заказ #{order_id} подтвержден
# 💰 Сумма: {amount} ₽
# 📝 Номер платежа: {payment_id}
#
# ❤️ <b>Огромное спасибо за ваш заказ!</b>
#
# Мы искренне благодарны, что выбрали наш магазин.
# С любовью, ваша команда Stone 😊
#
# P.S. Ждем вас снова! У нас всегда есть что-то особенное для вас!
# """
#
#         await bot.send_message(
#             chat_id=chat_id,
#             text=success_message,
#             parse_mode=ParseMode.HTML
#         )
#
#         # Уведомляем администраторов
#         await notify_order_success_to_admins(order_id, user_id, amount)
#
#     except Exception as e:
#         logger.error(f"Ошибка уведомления об успешной оплате: {e}")
#
#
# async def notify_payment_failed(user_id: int, chat_id: int, order_id: int, payment_id: str):
#     """
#     Уведомляет о неудачной оплате
#     """
#     try:
#         # Обновляем статус заказа
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#         cursor.execute("""
#             UPDATE orders
#             SET payment_status = 'failed'
#             WHERE id = ?
#         """, (order_id,))
#         conn.commit()
#         conn.close()
#
#         # Отправляем уведомление пользователю
#         failed_message = f"""
# ❌ <b>ПЛАТЕЖ НЕ ПРОШЕЛ</b>
#
# Заказ #{order_id} не был оплачен.
# Пожалуйста, попробуйте еще раз или выберите другой способ оплаты.
#
# Если это ошибка, свяжитесь с поддержкой: @StoneZakhar
# """
#
#         await bot.send_message(
#             chat_id=chat_id,
#             text=failed_message,
#             parse_mode=ParseMode.HTML
#         )
#
#     except Exception as e:
#         logger.error(f"Ошибка уведомления о неудачной оплате: {e}")
#
#
# async def yookassa_webhook_handler(request):
#     """
#     Обработчик вебхуков от ЮKassa
#     """
#     try:
#         # Получаем данные от ЮKassa
#         data = await request.json()
#
#         # Проверяем подпись (если настроено)
#         # ...
#
#         # Обрабатываем уведомление
#         event = data.get('event')
#         payment_id = data.get('object', {}).get('id')
#
#         if event == "payment.waiting_for_capture":
#             # Платеж ожидает подтверждения
#             await handle_payment_capture(payment_id)
#
#         elif event == "payment.succeeded":
#             # Платеж успешно завершен
#             await handle_payment_succeeded(payment_id, data)
#
#         elif event == "payment.canceled":
#             # Платеж отменен
#             await handle_payment_canceled(payment_id)
#
#         return web.Response(text='OK', status=200)
#
#     except Exception as e:
#         logger.error(f"Ошибка обработки вебхука ЮKassa: {e}")
#         return web.Response(text='Error', status=500)
#
#
# async def setup_webhook_server():
#     """
#     Настраивает веб-сервер для вебхуков
#     """
#     app = web.Application()
#     app.router.add_post('/webhook/yookassa', yookassa_webhook_handler)
#
#     runner = web.AppRunner(app)
#     await runner.setup()
#
#     site = web.TCPSite(runner, '0.0.0.0', 3000)
#     await site.start()
#
#     logger.info("Вебхук сервер запущен на порту 3000")
#
#
# @dp.message(Command("payment_status"))
# async def cmd_payment_status(message: types.Message):
#     """
#     Проверка статуса последнего платежа
#     """
#     user_id = message.from_user.id
#
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#
#     cursor.execute("""
#         SELECT payment_id, order_id, amount, status
#         FROM payments
#         WHERE user_id = ?
#         ORDER BY created_at DESC
#         LIMIT 1
#     """, (user_id,))
#
#     payment = cursor.fetchone()
#     conn.close()
#
#     if not payment:
#         await message.answer("У вас нет активных платежей")
#         return
#
#     payment_id, order_id, amount, status = payment
#
#     # Проверяем актуальный статус
#     payment_info = await payment_system.check_payment_status(payment_id)
#
#     status_text = {
#         "pending": "⏳ Ожидает оплаты",
#         "waiting_for_capture": "⏳ Ожидает подтверждения",
#         "succeeded": "✅ Оплачен",
#         "canceled": "❌ Отменен",
#         "failed": "❌ Не удался"
#     }.get(payment_info.get('status', status), status)
#
#     response = f"""
# 📊 <b>СТАТУС ПЛАТЕЖА</b>
#
# 🆔 Номер: {payment_id}
# 📦 Заказ: #{order_id}
# 💰 Сумма: {amount} ₽
# 📈 Статус: {status_text}
#
# """
#
#     if payment_info.get('status') == 'pending':
#         response += "\n⏱ QR-код действителен еще 15 минут"
#
#     await message.answer(response, parse_mode=ParseMode.HTML)
#
#
# @dp.message(Command("cancel_payment"))
# async def cmd_cancel_payment(message: types.Message):
#     """
#     Отмена текущего платежа
#     """
#     user_id = message.from_user.id
#
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#
#     cursor.execute("""
#         SELECT payment_id
#         FROM payments
#         WHERE user_id = ? AND status = 'pending'
#         ORDER BY created_at DESC
#         LIMIT 1
#     """, (user_id,))
#
#     payment = cursor.fetchone()
#     conn.close()
#
#     if not payment:
#         await message.answer("У вас нет активных платежей для отмены")
#         return
#
#     payment_id = payment[0]
#
#     success = await payment_system.cancel_payment(payment_id)
#
#     if success:
#         await message.answer("✅ Платеж успешно отменен")
#     else:
#         await message.answer("❌ Не удалось отменить платеж")
#
#
# def get_payment_keyboard(payment_url: str):
#     """
#     Создает клавиатуру для оплаты
#     """
#     keyboard = InlineKeyboardMarkup(inline_keyboard=[
#         [
#             InlineKeyboardButton(
#                 text="💳 Оплатить онлайн",
#                 url=payment_url
#             )
#         ],
#         [
#             InlineKeyboardButton(
#                 text="📊 Проверить статус",
#                 callback_data="check_payment_status"
#             )
#         ],
#         [
#             InlineKeyboardButton(
#                 text="❌ Отменить платеж",
#                 callback_data="cancel_payment"
#             )
#         ]
#     ])
#
#     return keyboard

# Обработчик подтверждения заказа
# Глобальный словарь для временного хранения заказов (можно заменить на БД)
# Обработчик подтверждения заказа


@dp.callback_query(F.data.startswith('confirm_order_'))
async def confirm_order_handler(callback: types.CallbackQuery):
    conn = None
    try:
        order_id = int(callback.data.split('_')[-1])
        admin_username = callback.from_user.username or f"id{callback.from_user.id}"

        logger.info(f"Начало обработки подтверждения заказа #{order_id} администратором @{admin_username}")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем данные заказа
        cursor.execute("SELECT user_id, user_name, status FROM orders WHERE id = ?", (order_id,))
        order_data = cursor.fetchone()

        if not order_data:
            await callback.answer("❌ Заказ не найден", show_alert=True)
            return

        user_id, user_name, current_status = order_data

        if current_status != 'pending':
            await callback.answer(f"❌ Заказ уже был обработан (статус: {current_status})", show_alert=True)
            return

        # Получаем товары заказа из order_items
        cursor.execute("""
            SELECT oi.product_id, oi.size_id, oi.quantity, oi.price as sold_price
            FROM order_items oi
            WHERE oi.order_id = ?
        """, (order_id,))
        order_items = cursor.fetchall()

        if not order_items:
            await callback.answer("❌ Заказ пуст", show_alert=True)
            return

        # Переносим каждый товар в sold_products с полной информацией
        logger.info("Переносим товары в sold_products с полной информацией")
        for item in order_items:
            product_id, size_id, quantity, sold_price = item

            # Получаем полную информацию о товаре из products
            cursor.execute("""
                SELECT name, sku, brand, category_id, price, discount_price, 
                       quantity, image_url, discount_percent, cost_price
                FROM products 
                WHERE id = ?
            """, (product_id,))
            product_data = cursor.fetchone()

            if product_data:
                (name, sku, brand, category_id, price, discount_price,
                 prod_quantity, image_url, discount_percent, cost_price) = product_data

                # Вставляем полную копию товара в sold_products
                cursor.execute("""
                    INSERT INTO sold_products 
                    (name, sku, brand, category_id, price, discount_price, size_id, 
                     quantity, image_url, discount_percent, cost_price, order_id, user_id, sold_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, sku, brand, category_id, price, discount_price, size_id,
                      quantity, image_url, discount_percent, cost_price, order_id, user_id, sold_price))

                # Уменьшаем количество в оригинальном products
                is_null_size = size_id in (None, 0)
                if is_null_size:
                    cursor.execute("""
                        UPDATE products 
                        SET quantity = quantity - ? 
                        WHERE id = ? AND size_id IS NULL
                    """, (quantity, product_id))
                else:
                    cursor.execute("""
                        UPDATE products 
                        SET quantity = quantity - ? 
                        WHERE id = ? AND size_id = ?
                    """, (quantity, product_id, size_id))

                logger.info(f"Товар {product_id} '{name}' перенесен в sold_products")
            else:
                logger.warning(f"Товар {product_id} не найден в каталоге при подтверждении заказа #{order_id}")

        # Обновляем статус заказа
        cursor.execute("""
            UPDATE orders 
            SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (order_id,))
        conn.commit()

        # Отправляем уведомление клиенту
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 <b>Ваш заказ #{order_id} подтвержден!</b>\n\n"
                     f"❤️ <b>Огромное спасибо за ваш заказ!</b>\n\n"
                     f"Мы искренне благодарны, что выбрали наш магазин.\n\n"
                     f"Администратор @{admin_username} подтвердил ваш заказ.\n"
                     f"С любовью, ваша команда Stone 😊\n\n"
                     f"P.S. Ждем вас снова! У нас всегда есть что-то особенное для вас!",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

        # Обновляем сообщение с уведомлением о заказе
        try:
            # Получаем текущий текст сообщения
            current_text = callback.message.text

            # Добавляем информацию о подтверждении
            updated_text = current_text + f"\n\n✅ <b>Заказ подтвержден администратором @{admin_username}</b>"

            # Редактируем сообщение, убирая кнопки
            await callback.message.edit_text(
                updated_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None  # Убираем все кнопки
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")

            # Если не удалось отредактировать, попробуем отправить новое сообщение
            try:
                await update_order_messages(order_id, "confirmed", admin_username)
            except Exception as update_error:
                logger.error(f"Ошибка обновления сообщений заказа: {update_error}")

        await callback.answer(f"Заказ #{order_id} подтвержден!", show_alert=True)
        logger.info(f"Обработка заказа #{order_id} завершена успешно")

    except Exception as e:
        logger.error(f"Ошибка при обработке заказа #{order_id}: {e}")
        if conn: conn.rollback()
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn: conn.close()


# Обработчик отмены заказа
@dp.callback_query(F.data.startswith('cancel_order_'))
async def cancel_order_handler(callback: types.CallbackQuery):
    conn = None
    try:
        # Проверяем формат команды
        parts = callback.data.split('_')
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат команды", show_alert=True)
            return

        # Извлекаем ID заказа
        try:
            order_id = int(callback.data.split('_')[-1])
            admin_username = callback.from_user.username or f"id{callback.from_user.id}"
        except ValueError:
            await callback.answer("❌ Неверный ID заказа", show_alert=True)
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем необходимую информацию о заказе
        cursor.execute("""
                       SELECT user_id, user_name, total_amount, status
                       FROM orders
                       WHERE id = ?
                       """, (order_id,))
        order_data = cursor.fetchone()

        if not order_data:
            await callback.answer("❌ Заказ не найден!", show_alert=True)
            return

        # Распаковываем данные заказа
        user_id, user_name, total_amount, current_status = order_data

        # Проверяем статус заказа
        if current_status != 'pending':
            await callback.answer(f"❌ Заказ уже был обработан (статус: {current_status})", show_alert=True)
            return

        # Обновляем статус заказа
        cursor.execute("""
                       UPDATE orders
                       SET status = 'cancelled'
                       WHERE id = ?
                       """, (order_id,))
        conn.commit()

        # Уведомление пользователя
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ Ваш заказ #{order_id} был отменен.\n\n"
                     f"Сумма заказа: {int(total_amount)} ₽\n"
                     f"Если это ошибка, свяжитесь с поддержкой.",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю: {e}")

        # Обновляем сообщение с уведомлением о заказе
        try:
            # Получаем текущий текст сообщения
            current_text = callback.message.text

            # Добавляем информацию об отмене
            updated_text = current_text + f"\n\n❌ <b>Заказ отменен администратором @{admin_username}</b>"

            # Редактируем сообщение, убирая кнопки
            await callback.message.edit_text(
                updated_text,
                parse_mode=ParseMode.HTML,
                reply_markup=None  # Убираем все кнопки
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")

            # Если не удалось отредактировать, попробуем отправить новое сообщение
            try:
                await update_order_messages(order_id, "cancelled", admin_username)
            except Exception as update_error:
                logger.error(f"Ошибка обновления сообщений заказа: {update_error}")

        await callback.answer(f"Заказ #{order_id} отменен!", show_alert=True)

    except sqlite3.Error as e:
        logger.error(f"SQL error: {e}")
        if conn: conn.rollback()
        await callback.answer("⚠️ Ошибка базы данных", show_alert=True)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
    finally:
        if conn:
            conn.close()


# Автоматическая очистка старых заказов:
async def clean_old_orders():
    while True:
        now = datetime.now()
        for order_id, order_data in list(pending_orders.items()):
            # Удаляем заказы старше 24 часов
            if (now - order_data['created_at']) > timedelta(hours=24):
                del pending_orders[order_id]
        await asyncio.sleep(3600)  # Проверка каждый час









def get_product_with_size(product_id, size_id=None):
    """Получает товар с конкретным размером"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if size_id and size_id != 0:
            # Товар с конкретным размером
            cursor.execute("""
                SELECT 
                    p.id, p.name, p.price, p.discount_percent,
                    p.image_url, p.sku,
                    s.id as size_id, s.value as size_name,
                    pv.quantity,
                    b.name as brand_name,
                    c.name as category_name
                FROM products p
                LEFT JOIN product_variants pv ON p.id = pv.product_id
                LEFT JOIN sizes s ON pv.size_id = s.id
                LEFT JOIN brands b ON p.brand_id = b.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE p.id = ? AND pv.size_id = ? AND pv.quantity > 0
            """, (product_id, size_id))
        else:
            # Товар без размера (аксессуары)
            cursor.execute("""
                SELECT 
                    p.id, p.name, p.price, p.discount_percent,
                    p.image_url, p.sku, p.quantity,
                    b.name as brand_name,
                    c.name as category_name
                FROM products p
                LEFT JOIN brands b ON p.brand_id = b.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE p.id = ? AND p.quantity > 0
            """, (product_id,))

        product = cursor.fetchone()
        return dict(product) if product else None

    except Exception as e:
        print(f"Ошибка получения товара с размером: {e}")
        return None
    finally:
        conn.close()


def update_user_activity(user_id: int):
    """Обновляет время последней активности пользователя"""
    user_activity[user_id] = time.time()

    # Также обновляем в базе данных
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_login = CURRENT_TIMESTAMP 
            WHERE id = ? OR telegram_id = ?
        """, (user_id, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Ошибка обновления last_login: {e}")


# ======== ОБРАБОТЧИК ДЛЯ КНОПОК "КУПИТЬ" ИЗ РАССЫЛКИ СКИДОК ========
#
# @dp.callback_query(F.data.startswith('buy_discount_'))
# async def handle_buy_discount_callback(callback: types.CallbackQuery):
#     """Обработчик для кнопок Купить из рассылки скидок"""
#     try:
#         logger.info(f"🔍 Обработчик buy_discount вызван: {callback.data}")
#
#         # Получаем product_id из callback_data
#         product_id = int(callback.data.replace('buy_discount_', ''))
#         user_id = callback.from_user.id
#
#         logger.info(f"🔍 Product ID: {product_id}, User ID: {user_id}")
#
#         # Добавляем товар в корзину
#         success = await add_product_to_cart_directly(user_id, product_id)
#
#         if success:
#             await callback.answer("✅ Товар добавлен в корзину!")
#
#             # Обновляем сообщение
#             try:
#                 message_text = callback.message.text or callback.message.caption
#                 if "✅ Добавлено в корзину" not in message_text:
#                     new_text = message_text + "\n\n✅ Добавлено в корзину"
#                     await callback.message.edit_text(new_text, parse_mode='HTML')
#             except Exception as e:
#                 logger.error(f"Ошибка обновления сообщения: {e}")
#         else:
#             await callback.answer("❌ Ошибка при добавлении в корзину", show_alert=True)
#
#     except Exception as e:
#         logger.error(f"❌ Ошибка в handle_buy_discount_callback: {e}")
#         await callback.answer("❌ Произошла ошибка", show_alert=True)
#
#
# async def add_product_to_cart_directly(user_id: int, product_id: int) -> bool:
#     """Добавление товара напрямую в корзину (для рассылки скидок)"""
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         # Проверяем наличие товара
#         cursor.execute("SELECT quantity FROM products WHERE id = ?", (product_id,))
#         product = cursor.fetchone()
#
#         if not product or product[0] <= 0:
#             logger.error(f"Товар {product_id} отсутствует")
#             return False
#
#         # Создаем/получаем корзину
#         cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
#         cart = cursor.fetchone()
#
#         if cart:
#             cart_id = cart[0]
#         else:
#             cursor.execute("INSERT INTO cart (user_id) VALUES (?)", (user_id,))
#             cart_id = cursor.lastrowid
#
#         # Добавляем товар в корзину
#         cursor.execute("""
#             INSERT INTO cart_items (cart_id, product_id, quantity)
#             VALUES (?, ?, 1)
#             ON CONFLICT(cart_id, product_id)
#             DO UPDATE SET quantity = quantity + 1
#         """, (cart_id, product_id))
#
#         conn.commit()
#         conn.close()
#
#         logger.info(f"✅ Товар {product_id} добавлен в корзину пользователя {user_id}")
#         return True
#
#     except Exception as e:
#         logger.error(f"❌ Ошибка добавления товара в корзину: {e}")
#         return False
#



# @dp.callback_query()
# async def handle_other_callbacks(callback: types.CallbackQuery, state: FSMContext):
#     """Обрабатывает все callback-запросы, которые не были обработаны другими обработчиками"""
#     update_user_activity(callback.from_user.id)
#     await callback.answer("Действие выполнено")


# ДОБАВЬТЕ ЭТОТ ОБРАБОТЧИК ПЕРВЫМ - он будет ловить ВСЕ callback_data для отладки
# @dp.callback_query()
# async def debug_all_callbacks(callback: types.CallbackQuery):
#     """Обработчик для отладки - ловит все callback_data"""
#     print(f"🔍 DEBUG: Получен callback_data: {callback.data}")
#     print(f"🔍 DEBUG: От пользователя: {callback.from_user.id}")
#     # Пропускаем обработку дальше
#     return


# УДАЛИТЕ все предыдущие обработчики add_ и add_from_notify_ и ЗАМЕНИТЕ на этот:







# 2. Обработчик для добавления с размером из уведомлений
@dp.callback_query(F.data.startswith('add_from_notify_'))
async def handle_add_with_size_from_notification(callback: types.CallbackQuery):
    print(f"🔍 DEBUG: Обработчик add_from_notify получил: {callback.data}")
    try:
        # Парсим данные из callback - формат: add_from_notify_{product_id}_{size_id}
        parts = callback.data.split('_')
        product_id = int(parts[3])
        size_id = int(parts[4])

        user_id = callback.from_user.id
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Создаем/получаем корзину
        cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
        cart = cursor.fetchone()

        if cart:
            cart_id = cart[0]
        else:
            cursor.execute("INSERT INTO cart (user_id) VALUES (?)", (user_id,))
            cart_id = cursor.lastrowid

        # Добавляем товар в корзину
        cursor.execute("""
            INSERT INTO cart_items (cart_id, product_id, size_id, quantity)
            VALUES (?, ?, ?, 1) 
            ON CONFLICT(cart_id, product_id, size_id) 
            DO UPDATE SET quantity = quantity + 1
        """, (cart_id, product_id, size_id))

        conn.commit()
        conn.close()

        # Обновляем сообщение с товаром
        try:
            await callback.message.edit_caption(
                caption=callback.message.caption,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🛒 Посмотреть корзину", callback_data="view_cart")],
                        [InlineKeyboardButton(text="❌ Очистить корзину", callback_data="clear_cart")],
                    ]
                )
            )
        except:
            pass

        await callback.answer("💠 Товар добавлен в корзину!")

    except Exception as e:
        logger.exception(f"Ошибка добавления с размером из уведомления: {e}")
        await callback.answer("❌ Произошла ошибка при добавлении в корзину", show_alert=True)


# 3. Упрощенный обработчик для добавления в корзину
@dp.callback_query(F.data.startswith('add_') | F.data.startswith('select_size_'))
async def universal_cart_handler(callback: types.CallbackQuery):
    """Универсальный обработчик для корзины"""
    print(f"🔍 DEBUG: Универсальный обработчик получил: {callback.data}")

    conn = None
    try:
        data = callback.data
        user_id = callback.from_user.id
        print(f"🔍 DEBUG: User ID: {user_id}")

        # Обработка выбора размера
        if data.startswith('select_size_'):
            product_id = int(data.split('_')[2])
            print(f"🔍 DEBUG: Обработка выбора размера для товара {product_id}")

            # Получаем информацию о товаре
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name, price, category_id FROM products WHERE id = ?", (product_id,))
            product = cursor.fetchone()
            conn.close()

            if not product:
                print(f"🔍 DEBUG: Товар {product_id} не найден")
                await callback.answer("❌ Товар не найден", show_alert=True)
                return

            product_name, price, category_id = product
            print(f"🔍 DEBUG: Товар найден: {product_name}, цена: {price}, категория: {category_id}")

            # Показываем выбор размера
            await show_size_selection(callback, product_id, product_name, price, from_notification=True)
            return

        # Обработка добавления в корзину
        parts = data.split('_')
        print(f"🔍 DEBUG: Части callback_data: {parts}, количество: {len(parts)}")

        # Определяем формат и парсим данные
        product_id = None
        size_id = None

        if len(parts) == 2:
            # Формат: add_{product_id} - для аксессуаров
            product_id = int(parts[1])
            size_id = 0
            print(f"🔍 DEBUG: Формат для аксессуаров. Product ID: {product_id}, Size ID: {size_id}")
        elif len(parts) == 3:
            # Формат: add_{product_id}_{size_id} - обычное добавление
            product_id = int(parts[1])
            size_id = int(parts[2])
            print(f"🔍 DEBUG: Формат с размером. Product ID: {product_id}, Size ID: {size_id}")
        elif len(parts) == 4 and parts[1] == 'from' and parts[2] == 'notify':
            # Формат: add_from_notify_{product_id}_{size_id} - из уведомлений
            product_id = int(parts[3])
            size_id = int(parts[4])
            print(f"🔍 DEBUG: Формат из уведомлений. Product ID: {product_id}, Size ID: {size_id}")
        else:
            print(f"🔍 DEBUG: Неверный формат данных: {data}")
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        if product_id is None:
            print(f"🔍 DEBUG: Не удалось распарсить product_id из {data}")
            await callback.answer("❌ Ошибка в данных товара", show_alert=True)
            return

        # Добавляем товар в корзину
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Для товаров без размера (аксессуары) - size_id = 0
        if size_id is None:
            # Проверяем, действительно ли это аксессуар
            cursor.execute("SELECT name, category_id FROM products WHERE id = ?", (product_id,))
            result = cursor.fetchone()

            if not result:
                print(f"🔍 DEBUG: Товар с ID {product_id} не найден в базе")
                await callback.answer("❌ Товар не найден", show_alert=True)
                return

            product_name, category_id = result
            print(f"🔍 DEBUG: Товар '{product_name}' имеет category_id: {category_id}")

            if category_id != 8:  # 8 - ID для аксессуаров
                print(
                    f"🔍 DEBUG: Товар {product_id} не является аксессуаром (category_id={category_id}), требуется выбор размера")
                await callback.answer(
                    "🚫 Для этого товара нужно выбрать размер!",
                    show_alert=True
                )
                return
            else:
                print(f"🔍 DEBUG: Товар {product_id} является аксессуаром, добавляем в корзину")

        # Создаем/получаем корзину
        cursor.execute("SELECT id FROM cart WHERE user_id = ?", (user_id,))
        cart = cursor.fetchone()

        if cart:
            cart_id = cart[0]
            print(f"🔍 DEBUG: Найдена существующая корзина ID: {cart_id}")
        else:
            cursor.execute("INSERT INTO cart (user_id) VALUES (?)", (user_id,))
            cart_id = cursor.lastrowid
            print(f"🔍 DEBUG: Создана новая корзина ID: {cart_id}")

        # Добавляем товар в корзину
        print(f"🔍 DEBUG: Добавляем товар {product_id} с размером {size_id} в корзину {cart_id}")
        cursor.execute("""
            INSERT INTO cart_items (cart_id, product_id, size_id, quantity)
            VALUES (?, ?, ?, 1) 
            ON CONFLICT(cart_id, product_id, size_id) 
            DO UPDATE SET quantity = quantity + 1
        """, (cart_id, product_id, size_id))

        conn.commit()
        print(f"🔍 DEBUG: Товар успешно добавлен в корзину")

        # Обновляем сообщение с товаром
        try:
            # Пытаемся изменить подпись (для фото)
            await callback.message.edit_caption(
                caption=callback.message.caption,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🛒 Посмотреть корзину", callback_data="view_cart")],
                        [InlineKeyboardButton(text="❌ Очистить корзину", callback_data="clear_cart")],
                    ]
                )
            )
            print(f"🔍 DEBUG: Сообщение успешно обновлено (edit_caption)")
        except Exception as e:
            # Пытаемся изменить разметку (для текста)
            try:
                await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🛒 Посмотреть корзину", callback_data="view_cart")],
                        [InlineKeyboardButton(text="❌ Очистить корзину", callback_data="clear_cart")],
                    ]
                ))
                print(f"🔍 DEBUG: Сообщение успешно обновлено (edit_reply_markup)")
            except Exception as e2:
                print(f"🔍 DEBUG: Не удалось обновить сообщение: {e2}")

        await callback.answer("💠 Товар добавлен в корзину!")
        print(f"🔍 DEBUG: callback.answer отправлен")

    except ValueError as e:
        print(f"🔍 DEBUG: Ошибка парсинга данных: {e}")
        logger.error(f"Ошибка парсинга callback_data: {callback.data}, ошибка: {e}")
        await callback.answer("❌ Ошибка в данных товара", show_alert=True)
    except Exception as e:
        print(f"🔍 DEBUG: Общая ошибка: {e}")
        logger.exception(f"Ошибка добавления в корзину: {e}")
        await callback.answer("❌ Произошла ошибка при добавлении в корзину", show_alert=True)
    finally:
        if conn:
            conn.close()
            print(f"🔍 DEBUG: Соединение с БД закрыто")

# Функция для показа выбора размера
async def show_size_selection(callback: types.CallbackQuery, product_id: int, product_name: str, price: float,
                              from_notification: bool = False):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем доступные размеры для этого товара
        cursor.execute("""
            SELECT DISTINCT s.id, s.value 
            FROM sizes s 
            JOIN product_variants pv ON s.id = pv.size_id 
            WHERE pv.product_id = ? AND pv.quantity > 0
            ORDER BY s.id
        """, (product_id,))

        sizes = cursor.fetchall()
        conn.close()

        if not sizes:
            await callback.answer("❌ Нет доступных размеров для этого товара", show_alert=True)
            return

        # Создаем клавиатуру с размерами
        keyboard = []
        row = []

        for size_id, size_value in sizes:
            # Для уведомлений используем другой формат callback_data
            if from_notification:
                callback_data = f"add_from_notify_{product_id}_{size_id}"
            else:
                callback_data = f"add_{product_id}_{size_id}"

            row.append(InlineKeyboardButton(text=size_value, callback_data=callback_data))

            if len(row) == 3:  # 3 кнопки в строке
                keyboard.append(row)
                row = []

        if row:  # Добавляем оставшиеся кнопки
            keyboard.append(row)

        # Добавляем кнопку отмены
        keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_size")])

        # Отправляем или редактируем сообщение с выбором размера
        message_text = f"🎱 Выберите размер для:\n<b>{product_name}</b>\n💵 Цена: {price}₽"

        if from_notification:
            # Для уведомлений редактируем текущее сообщение
            await callback.message.edit_caption(
                caption=message_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )
        else:
            # Для обычного каталога отправляем новое сообщение
            await callback.message.answer(
                message_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="HTML"
            )

        if not from_notification:
            await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка при показе размеров: {e}")
        await callback.answer("❌ Ошибка при выборе размера", show_alert=True)
@dp.callback_query(F.data.startswith('select_size_'))
async def handle_select_size_from_notification(callback: types.CallbackQuery):
    print(f"🔍 DEBUG: Обработчик select_size получил: {callback.data}")
    try:
        # Парсим product_id из callback_data: select_size_{product_id}
        product_id = int(callback.data.split('_')[2])

        # Получаем информацию о товаре
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name, price FROM products WHERE id = ?", (product_id,))
        product = cursor.fetchone()
        conn.close()

        if not product:
            await callback.answer("❌ Товар не найден", show_alert=True)
            return

        product_name, price = product

        # Показываем выбор размера
        await show_size_selection(callback, product_id, product_name, price, from_notification=True)

    except Exception as e:
        logger.exception(f"Ошибка при выборе размера из уведомления: {e}")
        await callback.answer("❌ Ошибка при выборе размера", show_alert=True)
# ======== ЗАПУСК БОТА ========

async def main():
    await on_startup()
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())
    asyncio.create_task(clean_old_orders())
    asyncio.create_task(start_cleanup_task())
