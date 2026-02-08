from aiohttp import web
import aiohttp
import sys
import uuid  # Добавьте в начало файла с другими импортами
from typing import List, Dict, Any
import asyncio
import aiohttp
from aiohttp import web
import aiohttp_jinja2
import sqlite3
from datetime import datetime
from flask import jsonify, request
import sqlite3
from datetime import datetime, timedelta
import sqlite3
import asyncio
from datetime import datetime, timedelta
import json
from datetime import datetime
import aiohttp_jinja2
import jinja2
from pathlib import Path
import sqlite3
import os
import json
from functools import wraps
from pathlib import Path
import logging
logging.basicConfig(filename='debug.log', level=logging.DEBUG)
from dotenv import load_dotenv
load_dotenv()  # Эта строка ОБЯЗАТЕЛЬНА!
logger=logging.getLogger(__name__)
# Настройки
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'shop.db')
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
BASE_DIR = Path(__file__).parent


# Добавим после других функций

class TelegramBot:
    def __init__(self):
        self.token = os.getenv('BOT_TOKEN')
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def get_bot_info(self) -> Dict[str, Any]:
        """Получает информацию о боте"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/getMe") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('result', {})
                    return {}
        except Exception as e:
            print(f"Ошибка при получении информации о боте: {e}")
            return {}

    async def get_chat_members_count(self, chat_id: str) -> int:
        """Получает количество участников в чате/канале"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/getChatMembersCount?chat_id={chat_id}") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('result', 0)
                    return 0
        except Exception as e:
            print(f"Ошибка при получении количества участников: {e}")
            return 0

    async def send_message_to_chat(self, chat_id: str, message: str, parse_mode: str = "HTML") -> bool:
        """Отправляет сообщение в чат/канал"""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    'chat_id': chat_id,
                    'text': message,
                    'parse_mode': parse_mode
                }
                async with session.post(f"{self.base_url}/sendMessage", json=payload) as response:
                    return response.status == 200
        except Exception as e:
            print(f"Ошибка при отправке сообщения: {e}")
            return False

    async def broadcast_message(self, chat_ids: List[str], message: str) -> Dict[str, int]:
        """Рассылает сообщение по списку чатов"""
        success_count = 0
        fail_count = 0

        for chat_id in chat_ids:
            if await self.send_message_to_chat(chat_id, message):
                success_count += 1
            else:
                fail_count += 1

        return {
            'success_count': success_count,
            'fail_count': fail_count,
            'total': success_count + fail_count
        }





def get_chat_ids_from_db():
    """Получает список chat_id активных пользователей"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT telegram_chat_id FROM users WHERE is_active = TRUE AND telegram_chat_id IS NOT NULL")
        chat_ids = [row[0] for row in cursor.fetchall()]
        return chat_ids
    except Exception as e:
        print(f"Ошибка получения chat_ids: {e}")
        return []
    finally:
        conn.close()


def save_notification_to_db(notification_type, message, success_count, fail_count):
    """Сохраняет уведомление в базу данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO notification_history (type, text, success_count, fail_count, sent_at)
            VALUES (?, ?, ?, ?, ?)
        """, (notification_type, message, success_count, fail_count, datetime.now()))

        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Ошибка сохранения уведомления: {e}")
        return None
    finally:
        conn.close()


def get_notifications_from_db(limit=10):
    """Получает историю уведомлений из базы данных"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT type, text, success_count, fail_count, sent_at 
            FROM notification_history 
            ORDER BY sent_at DESC 
            LIMIT ?
        """, (limit,))

        notifications = []
        for row in cursor.fetchall():
            sent_at = row[4]
            if isinstance(sent_at, str):
                # Преобразуем строку в datetime если нужно
                try:
                    sent_at = datetime.strptime(sent_at, '%Y-%m-%d %H:%M:%S')
                except:
                    pass

            date_str = sent_at.strftime('%d.%m.%Y %H:%M') if isinstance(sent_at, datetime) else str(sent_at)

            notifications.append({
                'type': row[0],
                'text': row[1],
                'success_count': row[2],
                'fail_count': row[3],
                'date': date_str,
                'type_display': get_type_display(row[0])
            })

        return notifications
    except Exception as e:
        print(f"Ошибка получения истории уведомлений: {e}")
        return []
    finally:
        conn.close()


def get_type_display(notification_type):
    """Возвращает читаемое название типа уведомления"""
    types = {
        'general': 'Общее уведомление',
        'sale': 'Скидки и акции',
        'new_arrivals': 'Новые поступления',
        'important': 'Важная информация',
        'custom': 'Произвольный текст'
    }
    return types.get(notification_type, 'Общее уведомление')





def get_online_users_count():
    """Получает количество онлайн пользователей"""
    try:
        # Простая реализация через временные метки в БД
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Используем last_login как показатель активности
        cursor.execute("""
            SELECT COUNT(*) FROM users 
            WHERE last_login >= datetime('now', '-5 minutes')
            AND is_active = TRUE
        """)
        online_count = cursor.fetchone()[0]
        conn.close()
        return online_count

    except Exception as e:
        print(f"Ошибка получения онлайн пользователей: {e}")
        return 0


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

        # Онлайн пользователи
        online_users = get_online_users_count()

        return {
            'total_users': total_users,
            'today_users': today_users,
            'active_users': active_users,
            'all_users': all_users,
            'online_users': online_users
        }
    except sqlite3.Error as e:
        logger.error(f"Ошибка получения статистики пользователей: {e}")
        return {'total_users': 0, 'today_users': 0, 'active_users': 0, 'all_users': 0, 'online_users': 0}
    finally:
        conn.close()

def init_db():
    """Инициализация базы данных с правильной структурой"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Создаем таблицу для истории уведомлений
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type VARCHAR(50) NOT NULL,
            text TEXT NOT NULL,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("✅ Таблица notification_history создана/проверена")

async def handle_404(request):
    return aiohttp_jinja2.render_template('404.html', request, {})

async def handle_500(request):
    return aiohttp_jinja2.render_template('500.html', request, {})

def create_error_middleware():
    @web.middleware
    async def error_middleware(request, handler):
        try:
            response = await handler(request)
            return response
        except web.HTTPException as ex:
            if ex.status == 404:
                return await handle_404(request)
            else:
                raise
        except Exception:
            return await handle_500(request)
    return error_middleware
# Добавьте эту функцию после импортов
def format_price(value):
    """Форматирует цену в читаемый вид"""
    if isinstance(value, str):
        value = int(value)
    return f"{value:,}".replace(",", " ")
# Создаем приложение
app = web.Application(client_max_size=20*1024*1024)
app.middlewares.append(create_error_middleware())
# Настраиваем Jinja2
env = aiohttp_jinja2.setup(app,
    loader=jinja2.FileSystemLoader('templates')
)

# Добавьте фильтр для форматирования цены
env.filters['format_price'] = format_price

# Добавьте фильтр from_json для парсинга JSON
def from_json(value):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
env.filters['from_json'] = from_json

# Добавьте фильтр для форматирования цены
env.filters['format_price'] = format_price

# Middleware для аутентификации
def require_auth(func):
    @wraps(func)
    async def wrapper(request):
        if not request.cookies.get('authenticated'):
            return web.HTTPFound('/login')
        return await func(request)

    return wrapper


# Статические файлы
app.router.add_static('/static', Path('static'))


# Роуты
@aiohttp_jinja2.template('login.html')
async def login_page(request):
    error = request.query.get('error')
    return {'error': error}


async def login_handler(request):
    data = await request.post()
    admin_username = os.getenv('ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('ADMIN_PASSWORD', 'ADMIN_PASSWORD')

    if data.get('username') == admin_username and data.get('password') == admin_password:
        response = web.HTTPFound('/')
        # Добавляем параметры для долгоживущей куки (30 дней)
        response.set_cookie('authenticated', 'true',
                          max_age=30*24*60*60,  # 30 дней в секундах
                          path='/',
                          httponly=True,
                          secure=True)  # Поставьте True если используете HTTPS
        return response
    return web.HTTPFound('/login?error=1')


@require_auth
@aiohttp_jinja2.template('dashboard.html')
async def dashboard(request):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Получаем статистику
        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total_orders = cursor.fetchone()['count']

        cursor.execute("SELECT SUM(total_amount) as total FROM orders WHERE status != 'cancelled'")
        total_revenue_result = cursor.fetchone()['total']
        total_revenue = total_revenue_result if total_revenue_result else 0

        # Выручка за сегодня
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT SUM(total_amount) as total_today 
            FROM orders 
            WHERE DATE(created_at) = ? AND status != 'cancelled'
        """, (today,))
        revenue_today_result = cursor.fetchone()['total_today']
        revenue_today = revenue_today_result if revenue_today_result else 0

        # Чистая прибыль (примерная формула - 60% от выручки)
        net_profit = int(total_revenue * 0.6)

        cursor.execute("SELECT COUNT(*) as count FROM products")
        total_products = cursor.fetchone()['count']

        # Активные клиенты
        cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM orders WHERE status != 'cancelled'")
        total_customers_result = cursor.fetchone()['count']
        total_customers = total_customers_result if total_customers_result else 0

        # Доставки за сегодня
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM orders 
            WHERE DATE(created_at) = ? AND status = 'delivered'
        """, (today,))
        deliveries_today_result = cursor.fetchone()['count']
        deliveries_today = deliveries_today_result if deliveries_today_result else 0

        # Получаем последние заказы
        cursor.execute("""
            SELECT o.id, o.user_name, o.total_amount, o.created_at, o.status,
                   (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as items_count,
                   (SELECT p.name FROM order_items oi 
                    JOIN products p ON oi.product_id = p.id 
                    WHERE oi.order_id = o.id LIMIT 1) as first_product_name
            FROM orders o 
            ORDER BY o.created_at DESC 
            LIMIT 5
        """)
        recent_orders_data = cursor.fetchall()

        # Преобразуем статусы на русский
        status_translation = {
            'pending': 'ожидание',
            'confirmed': 'подтвержден',
            'cancelled': 'отменен',
            'delivered': 'доставлен',
            'returned': 'возвращен'
        }

        recent_orders = []
        for order in recent_orders_data:
            # Преобразуем дату
            if isinstance(order['created_at'], str):
                try:
                    created_at = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    created_at = order['created_at']
            else:
                created_at = order['created_at']

            order_dict = {
                'id': order['id'],
                'user_name': order['user_name'],
                'total_amount': order['total_amount'],
                'created_at': created_at,
                'status': order['status'],
                'status_ru': status_translation.get(order['status'], order['status']),
                'items_count': order['items_count'],
                'first_product_name': order['first_product_name'] or 'Неизвестный товар'
            }
            recent_orders.append(order_dict)



        return {
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'net_profit': net_profit,
            'revenue_today': revenue_today,
            'total_products': total_products,
            'total_customers': total_customers,
            'deliveries_today': deliveries_today,
            'recent_orders': recent_orders

        }


    except Exception as e:

        print(f"Ошибка при загрузке данных для дашборда: {e}")

        conn.close()

        return {

            'total_orders': 0,

            'total_revenue': 0,

            'net_profit': 0,

            'revenue_today': 0,

            'total_products': 0,

            'total_customers': 0,

            'deliveries_today': 0,

            'recent_orders': [],

            'error': f'Ошибка при загрузке данных: {str(e)}'

        }


@require_auth
@aiohttp_jinja2.template('products.html')
async def products_list(request):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Упрощенный запрос для категорий
        try:
            cursor.execute("""
                SELECT id, name, parent_id, discount_percent, discount_end_date 
                FROM categories 
                ORDER BY name
            """)
            categories = cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Ошибка при получении категорий: {e}")
            categories = []

        # Получаем уникальные бренды из товаров (вместо таблицы brands)
        try:
            cursor.execute("SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand != '' ORDER BY brand")
            brands_data = cursor.fetchall()
            brands = [{'id': row['brand'], 'name': row['brand']} for row in brands_data]
        except sqlite3.Error as e:
            print(f"Ошибка при получении брендов: {e}")
            brands = []

        # Проверяем существование таблицы sizes
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sizes'")
            sizes_table_exists = cursor.fetchone() is not None
        except sqlite3.Error as e:
            print(f"Ошибка при проверке таблицы sizes: {e}")
            sizes_table_exists = False

        # Исправленный запрос для товаров - без brand_id
        try:
            # Базовый запрос с LEFT JOIN на таблицу sizes
            query = """
                SELECT p.id, p.name, p.price, p.sku, p.image_url, p.quantity,
                       p.brand,  -- Используем текстовое поле brand вместо brand_id
                       c.id as category_id, c.name as category_name, 
                       p.discount_percent as discount_percent,
                       s.value as size_name  -- Добавляем название размера
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                LEFT JOIN sizes s ON p.size_id = s.id  -- JOIN с таблицей sizes
                ORDER BY p.id DESC
            """

            cursor.execute(query)
            products_data = cursor.fetchall()

            products = []
            for row in products_data:
                product = dict(row)

                # Простая обработка изображений
                image_url = product.get('image_url', '')
                product['main_image'] = None
                product['has_image'] = False

                if image_url and image_url != 'None' and image_url != 'null' and image_url.strip():
                    # Если это JSON, пытаемся распарсить
                    if image_url.strip().startswith('['):
                        try:
                            images = json.loads(image_url)
                            if images and len(images) > 0:
                                product['main_image'] = images[0]
                                product['has_image'] = True
                        except json.JSONDecodeError:
                            product['main_image'] = image_url
                            product['has_image'] = True
                    else:
                        product['main_image'] = image_url
                        product['has_image'] = True

                products.append(product)

        except sqlite3.Error as e:
            print(f"Ошибка при получении товаров: {e}")
            products = []

        conn.close()

        return {
            'products': products,
            'categories': categories,
            'brands': brands,
            'sizes_table_exists': sizes_table_exists
        }

    except Exception as e:
        print(f"Общая ошибка в products_list: {e}")
        import traceback
        traceback.print_exc()
        return {
            'products': [],
            'categories': [],
            'brands': [],
            'sizes_table_exists': False,
            'error': str(e)
        }


async def apply_discounts(request):
    data = await request.json()
    product_id = data.get('product_id')
    discount_percent = data.get('discount_percent')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "UPDATE products SET discount_percent = ? WHERE id = ?",
            (discount_percent, product_id)
        )
        conn.commit()
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})
    finally:
        conn.close()

async def apply_category_discount(request):
    """Применение скидки к категории и всем товарам в ней"""
    data = await request.json()
    category_id = data.get('category_id')
    discount_percent = data.get('discount_percent')
    end_date = data.get('end_date')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Обновляем скидку в категории
        cursor.execute(
            "UPDATE categories SET discount_percent = ?, discount_end_date = ? WHERE id = ?",
            (discount_percent, end_date, category_id)
        )

        # Применяем скидку ко всем товарам в категории
        cursor.execute(
            "UPDATE products SET discount_percent = ? WHERE category_id = ?",
            (discount_percent, category_id)
        )

        conn.commit()
        return web.json_response({'success': True})

    except Exception as e:
        conn.rollback()
        return web.json_response({'success': False, 'error': str(e)})
    finally:
        conn.close()


async def get_category_discounts(request):
    """Получение всех категорий со скидками"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT id, name, discount_percent, discount_end_date 
            FROM categories 
            WHERE discount_percent IS NOT NULL
            ORDER BY name
        """)
        discounts = cursor.fetchall()

        return web.json_response({
            'success': True,
            'discounts': [dict(d) for d in discounts]
        })
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})
    finally:
        conn.close()

async def apply_product_discount(request):
    """Применение скидки к конкретному товару"""
    data = await request.json()
    product_id = data.get('product_id')
    discount_percent = data.get('discount_percent')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Обновляем процент скидки для товара
        cursor.execute(
            "UPDATE products SET discount_percent = ? WHERE id = ?",
            (discount_percent, product_id)
        )

        conn.commit()
        return web.json_response({'success': True})

    except Exception as e:
        conn.rollback()
        return web.json_response({'success': False, 'error': str(e)})
    finally:
        conn.close()


async def remove_discount(request):
    """Удаление скидки с категории или товара"""
    data = await request.json()
    discount_type = data.get('type')  # 'category' или 'product'
    entity_id = data.get('id')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        if discount_type == 'category':
            # Удаляем скидку с категории
            cursor.execute(
                "UPDATE categories SET discount_percent = NULL, discount_end_date = NULL WHERE id = ?",
                (entity_id,)
            )
            # Удаляем скидку со всех товаров в этой категории
            cursor.execute(
                "UPDATE products SET discount_percent = NULL WHERE category_id = ?",
                (entity_id,)
            )
        else:  # product
            # Удаляем скидку с конкретного товара
            cursor.execute(
                "UPDATE products SET discount_percent = NULL WHERE id = ?",
                (entity_id,)
            )

        conn.commit()
        return web.json_response({'success': True})

    except Exception as e:
        conn.rollback()
        return web.json_response({'success': False, 'error': str(e)})
    finally:
        conn.close()


@require_auth
@aiohttp_jinja2.template('add_product.html')
async def add_product(request):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        # Проверяем существование таблицы sizes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sizes'")
        sizes_table_exists = cursor.fetchone() is not None

        # Получаем существующие бренды для автодополнения
        cursor.execute("SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand != '' ORDER BY brand")
        existing_brands = [row['brand'] for row in cursor.fetchall()]

        if request.method == 'POST':
            data = await request.post()

            # Валидация обязательных полей
            required_fields = ['name', 'price', 'sku', 'brand', 'category_id']
            missing_fields = [field for field in required_fields if not data.get(field)]

            # Проверяем, что добавлен хотя бы один размер
            size_ids = data.getall('size_ids[]')
            quantities = data.getall('quantities[]')

            if sizes_table_exists and (not size_ids or not any(size_ids)):
                missing_fields.append('размеры')

            if missing_fields:
                cursor.execute("SELECT id, name FROM categories ORDER BY name")
                categories = cursor.fetchall()

                sizes = []
                if sizes_table_exists:
                    cursor.execute("SELECT id, value FROM sizes ORDER BY value")
                    sizes = cursor.fetchall()

                return {
                    'categories': categories,
                    'existing_brands': existing_brands,
                    'sizes': sizes,
                    'sizes_table_exists': sizes_table_exists,
                    'error': f'Заполните все обязательные поля: {", ".join(missing_fields)}',
                    'form_data': dict(data)
                }

            # Подготовка данных
            name = data['name']
            price = int(float(data['price']))  # Конвертируем в integer
            sku = data['sku']
            brand = data['brand'].strip()
            category_id = int(data['category_id'])
            image_url = data.get('image_url', '[]')  # По умолчанию пустой список JSON

            # Вставляем товары для каждого размера
            for i, size_id_str in enumerate(size_ids):
                if not size_id_str:  # Пропускаем пустые размеры
                    continue

                size_id = int(size_id_str)
                quantity = int(quantities[i]) if i < len(quantities) else 0

                # Вставляем товар
                cursor.execute("""
                    INSERT INTO products (
                        name, sku, category_id, price, brand, 
                        size_id, quantity, image_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    name, sku, category_id, price, brand,
                    size_id, quantity, image_url
                ))

            conn.commit()
            return web.HTTPFound('/products')

        else:
            # GET запрос
            cursor.execute("SELECT id, name FROM categories ORDER BY name")
            categories = cursor.fetchall()

            sizes = []
            if sizes_table_exists:
                cursor.execute("SELECT id, value FROM sizes ORDER BY value")
                sizes = cursor.fetchall()

            return {
                'categories': categories,
                'existing_brands': existing_brands,
                'sizes': sizes,
                'sizes_table_exists': sizes_table_exists
            }

    except Exception as e:
        conn.rollback()
        print(f"Ошибка при добавлении товара: {str(e)}")
        import traceback
        print(f"Трассировка: {traceback.format_exc()}")

        # Получаем данные для формы
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        categories = cursor.fetchall()

        sizes = []
        if sizes_table_exists:
            cursor.execute("SELECT id, value FROM sizes ORDER BY value")
            sizes = cursor.fetchall()

        return {
            'categories': categories,
            'existing_brands': existing_brands,
            'sizes': sizes,
            'sizes_table_exists': sizes_table_exists,
            'error': f'Ошибка при добавлении товара: {str(e)}',
            'form_data': dict(data) if 'data' in locals() else {}
        }

    finally:
        conn.close()



async def delete_product_handler(request):
    product_id = request.match_info['id']

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Удаляем товар
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()

        return web.json_response({'success': True, 'message': 'Товар успешно удален'})

    except Exception as e:
        conn.rollback()
        return web.json_response({'success': False, 'message': str(e)}, status=500)

    finally:
        conn.close()





@require_auth
@aiohttp_jinja2.template('sales.html')
async def sales_list(request):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получаем общую статистику
        cursor.execute("""
            SELECT 
                COALESCE(SUM(p.price * sp.quantity), 0) as total_revenue,
                COALESCE(COUNT(sp.id), 0) as total_sales,
                COALESCE(COUNT(DISTINCT sp.user_id), 0) as total_customers,
                CASE 
                    WHEN COUNT(sp.id) > 0 THEN SUM(p.price * sp.quantity) / COUNT(sp.id)
                    ELSE 0 
                END as avg_order_value
            FROM sold_products sp
            LEFT JOIN products p ON sp.product_id = p.id
        """)
        stats = cursor.fetchone()

        total_revenue = stats['total_revenue'] or 0
        total_sales = stats['total_sales'] or 0
        total_customers = stats['total_customers'] or 0
        avg_order_value = stats['avg_order_value'] or 0

        # Получаем данные для графиков
        sales_chart_labels = []
        sales_chart_values = []
        category_chart_labels = []
        category_chart_values = []

        try:
            # Данные для графика продаж по дням
            cursor.execute("""
                SELECT 
                    DATE(sold_at) as date,
                    SUM(p.price * sp.quantity) as revenue
                FROM sold_products sp
                LEFT JOIN products p ON sp.product_id = p.id
                WHERE DATE(sold_at) >= DATE('now', '-7 days')
                GROUP BY DATE(sold_at)
                ORDER BY date ASC
            """)
            sales_data = cursor.fetchall()

            # Добавляем все дни последней недели, даже если продаж не было
            today = datetime.now().date()
            dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]

            # Создаем словарь с данными по датам
            sales_dict = {data['date']: data['revenue'] for data in sales_data}

            # Заполняем данные для всех дней
            for date in dates:
                sales_chart_labels.append(date)
                sales_chart_values.append(sales_dict.get(date, 0))

            # Данные для графика по категориям
            cursor.execute("""
                SELECT 
                    c.name as category,
                    SUM(p.price * sp.quantity) as revenue
                FROM sold_products sp
                LEFT JOIN products p ON sp.product_id = p.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE c.name IS NOT NULL
                GROUP BY c.name
                ORDER BY revenue DESC
                LIMIT 5
            """)
            category_data = cursor.fetchall()

            for data in category_data:
                category_chart_labels.append(data['category'])
                category_chart_values.append(data['revenue'])

            # Отладочная информация
            print(f"Sales chart labels: {sales_chart_labels}")
            print(f"Sales chart values: {sales_chart_values}")
            print(f"Category chart labels: {category_chart_labels}")
            print(f"Category chart values: {category_chart_values}")

        except Exception as e:
            print(f"Ошибка при получении данных для графиков: {e}")
            # Добавляем тестовые данные для отладки
            sales_chart_labels = ['2023-10-01', '2023-10-02', '2023-10-03']
            sales_chart_values = [1000, 1500, 2000]
            category_chart_labels = ['Категория 1', 'Категория 2']
            category_chart_values = [5000, 3000]

        conn.close()

        return {
            'active_page': 'sales',
            'total_revenue': f"{total_revenue:,.0f}".replace(',', ' '),
            'total_sales': total_sales,
            'total_customers': total_customers,
            'avg_order_value': f"{avg_order_value:,.0f}".replace(',', ' '),
            'sales_chart_labels': sales_chart_labels,
            'sales_chart_values': sales_chart_values,
            'category_chart_labels': category_chart_labels,
            'category_chart_values': category_chart_values,
        }
    except Exception as e:
        print(f"Ошибка в sales_list: {e}")
        import traceback
        traceback.print_exc()
        return {
            'active_page': 'sales',
            'total_revenue': '0',
            'total_sales': 0,
            'total_customers': 0,
            'avg_order_value': '0',
            'sales_chart_labels': ['2023-10-01', '2023-10-02', '2023-10-03'],
            'sales_chart_values': [1000, 1500, 2000],
            'category_chart_labels': ['Категория 1', 'Категория 2'],
            'category_chart_values': [5000, 3000],
        }


@require_auth
async def set_category_discount(request):
    """Установка скидки на категорию"""
    try:
        data = await request.json()
        category_name = data.get('category')
        discount_percent = data.get('discount_percent')
        end_date = data.get('end_date')

        if not category_name or discount_percent is None:
            return web.json_response({'success': False, 'message': 'Не указана категория или процент скидки'})

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Проверяем существование столбца discount_percent в таблице categories
        cursor.execute("PRAGMA table_info(categories)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'discount_percent' not in columns:
            cursor.execute("ALTER TABLE categories ADD COLUMN discount_percent INTEGER")
            cursor.execute("ALTER TABLE categories ADD COLUMN discount_end_date TEXT")

        # Обновляем скидку для категории
        cursor.execute(
            "UPDATE categories SET discount_percent = ?, discount_end_date = ? WHERE name = ?",
            (discount_percent, end_date, category_name)
        )

        # Обновляем скидку для всех товаров в этой категории
        cursor.execute(
            "UPDATE products SET discount_percent = ? WHERE category_id IN (SELECT id FROM categories WHERE name = ?)",
            (discount_percent, category_name)
        )

        conn.commit()
        conn.close()

        return web.json_response({'success': True, 'message': 'Скидка применена к категории'})

    except Exception as e:
        print(f"Ошибка при установке скидки на категорию: {e}")
        return web.json_response({'success': False, 'message': f'Ошибка: {str(e)}'})


@require_auth
async def remove_category_discount(request):
    """Удаление скидки с категории"""
    try:
        data = await request.json()
        category_name = data.get('category')

        if not category_name:
            return web.json_response({'success': False, 'message': 'Не указана категория'})

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Удаляем скидку с категории
        cursor.execute(
            "UPDATE categories SET discount_percent = NULL, discount_end_date = NULL WHERE name = ?",
            (category_name,)
        )

        # Удаляем скидку со всех товаров в этой категории
        cursor.execute(
            "UPDATE products SET discount_percent = NULL WHERE category_id IN (SELECT id FROM categories WHERE name = ?)",
            (category_name,)
        )

        conn.commit()
        conn.close()

        return web.json_response({'success': True, 'message': 'Скидка удалена с категории'})

    except Exception as e:
        print(f"Ошибка при удалении скидки с категории: {e}")
        return web.json_response({'success': False, 'message': f'Ошибка: {str(e)}'})


@require_auth
async def set_product_discount(request):
    """Установка скидки на товар"""
    try:
        data = await request.json()
        product_id = data.get('product_id')
        discount_percent = data.get('discount_percent')

        if not product_id or discount_percent is None:
            return web.json_response({'success': False, 'message': 'Не указан товар или процент скидки'})

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Проверяем существование столбца discount_percent в таблице products
        cursor.execute("PRAGMA table_info(products)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'discount_percent' not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN discount_percent INTEGER")

        # Обновляем скидку для товара
        cursor.execute(
            "UPDATE products SET discount_percent = ? WHERE id = ?",
            (discount_percent, product_id)
        )

        conn.commit()
        conn.close()

        return web.json_response({'success': True, 'message': 'Скидка применена к товару'})

    except Exception as e:
        print(f"Ошибка при установке скидки на товар: {e}")
        return web.json_response({'success': False, 'message': f'Ошибка: {str(e)}'})

@require_auth
async def return_sale(request):
    sale_id = request.match_info['sale_id']

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем информацию о продаже
        cursor.execute("""
            SELECT product_id, size_id, quantity 
            FROM sold_products 
            WHERE id = ?
        """, (sale_id,))
        sale = cursor.fetchone()

        if sale:
            product_id, size_id, quantity = sale

            # Увеличиваем количество товара на складе
            if size_id:
                # Проверяем, есть ли запись в product_sizes
                cursor.execute("""
                    SELECT COUNT(*) FROM product_sizes 
                    WHERE product_id = ? AND size_id = ?
                """, (product_id, size_id))
                exists = cursor.fetchone()[0]

                if exists:
                    cursor.execute("""
                        UPDATE product_sizes 
                        SET quantity = quantity + ? 
                        WHERE product_id = ? AND size_id = ?
                    """, (quantity, product_id, size_id))
                else:
                    # Создаем новую запись
                    cursor.execute("""
                        INSERT INTO product_sizes (product_id, size_id, quantity)
                        VALUES (?, ?, ?)
                    """, (product_id, size_id, quantity))
            else:
                cursor.execute("""
                    UPDATE products 
                    SET quantity = quantity + ? 
                    WHERE id = ?
                """, (quantity, product_id))

            # Помечаем продажу как возвращенную
            cursor.execute("""
                UPDATE sold_products 
                SET returned = 1 
                WHERE id = ?
            """, (sale_id,))

            conn.commit()
            conn.close()

            return web.json_response({
                'success': True,
                'message': 'Товар успешно возвращен'
            })
        else:
            conn.close()
            return web.json_response({
                'success': False,
                'message': 'Продажа не найдена'
            })

    except Exception as e:
        print(f"Error in return_sale: {e}")
        return web.json_response({
            'success': False,
            'message': 'Ошибка при возврате товара'
        })


async def return_product_handler(request):
    sale_id = request.match_info['id']
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Получаем информацию о продаже
        cursor.execute("""
            SELECT product_id, size_id, quantity, order_id
            FROM sold_products WHERE id = ?
        """, (sale_id,))
        sale = cursor.fetchone()

        if sale:
            product_id, size_id, quantity, order_id = sale

            # Возвращаем товар на склад
            if size_id:
                cursor.execute("""
                    UPDATE products
                    SET quantity = quantity + ? 
                    WHERE id = ? AND size_id = ?
                """, (quantity, product_id, size_id))
            else:
                cursor.execute("""
                    UPDATE products
                    SET quantity = quantity + ? 
                    WHERE id = ? AND size_id IS NULL
                """, (quantity, product_id))

            # Обновляем сумму заказа
            cursor.execute("SELECT price FROM products WHERE id = ?", (product_id,))
            price = cursor.fetchone()[0]

            cursor.execute("""
                UPDATE orders 
                SET total_amount = total_amount - (? * ?)
                WHERE id = ?
            """, (price, quantity, order_id))

            # Удаляем запись о продаже
            cursor.execute("DELETE FROM sold_products WHERE id = ?", (sale_id,))

            conn.commit()

    except Exception as e:
        conn.rollback()
        print(f"Ошибка возврата товара: {e}")

    finally:
        conn.close()

    return web.HTTPFound('/sales')


async def logout_handler(request):
    response = web.HTTPFound('/login')
    response.del_cookie('authenticated')
    return response


@require_auth
@aiohttp_jinja2.template('edit_products.html')
async def edit_product(request):
    product_id = request.match_info.get('product_id')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        # Проверяем существование таблицы sizes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sizes'")
        sizes_table_exists = cursor.fetchone() is not None

        # Получаем существующие бренды для автодополнения
        cursor.execute("SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand != '' ORDER BY brand")
        existing_brands = [row['brand'] for row in cursor.fetchall()]

        if request.method == 'POST':
            data = await request.post()

            # Подготовка данных
            name = data['name']
            price = int(float(data['price']))
            sku = data['sku']
            brand = data['brand'].strip()
            category_id = int(data['category_id'])
            quantity = int(data.get('quantity', 0))
            image_url = data.get('image_url', '[]')

            # Обработка size_id
            size_id = int(data['size_id']) if data.get('size_id') else None

            # Обновляем товар
            cursor.execute("""
                UPDATE products 
                SET name=?, price=?, sku=?, brand=?, category_id=?, 
                    size_id=?, quantity=?, image_url=?
                WHERE id=?
            """, (
                name, price, sku, brand, category_id,
                size_id, quantity, image_url, product_id
            ))

            conn.commit()
            return web.HTTPFound('/products')

        else:
            # GET запрос - получаем товар
            cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            product = cursor.fetchone()

            if not product:
                return web.HTTPNotFound(text="Товар не найден")

            cursor.execute("SELECT id, name FROM categories ORDER BY name")
            categories = cursor.fetchall()

            sizes = []
            if sizes_table_exists:
                cursor.execute("SELECT id, value FROM sizes ORDER BY value")
                sizes = cursor.fetchall()

            return {
                'product': product,
                'categories': categories,
                'existing_brands': existing_brands,
                'sizes': sizes,
                'sizes_table_exists': sizes_table_exists
            }

    except Exception as e:
        conn.rollback()
        print(f"Ошибка при редактировании товара: {str(e)}")

        # Получаем данные для формы
        cursor.execute("SELECT id, name FROM categories ORDER BY name")
        categories = cursor.fetchall()

        sizes = []
        if sizes_table_exists:
            cursor.execute("SELECT id, value FROM sizes ORDER BY value")
            sizes = cursor.fetchall()

        return {
            'categories': categories,
            'existing_brands': existing_brands,
            'sizes': sizes,
            'sizes_table_exists': sizes_table_exists,
            'error': f'Ошибка при редактировании товара: {str(e)}',
            'form_data': dict(data) if 'data' in locals() else {}
        }

    finally:
        conn.close()


@require_auth
@aiohttp_jinja2.template('dashboard.html')
async def dashboard(request):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Получаем статистику
        cursor.execute("SELECT COUNT(*) as count FROM orders")
        total_orders = cursor.fetchone()['count']

        cursor.execute("SELECT SUM(total_amount) as total FROM orders WHERE status != 'cancelled'")
        total_revenue_result = cursor.fetchone()['total']
        total_revenue = total_revenue_result if total_revenue_result else 0

        # Выручка за сегодня
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            SELECT SUM(total_amount) as total_today 
            FROM orders 
            WHERE DATE(created_at) = ? AND status != 'cancelled'
        """, (today,))
        revenue_today_result = cursor.fetchone()['total_today']
        revenue_today = revenue_today_result if revenue_today_result else 0

        # Чистая прибыль (примерная формула - 60% от выручки)
        net_profit = int(total_revenue * 0.6)

        cursor.execute("SELECT COUNT(*) as count FROM products WHERE quantity > 0")
        total_products = cursor.fetchone()['count']

        # Активные клиенты
        cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM orders WHERE status != 'cancelled'")
        total_customers_result = cursor.fetchone()['count']
        total_customers = total_customers_result if total_customers_result else 0

        # Доставки за сегодня
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM orders 
            WHERE DATE(created_at) = ? AND status = 'delivered'
        """, (today,))
        deliveries_today_result = cursor.fetchone()['count']
        deliveries_today = deliveries_today_result if deliveries_today_result else 0

        # Получаем последние заказы
        # Получаем последние заказы с названиями товаров через JOIN
        # Получаем последние заказы с товарами из sold_products
        # В dashboard handler обновляем запрос:
        # В dashboard handler обновляем запрос для возвращенных заказов:
        cursor.execute("""
            SELECT 
                o.id, 
                o.user_name, 
                o.total_amount, 
                o.created_at, 
                o.status,
                CASE 
                    WHEN o.status = 'returned' THEN
                        COALESCE(
                            (SELECT p.name FROM order_items oi 
                             LEFT JOIN products p ON oi.product_id = p.id 
                             WHERE oi.order_id = o.id LIMIT 1),
                            (SELECT name FROM sold_products WHERE order_id = o.id LIMIT 1),
                            'Неизвестный товар'
                        )
                    ELSE
                        COALESCE(
                            (SELECT name FROM sold_products WHERE order_id = o.id LIMIT 1),
                            (SELECT p.name FROM order_items oi 
                             LEFT JOIN products p ON oi.product_id = p.id 
                             WHERE oi.order_id = o.id LIMIT 1),
                            'Неизвестный товар'
                        )
                END as first_product_name,
                CASE 
                    WHEN o.status = 'returned' THEN
                        COALESCE(
                            (SELECT COUNT(*) FROM order_items WHERE order_id = o.id),
                            (SELECT COUNT(*) FROM sold_products WHERE order_id = o.id),
                            0
                        )
                    ELSE
                        COALESCE(
                            (SELECT COUNT(*) FROM sold_products WHERE order_id = o.id),
                            (SELECT COUNT(*) FROM order_items WHERE order_id = o.id),
                            0
                        )
                END as items_count
            FROM orders o 
            ORDER BY o.created_at DESC 
            LIMIT 5
        """)

        recent_orders_data = cursor.fetchall()

        # Преобразуем статусы на русский
        status_translation = {
            'pending': 'ожидание',
            'confirmed': 'подтвержден',
            'cancelled': 'отменен',
            'delivered': 'доставлен',
            'returned': 'возвращен'
        }

        recent_orders = []
        for order in recent_orders_data:
            if isinstance(order['created_at'], str):
                try:
                    created_at = datetime.strptime(order['created_at'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    created_at = order['created_at']
            else:
                created_at = order['created_at']

            order_dict = {
                'id': order['id'],
                'user_name': order['user_name'],
                'total_amount': order['total_amount'],
                'created_at': created_at,
                'status': order['status'],
                'status_ru': status_translation.get(order['status'], order['status']),
                'items_count': order['items_count'],
                'first_product_name': order['first_product_name'] or 'Неизвестный товар'
            }
            recent_orders.append(order_dict)



        return {
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'net_profit': net_profit,
            'revenue_today': revenue_today,
            'total_products': total_products,
            'total_customers': total_customers,
            'deliveries_today': deliveries_today,
            'recent_orders': recent_orders,

        }


    except Exception as e:

        print(f"Ошибка при загрузке данных для дашборда: {e}")

        conn.close()

        return {

            'total_orders': 0,

            'total_revenue': 0,

            'net_profit': 0,

            'revenue_today': 0,

            'total_products': 0,

            'total_customers': 0,

            'deliveries_today': 0,

            'recent_orders': [],

            'popular_product': "Не определен",

            'error': f'Ошибка при загрузке данных: {str(e)}'

        }


@require_auth
@aiohttp_jinja2.template('orders.html')
async def orders_handler(request):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, user_id, user_name, total_amount, status, created_at FROM orders ORDER BY created_at DESC")
        orders_data = cursor.fetchall()

        orders = []
        for order in orders_data:
            order_dict = dict(order)
            items = []

            # Для ВОЗВРАЩЕННЫХ заказов ищем в returned_items
            if order_dict['status'] == 'returned':
                cursor.execute("""
                    SELECT 
                        product_id,
                        product_name,
                        image_url,
                        quantity,
                        price,
                        size_id,
                        size_value
                    FROM returned_items 
                    WHERE order_id = ?
                """, (order_dict['id'],))
                items_data = cursor.fetchall()
                items = [dict(item) for item in items_data]

            # Для подтвержденных заказов ищем в sold_products - ИСПРАВЛЕННЫЙ ЗАПРОС
            elif order_dict['status'] == 'confirmed':
                cursor.execute("""
                    SELECT 
                        sp.product_id,
                        sp.name as product_name,
                        sp.image_url,
                        sp.quantity,
                        sp.sold_price as price,
                        sp.size_id,
                        sp.sku,
                        sp.brand,
                        s.value as size_value
                    FROM sold_products sp
                    LEFT JOIN sizes s ON sp.size_id = s.id
                    WHERE sp.order_id = ?
                """, (order_dict['id'],))
                items_data = cursor.fetchall()
                items = [dict(item) for item in items_data]

            # Для отмененных заказов ищем в order_items
            elif order_dict['status'] == 'cancelled':
                cursor.execute("""
                    SELECT 
                        oi.product_id,
                        p.name as product_name,
                        p.image_url,
                        oi.quantity,
                        oi.price,
                        oi.size_id,
                        s.value as size_value
                    FROM order_items oi
                    LEFT JOIN products p ON oi.product_id = p.id
                    LEFT JOIN sizes s ON oi.size_id = s.id
                    WHERE oi.order_id = ?
                """, (order_dict['id'],))
                items_data = cursor.fetchall()
                items = [dict(item) for item in items_data]

            # ДЛЯ PENDING ЗАКАЗОВ
            elif order_dict['status'] == 'pending':
                cursor.execute("""
                    SELECT 
                        oi.product_id,
                        p.name as product_name,
                        p.image_url,
                        oi.quantity,
                        oi.price,
                        oi.size_id,
                        s.value as size_value,
                        p.sku,
                        p.brand
                    FROM order_items oi
                    LEFT JOIN products p ON oi.product_id = p.id
                    LEFT JOIN sizes s ON oi.size_id = s.id
                    WHERE oi.order_id = ?
                """, (order_dict['id'],))
                items_data = cursor.fetchall()
                items = [dict(item) for item in items_data]

            order_dict['items'] = items
            orders.append(order_dict)

        return {'orders': orders}

    except Exception as e:
        print(f"Ошибка при загрузке заказов: {e}")
        import traceback
        traceback.print_exc()
        return {'orders': [], 'error': str(e)}
    finally:
        if conn:
            conn.close()

@require_auth
async def update_order(request):
    order_id = request.match_info['id']
    data = await request.json()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (data['status'], order_id))
    conn.commit()
    conn.close()

    return web.json_response({'status': 'success'})


@require_auth
@aiohttp_jinja2.template('order_detail.html')
async def order_detail_handler(request):
    order_id = request.match_info.get('order_id')
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получаем заказ с полем returned_count
        cursor.execute("""
            SELECT id, user_id, user_name, total_amount, 
                   status, created_at, returned_count
            FROM orders 
            WHERE id = ?
        """, (order_id,))
        order = cursor.fetchone()

        if not order:
            return {'error': 'Заказ не найден'}

        order_dict = dict(order)
        items = []

        # Для всех заказов получаем товары из order_items
        cursor.execute("""
            SELECT 
                oi.id,
                oi.product_id,
                p.name as product_name,
                p.image_url,
                oi.quantity,
                oi.price,
                p.sku,
                p.brand,
                oi.size_id,
                s.value as size_value,
                CASE 
                    WHEN oi.returned IS NULL THEN 0
                    ELSE oi.returned
                END as returned
            FROM order_items oi
            LEFT JOIN products p ON oi.product_id = p.id
            LEFT JOIN sizes s ON oi.size_id = s.id
            WHERE oi.order_id = ?
        """, (order_id,))
        items_data = cursor.fetchall()
        items = [dict(item) for item in items_data]

        return {'order': order_dict, 'items': items}

    except Exception as e:
        print(f"Ошибка при загрузке деталей заказа: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}
    finally:
        if conn:
            conn.close()


@require_auth
async def update_order_status_handler(request):
    """Обновленный обработчик статуса заказа с переносом в sold_products"""
    order_id = request.match_info['id']
    conn = None

    try:
        if request.content_type != 'application/json':
            return web.json_response({
                'success': False,
                'error': 'Invalid Content-Type. Expected application/json'
            }, status=400)

        data = await request.json()
        new_status = data.get('status')

        if not new_status:
            return web.json_response({
                'success': False,
                'error': 'Статус не указан'
            }, status=400)

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Проверяем существование заказа
        cursor.execute("SELECT id, status, user_id FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()

        if not order:
            return web.json_response({
                'success': False,
                'error': f'Заказ с ID {order_id} не найден'
            }, status=404)

        current_status = order['status']
        user_id = order['user_id']

        print(f"🔄 Обновление заказа {order_id} с {current_status} на {new_status}")

        # Если подтверждаем заказ из статуса pending - переносим товары в sold_products
        if new_status == 'confirmed' and current_status == 'pending':
            print(f"🔄 Перенос товаров заказа {order_id} в sold_products")

            # Получаем товары заказа из order_items
            cursor.execute("""
                SELECT oi.product_id, oi.size_id, oi.quantity, oi.price as sold_price
                FROM order_items oi
                WHERE oi.order_id = ?
            """, (order_id,))
            order_items = cursor.fetchall()

            if order_items:
                for item in order_items:
                    product_id, size_id, quantity, sold_price = item

                    # Получаем полную информацию о товаре
                    cursor.execute("""
                        SELECT name, sku, brand, category_id, price, discount_price, 
                               image_url, discount_percent, cost_price
                        FROM products 
                        WHERE id = ?
                    """, (product_id,))
                    product_data = cursor.fetchone()

                    if product_data:
                        (name, sku, brand, category_id, price, discount_price,
                         image_url, discount_percent, cost_price) = product_data

                        # Вставляем в sold_products
                        cursor.execute("""
                            INSERT INTO sold_products 
                            (name, sku, brand, category_id, price, discount_price, size_id, 
                             quantity, image_url, discount_percent, cost_price, order_id, user_id, sold_price)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (name, sku, brand, category_id, price, discount_price, size_id,
                              quantity, image_url, discount_percent, cost_price, order_id, user_id, sold_price))

                        # Уменьшаем количество в products
                        is_null_size = size_id in (None, 0)
                        if is_null_size:
                            cursor.execute("""
                                UPDATE products 
                                SET quantity = quantity - ? 
                                WHERE id = ? AND (size_id IS NULL OR size_id = 0)
                            """, (quantity, product_id))
                        else:
                            cursor.execute("""
                                UPDATE products 
                                SET quantity = quantity - ? 
                                WHERE id = ? AND size_id = ?
                            """, (quantity, product_id, size_id))

                        print(f"  ✅ Товар {product_id} перенесен в sold_products")

        # Если отменяем заказ из статуса pending - возвращаем товары на склад
        elif new_status == 'cancelled' and current_status == 'pending':
            print(f"🔄 Отмена заказа {order_id}, возврат товаров на склад")

            cursor.execute("""
                SELECT product_id, size_id, quantity 
                FROM order_items 
                WHERE order_id = ?
            """, (order_id,))
            order_items = cursor.fetchall()

            for item in order_items:
                product_id, size_id, quantity = item

                is_null_size = size_id in (None, 0)
                if is_null_size:
                    cursor.execute("""
                        UPDATE products
                        SET quantity = quantity + ? 
                        WHERE id = ? AND (size_id IS NULL OR size_id = 0)
                    """, (quantity, product_id))
                else:
                    cursor.execute("""
                        UPDATE products 
                        SET quantity = quantity + ? 
                        WHERE id = ? AND size_id = ?
                    """, (quantity, product_id, size_id))

                print(f"  ✅ Товар {product_id} возвращен на склад")

        # Обновляем статус заказа
        cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
        conn.commit()

        # Обновляем сообщения в Telegram
        admin_username = "веб-админ"
        message_updated = await update_order_messages(order_id, new_status, admin_username)

        return web.json_response({
            'success': True,
            'message': f'Статус заказа {order_id} обновлен на {new_status}',
            'message_updated': message_updated
        })

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Ошибка при обновлении статуса заказа {order_id}: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({
            'success': False,
            'error': f'Внутренняя ошибка сервера: {str(e)}'
        }, status=500)
    finally:
        if conn:
            conn.close()


async def return_order_handler(request):
    """Исправленный обработчик возврата заказа"""
    conn = None
    try:
        order_id = request.match_info.get('id')
        print(f"🔄 Начало возврата заказа #{order_id}")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Получаем информацию о заказе
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            return web.json_response({'success': False, 'error': 'Заказ не найден'})

        order_dict = dict(order)

        # 2. Получаем товары из sold_products
        cursor.execute("""
            SELECT product_id, name, image_url, quantity, sold_price as price, size_id
            FROM sold_products 
            WHERE order_id = ?
        """, (order_id,))

        items = cursor.fetchall()

        if not items:
            return web.json_response({'success': False, 'error': 'Товары в заказе не найдены'})

        returned_count = 0

        # 3. Возвращаем каждый товар на склад
        for item in items:
            item_dict = dict(item)
            product_id = item_dict['product_id']
            product_name = item_dict['name']
            quantity = item_dict['quantity']

            # ЕСЛИ product_id = None, ПОПЫТАЕМСЯ НАЙТИ ТОВАР ПО ИМЕНИ
            if not product_id:
                print(f"🔍 Товар без product_id: '{product_name}', пытаемся найти по имени...")
                cursor.execute("SELECT id FROM products WHERE name = ? LIMIT 1", (product_name,))
                found_product = cursor.fetchone()
                if found_product:
                    product_id = found_product['id']
                    print(f"✅ Найден товар по имени: '{product_name}' -> ID={product_id}")
                else:
                    print(f"❌ Не удалось найти товар по имени: '{product_name}'")

            if product_id:
                print(f"🔄 Возвращаем товар ID={product_id}, название='{product_name}', количество={quantity}")

                # Возвращаем товар на склад
                cursor.execute("""
                    UPDATE products 
                    SET quantity = quantity + ? 
                    WHERE id = ?
                """, (quantity, product_id))

                if cursor.rowcount > 0:
                    returned_count += 1
                    print(f"  ✅ Товар успешно возвращен на склад")
                else:
                    print(f"  ❌ Не удалось обновить количество товара")
            else:
                print(f"  ⚠️ Пропускаем товар без product_id: '{product_name}'")

        # 4. Обновляем статус заказа на 'returned'
        cursor.execute("""
            UPDATE orders 
            SET status = 'returned', 
                returned_count = ?,
                total_amount = 0
            WHERE id = ?
        """, (len(items), order_id))

        print(f"📊 Возвращено товаров на склад: {returned_count} из {len(items)}")

        conn.commit()
        return web.json_response({
            'success': True,
            'returned_items': len(items),
            'message': f'Заказ полностью возвращен. {returned_count} товаров возвращены на склад.'
        })

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Ошибка при возврате заказа: {e}")
        return web.json_response({'success': False, 'error': str(e)})
    finally:
        if conn:
            conn.close()

import html
from datetime import datetime


async def update_order_messages(order_id: int, status: str, admin_username: str):
    """Обновляет сообщения о заказе в Telegram используя sold_products"""
    try:
        from config import TELEGRAM_BOT_TOKEN, GROUP_CHAT_ID, ADMIN_IDS

        print(f"🔍 Начинаем обновление сообщений для заказа #{order_id}")
        print(f"🔍 Статус: {status}, Админ: {admin_username}")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем информацию о заказе
        cursor.execute("""
            SELECT user_id, user_name, total_amount, created_at, group_chat_id, group_message_id
            FROM orders WHERE id = ?
        """, (order_id,))
        order_data = cursor.fetchone()

        if not order_data:
            print(f"❌ Заказ #{order_id} не найден в базе данных")
            return False

        user_id, user_name, total_amount, created_at, group_chat_id, group_message_id = order_data
        print(f"🔍 Данные заказа: user_id={user_id}, group_chat_id={group_chat_id}, group_message_id={group_message_id}")

        # Получаем товары заказа ИЗ ТАБЛИЦЫ SOLD_PRODUCTS
        cursor.execute("""
            SELECT 
                name as product_name, 
                quantity, 
                sold_price as price, 
                size_id,
                (SELECT value FROM sizes WHERE id = sold_products.size_id) as size_name
            FROM sold_products 
            WHERE order_id = ?
        """, (order_id,))
        items = cursor.fetchall()

        print(f"🔍 Найдено товаров в sold_products: {len(items)}")

        if not items:
            print(f"⚠️ В sold_products нет товаров для заказа #{order_id}, пробуем order_items...")
            # Резервный вариант - берем из order_items
            cursor.execute("""
                SELECT 
                    p.name as product_name, 
                    oi.quantity, 
                    oi.price,
                    oi.size_id,
                    s.value as size_name
                FROM order_items oi
                LEFT JOIN products p ON oi.product_id = p.id
                LEFT JOIN sizes s ON oi.size_id = s.id
                WHERE oi.order_id = ?
            """, (order_id,))
            items = cursor.fetchall()
            print(f"🔍 Найдено товаров в order_items: {len(items)}")

        # Форматируем новый текст сообщения
        if status == "confirmed":
            status_header = "ЗАКАЗ ПОДТВЕРЖДЕН"
            status_line = "Статус: ПОДТВЕРЖДЕН"
            action = "подтвердил"
        else:
            status_header = "ЗАКАЗ ОТМЕНЕН"
            status_line = "Статус: ОТМЕНЕН"
            action = "отменил"

        current_time = datetime.now().strftime('%d.%m.%Y | %H:%M')

        # Формируем текст сообщения с названиями товаров
        message_text = (
            f"<b>🌟 {status_header} | #{order_id}</b>\n\n"
            f"<b>👤 КЛИЕНТ</b>\n"
            f"• Пользователь: @{user_name}\n"
            f"• ID: <code>{user_id}</code>\n"
            f"• Время заказа: <code>{created_at}</code>\n\n"
            f"<b>📦 СОСТАВ ЗАКАЗА</b>\n"
        )

        total_quantity = 0
        for i, item in enumerate(items, 1):
            product_name, quantity, price, size_id, size_name = item
            size_display = size_name if size_name else "без размера"
            total_quantity += quantity

            message_text += (
                f"{i}. {product_name} | Размер: {size_display}\n"
                f"   • Кол-во: {quantity} шт.\n"
                f"   • Цена: {price} ₽\n"
            )

        message_text += (
            f"\n<b>💸 TOTAL</b>\n"
            f"• Общее кол-во: {total_quantity} шт.\n"
            f"• <b>Итого: {total_amount} ₽</b>\n\n"
            f"<i>Заказ {action} администратор {admin_username}</i>\n"
            f"<b>{status_line}</b>\n"
            f"<i>Время: {current_time}</i>"
        )

        print(f"📝 Сформирован текст сообщения с {len(items)} товарами")

        # Обновляем сообщения в группе и у админов
        success_count = 0

        # 1. Обновляем в группе
        if group_chat_id and group_message_id:
            try:
                print(f"🔍 Пытаемся обновить сообщение в группе: chat_id={group_chat_id}, message_id={group_message_id}")
                success = await edit_telegram_message(
                    TELEGRAM_BOT_TOKEN,
                    group_chat_id,
                    group_message_id,
                    message_text,
                    remove_keyboard=True
                )
                if success:
                    success_count += 1
                    print(f"✅ Сообщение в группе успешно обновлено")
                else:
                    print(f"❌ Не удалось обновить сообщение в группе")
            except Exception as e:
                print(f"❌ Ошибка обновления сообщения в группе: {e}")
        else:
            print(f"⚠️ Нет данных group_chat_id или group_message_id для заказа #{order_id}")

        # 2. Обновляем у админов
        try:
            cursor.execute("""
                SELECT chat_id, message_id FROM order_messages WHERE order_id = ?
            """, (order_id,))
            admin_messages = cursor.fetchall()
            print(f"🔍 Найдено сообщений у админов: {len(admin_messages)}")

            for chat_id, message_id in admin_messages:
                try:
                    print(f"🔍 Обновляем сообщение у админа: chat_id={chat_id}, message_id={message_id}")
                    success = await edit_telegram_message(
                        TELEGRAM_BOT_TOKEN,
                        chat_id,
                        message_id,
                        message_text,
                        remove_keyboard=True
                    )
                    if success:
                        success_count += 1
                        print(f"✅ Сообщение у админа {chat_id} успешно обновлено")
                    else:
                        print(f"❌ Не удалось обновить сообщение у админа {chat_id}")
                except Exception as e:
                    print(f"❌ Ошибка обновления сообщения у админа {chat_id}: {e}")
        except Exception as e:
            print(f"❌ Ошибка при получении сообщений админов: {e}")

        conn.close()
        print(f"📊 Итог: успешно обновлено {success_count} сообщений")
        return success_count > 0

    except Exception as e:
        print(f"❌ Критическая ошибка в update_order_messages: {e}")
        import traceback
        traceback.print_exc()
        return False


async def edit_telegram_message(bot_token: str, chat_id: str, message_id: int, text: str,
                                remove_keyboard: bool = False):
    """Редактирует сообщение в Telegram с возможностью убрать клавиатуру"""
    import aiohttp
    import json

    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"

    payload = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    # Если нужно убрать клавиатуру
    if remove_keyboard:
        payload['reply_markup'] = json.dumps({'inline_keyboard': []})

    print(f"📤 Отправка запроса к Telegram API:")
    print(f"   URL: {url}")
    print(f"   chat_id: {chat_id}")
    print(f"   message_id: {message_id}")
    print(f"   text_length: {len(text)}")
    print(f"   remove_keyboard: {remove_keyboard}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as response:
                response_text = await response.text()
                print(f"📨 Ответ от Telegram API: статус {response.status}")
                print(f"   Ответ: {response_text}")

                if response.status == 200:
                    result = json.loads(response_text)
                    if result.get('ok'):
                        print(f"✅ Сообщение успешно отредактировано")
                        return True
                    else:
                        error_description = result.get('description', 'Неизвестная ошибка')
                        print(f"❌ Ошибка Telegram API: {error_description}")
                        return False
                else:
                    print(f"❌ HTTP ошибка: {response.status}")
                    return False

    except asyncio.TimeoutError:
        print(f"❌ Таймаут при редактировании сообщения")
        return False
    except Exception as e:
        print(f"❌ Ошибка при редактировании сообщения: {e}")
        return False




async def send_order_confirmation_to_client(order_id: int, admin_username: str = "веб-админ"):
    """Отправляет сообщение клиенту после подтверждения заказа"""
    try:
        from config import TELEGRAM_BOT_TOKEN

        print(f"🔍 Начинаем отправку подтверждения клиенту для заказа #{order_id}")

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получаем информацию о заказе
        cursor.execute("""
            SELECT user_id, user_name, total_amount, created_at
            FROM orders 
            WHERE id = ?
        """, (order_id,))

        order_data = cursor.fetchone()

        if not order_data:
            print(f"❌ Заказ #{order_id} не найден")
            return False

        user_id = order_data['user_id']
        user_name = order_data['user_name']
        total_amount = order_data['total_amount']
        created_at = order_data['created_at']

        print(f"🔍 Данные заказа: user_id={user_id}, user_name={user_name}")

        # ВРЕМЕННОЕ РЕШЕНИЕ: для пользователя maybezxxm используем фиксированный telegram_id
        telegram_id = None
        client_username = user_name

        # Если пользователь maybezxxm, используем известный telegram_id
        if user_name and 'maybezxxm' in user_name.lower():
            telegram_id = 1940348187
            client_username = "maybezxxm"
            print(f"✅ Используем фиксированный telegram_id для maybezxxm: {telegram_id}")
        else:
            # Оригинальная логика поиска для других пользователей
            if user_id:
                cursor.execute("SELECT telegram_id, username FROM users WHERE id = ?", (user_id,))
                user_data = cursor.fetchone()
                if user_data and user_data['telegram_id']:
                    telegram_id = user_data['telegram_id']
                    client_username = user_data['username'] or user_name

            if not telegram_id and user_name:
                clean_username = user_name.lstrip('@')
                cursor.execute("SELECT telegram_id, username FROM users WHERE username = ?", (clean_username,))
                user_data = cursor.fetchone()
                if user_data and user_data['telegram_id']:
                    telegram_id = user_data['telegram_id']
                    client_username = user_data['username'] or user_name

        if not telegram_id:
            print(f"❌ Не удалось найти telegram_id для клиента {user_name} (user_id: {user_id})")
            conn.close()
            return False

        # Получаем товары из заказа
        cursor.execute("""
            SELECT 
                name as product_name, 
                quantity, 
                sold_price as price
            FROM sold_products 
            WHERE order_id = ?
        """, (order_id,))

        items = cursor.fetchall()
        conn.close()

        print(f"🔍 Найдено товаров в заказе: {len(items)}")

        # Форматируем дату
        if isinstance(created_at, str):
            try:
                created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                created_at = created_at

        date_str = created_at.strftime('%d.%m.%Y %H:%M') if isinstance(created_at, datetime) else str(created_at)

        # Формируем детали товаров
        product_details = ""
        for i, item in enumerate(items, 1):
            product_name = item['product_name']
            quantity = item['quantity']
            price = item['price']
            product_details += f"{i}. {product_name}\n   • Количество: {quantity} шт.\n   • Цена: {price} ₽\n"

        # Формируем сообщение для клиента
        message_text = (
            f"🎉 Ваш заказ #{order_id} подтвержден!\n\n"
            f"❤️ Огромное спасибо за ваш заказ!\n\n"
            f"<b>Детали заказа:</b>\n"
            f"🗓️ Дата: {date_str}\n"
            f"👤 Клиент: {client_username}\n\n"
            f"<b>📦 Состав заказа:</b>\n"
            f"{product_details}\n"
            f"<b>💰 Общая сумма: {total_amount} ₽</b>\n\n"
            f"Мы искренне благодарны, что выбрали наш магазин.\n\n"
            f"Администратор @{admin_username} подтвердил ваш заказ.\n"
            f"С любовью, ваша команда Stone 😊\n\n"
            f"P.S. Ждем вас снова! У нас всегда есть что-то особенное для вас!"
        )

        print(f"📤 Отправка подтверждения клиенту {telegram_id}")

        # Отправляем сообщение клиенту
        success = await send_telegram_message(telegram_id, message_text)

        if success:
            print(f"✅ Сообщение подтверждения успешно отправлено клиенту {client_username}")
        else:
            print(f"❌ Не удалось отправить сообщение подтверждения клиенту {client_username}")

        return success

    except Exception as e:
        print(f"❌ Ошибка при отправке подтверждения клиенту: {e}")
        import traceback
        traceback.print_exc()
        return False


async def confirm_order_handler(request):
    """Универсальный обработчик подтверждения заказа"""
    try:
        order_id = request.match_info['id']
        admin_username = "веб-админ"

        print(f"🔍 Начинаем подтверждение заказа #{order_id}")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем данные заказа
        cursor.execute("SELECT user_id, user_name, status FROM orders WHERE id = ?", (order_id,))
        order_data = cursor.fetchone()

        if not order_data:
            return web.json_response({
                'success': False,
                'error': 'Заказ не найден'
            })

        user_id, user_name, current_status = order_data

        if current_status != 'pending':
            return web.json_response({
                'success': False,
                'error': f'Заказ уже был обработан (статус: {current_status})'
            })

        # Получаем товары заказа из order_items
        cursor.execute("""
            SELECT oi.product_id, oi.size_id, oi.quantity, oi.price as sold_price
            FROM order_items oi
            WHERE oi.order_id = ?
        """, (order_id,))
        order_items = cursor.fetchall()

        if not order_items:
            return web.json_response({
                'success': False,
                'error': 'Заказ пуст'
            })

        print(f"🔍 Найдено товаров в заказе: {len(order_items)}")

        # Переносим каждый товар в sold_products с полной информацией
        for item in order_items:
            product_id, size_id, quantity, sold_price = item

            # Получаем полную информацию о товаре из products
            cursor.execute("""
                SELECT name, sku, brand, category_id, price, discount_price, 
                       image_url, discount_percent, cost_price
                FROM products 
                WHERE id = ?
            """, (product_id,))
            product_data = cursor.fetchone()

            if product_data:
                (name, sku, brand, category_id, price, discount_price,
                 image_url, discount_percent, cost_price) = product_data

                # Вставляем полную копию товара в sold_products
                cursor.execute("""
                    INSERT INTO sold_products 
                    (name, product_id, sku, brand, category_id, price, discount_price, size_id, 
                     quantity, image_url, discount_percent, cost_price, order_id, user_id, sold_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, product_id, sku, brand, category_id, price, discount_price, size_id,
                      quantity, image_url, discount_percent, cost_price, order_id, user_id, sold_price))

                # Уменьшаем количество в оригинальном products
                is_null_size = size_id in (None, 0)
                if is_null_size:
                    cursor.execute("""
                        UPDATE products 
                        SET quantity = quantity - ? 
                        WHERE id = ? AND (size_id IS NULL OR size_id = 0)
                    """, (quantity, product_id))
                else:
                    cursor.execute("""
                        UPDATE products 
                        SET quantity = quantity - ? 
                        WHERE id = ? AND size_id = ?
                    """, (quantity, product_id, size_id))

                print(f"✅ Товар {product_id} '{name}' перенесен в sold_products")

        # Обновляем статус заказа
        cursor.execute("""
            UPDATE orders 
            SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (order_id,))

        conn.commit()
        print(f"✅ Заказ #{order_id} подтвержден и товары перенесены в sold_products")

        # Обновляем сообщения в Telegram для группы и админов
        message_updated = await update_order_messages(order_id, "confirmed", admin_username)

        # ОТПРАВЛЯЕМ СООБЩЕНИЕ КЛИЕНТУ
        client_notification_sent = await send_order_confirmation_to_client(order_id, admin_username)

        return web.json_response({
            'success': True,
            'message': f'Заказ #{order_id} подтвержден',
            'message_updated': message_updated,
            'client_notification_sent': client_notification_sent,
            'items_count': len(order_items)
        })

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Ошибка при подтверждении заказа: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)
    finally:
        if conn:
            conn.close()


# async def cancel_order_handler(request):
#     """Обработчик отмены заказа из админки с возвратом товаров на склад"""
#     conn = None
#     try:
#         order_id = request.match_info['id']
#         admin_username = "веб-админ"
#
#         print(f"🔍 Начинаем отмену заказа #{order_id} из админки")
#
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         # Получаем данные заказа
#         cursor.execute("SELECT user_id, user_name, status FROM orders WHERE id = ?", (order_id,))
#         order_data = cursor.fetchone()
#
#         if not order_data:
#             return web.json_response({
#                 'success': False,
#                 'error': 'Заказ не найден'
#             })
#
#         user_id, user_name, current_status = order_data
#
#         if current_status != 'pending':
#             return web.json_response({
#                 'success': False,
#                 'error': f'Заказ уже был обработан (статус: {current_status})'
#             })
#
#         # Получаем товары заказа из order_items
#         cursor.execute("""
#             SELECT oi.product_id, oi.size_id, oi.quantity
#             FROM order_items oi
#             WHERE oi.order_id = ?
#         """, (order_id,))
#         order_items = cursor.fetchall()
#
#         print(f"🔍 Найдено товаров в заказе: {len(order_items)}")
#
#         # # Возвращаем товары на склад
#         # returned_count = 0
#         # for item in order_items:
#         #     product_id, size_id, quantity = item
#         #
#         #     # Увеличиваем количество в оригинальном products
#         #     is_null_size = size_id in (None, 0)
#         #     if is_null_size:
#         #         cursor.execute("""
#         #             UPDATE products
#         #             SET quantity = quantity + ?
#         #             WHERE id = ? AND (size_id IS NULL OR size_id = 0)
#         #         """, (quantity, product_id))
#         #     else:
#         #         cursor.execute("""
#         #             UPDATE products
#         #             SET quantity = quantity + ?
#         #             WHERE id = ? AND size_id = ?
#         #         """, (quantity, product_id, size_id))
#         #
#         #     if cursor.rowcount > 0:
#         #         returned_count += 1
#         #         print(f"✅ Товар {product_id} возвращен на склад, количество: +{quantity}")
#         #     else:
#         #         print(f"⚠️ Не удалось вернуть товар {product_id} на склад")
#
#         # Обновляем статус заказа
#         cursor.execute("""
#             UPDATE orders
#             SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP
#             WHERE id = ?
#         """, (order_id,))
#
#         conn.commit()
#         print(f"✅ Заказ #{order_id} отменен, возвращено товаров: {returned_count}")
#
#         # Обновляем сообщения в Telegram
#         message_updated = await update_order_messages(order_id, "cancelled", admin_username)
#
#         return web.json_response({
#             'success': True,
#             'message': f'Заказ #{order_id} отменен',
#             'message_updated': message_updated,
#             'returned_items': returned_count
#         })
#
#     except Exception as e:
#         if conn:
#             conn.rollback()
#         print(f"❌ Ошибка при отмене заказа: {e}")
#         import traceback
#         traceback.print_exc()
#         return web.json_response({
#             'success': False,
#             'error': str(e)
#         }, status=500)
#     finally:
#         if conn:
#             conn.close()


@require_auth
async def cancel_order_handler(request):
    """Обработчик отмены заказа из админки БЕЗ возврата товаров на склад"""
    conn = None
    try:
        order_id = request.match_info['id']
        admin_username = "веб-админ"

        print(f"🔍 Начинаем отмену заказа #{order_id} из админки")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем данные заказа
        cursor.execute("SELECT user_id, user_name, status FROM orders WHERE id = ?", (order_id,))
        order_data = cursor.fetchone()

        if not order_data:
            return web.json_response({
                'success': False,
                'error': 'Заказ не найден'
            })

        user_id, user_name, current_status = order_data

        if current_status != 'pending':
            return web.json_response({
                'success': False,
                'error': f'Заказ уже был обработан (статус: {current_status})'
            })

        # Получаем товары заказа из order_items (только для логирования)
        cursor.execute("""
            SELECT oi.product_id, oi.size_id, oi.quantity
            FROM order_items oi
            WHERE oi.order_id = ?
        """, (order_id,))
        order_items = cursor.fetchall()

        print(f"🔍 Найдено товаров в заказе: {len(order_items)}")

        # ВАЖНО: НЕ возвращаем товары на склад, так как они никогда не списывались!
        # Для pending-заказов товары остаются на складе до подтверждения
        print(f"ℹ️ Товары НЕ возвращаются на склад, так как заказ был в статусе pending")

        # Обновляем статус заказа
        cursor.execute("""
            UPDATE orders 
            SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (order_id,))

        conn.commit()
        print(f"✅ Заказ #{order_id} отменен. Товары остались на складе (не списывались)")

        # Обновляем сообщения в Telegram
        message_updated = await update_order_messages(order_id, "cancelled", admin_username)

        return web.json_response({
            'success': True,
            'message': f'Заказ #{order_id} отменен',
            'message_updated': message_updated,
            'returned_items': 0  # Ничего не возвращали
        })

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Ошибка при отмене заказа: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)
    finally:
        if conn:
            conn.close()



@require_auth
async def process_return_handler(request):
    return_id = request.match_info['id']

    try:
        data = await request.json()
        action = data.get('action')

        if action not in ['approved', 'rejected']:
            return web.json_response({'error': 'Неверное действие'}, status=400)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем информацию о возврате
        cursor.execute("""
            SELECT order_id, product_id, size_id, quantity 
            FROM returns 
            WHERE id = ? AND status = 'pending'
        """, (return_id,))
        return_data = cursor.fetchone()

        if not return_data:
            return web.json_response({'error': 'Возврат не найден или уже обработан'}, status=400)

        order_id, product_id, size_id, quantity = return_data

        # Если возврат одобрен, вернем товар на склад
        if action == 'approved':
            if size_id:
                cursor.execute("""
                    UPDATE products 
                    SET quantity = quantity + ? 
                    WHERE id = ? AND size_id = ?
                """, (quantity, product_id, size_id))
            else:
                cursor.execute("""
                    UPDATE products 
                    SET quantity = quantity + ? 
                    WHERE id = ? AND size_id IS NULL
                """, (quantity, product_id))

        # Обновляем статус возврата
        cursor.execute("""
            UPDATE returns 
            SET status = ?, processed_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (action, return_id))

        conn.commit()
        return web.json_response({'success': True})

    except Exception as e:
        print(f"Ошибка при обработке возврата: {e}")
        return web.json_response({'error': str(e)}, status=500)
    finally:
        if conn:
            conn.close()


def get_chat_ids_from_db():
    """Получает список chat_id активных пользователей"""
    conn = sqlite3.connect('data/shop.db')  # Убедитесь, что путь правильный
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT telegram_chat_id FROM users WHERE is_active = TRUE AND telegram_chat_id IS NOT NULL")
        chat_ids = [row[0] for row in cursor.fetchall()]
        return chat_ids
    except Exception as e:
        print(f"Ошибка получения chat_ids: {e}")
        return []
    finally:
        conn.close()

async def get_bot_users_count() -> int:
    """Получает количество пользователей бота"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Сначала пробуем найти в таблице users
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'telegram_chat_id' in columns:
            cursor.execute("SELECT COUNT(*) FROM users WHERE telegram_chat_id IS NOT NULL AND telegram_chat_id != ''")
            count = cursor.fetchone()[0]
            return count

        # Пробуем таблицу bot_users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_users'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM bot_users")
            count = cursor.fetchone()[0]
            return count

        # Если нет специальной таблицы, считаем всех пользователей
        cursor.execute("SELECT COUNT(*) FROM users")
        return cursor.fetchone()[0]

    except Exception as e:
        print(f"Ошибка при подсчете пользователей: {e}")
        return 0
    finally:
        conn.close()


@require_auth
@aiohttp_jinja2.template('notifications.html')
async def notifications_page(request):
    """Страница управления уведомлениями"""
    try:
        # Получаем количество пользователей
        total_users = len(get_chat_ids_from_db())

        # Получаем историю уведомлений
        notifications = get_notifications_from_db(limit=10)

        online_users = get_online_users_count()

        return {
            'active_page': 'notifications',
            'total_users': total_users,
            'notifications': notifications,
            'online_users': online_users
        }

    except Exception as e:
        print(f"Ошибка при загрузке страницы уведомлений: {e}")
        return {
            'active_page': 'notifications',
            'total_users': 0,
            'notifications': [],
            'online_users': 0,
            'error': str(e)
        }


# Функция для отправки сообщения через бота
# Глобальная переменная для бота
bot_instance = None


def set_bot(bot):
    global bot_instance
    bot_instance = bot


# В начале файла добавьте импорт
from bot_init import get_bot, init_bot


async def send_telegram_message(chat_id, message):
    """Улучшенная функция отправки текстовых сообщений в Telegram"""
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        print("❌ Токен бота не настроен в config.py")
        return False

    try:
        # Проверяем валидность chat_id
        if not chat_id or not isinstance(chat_id, (int, str)):
            print(f"❌ Неверный chat_id: {chat_id}")
            return False

        # Лимит сообщения для Telegram
        if len(message) > 4096:
            message = message[:4090] + "..."  # Обрезаем если слишком длинное

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }

        print(f"📤 Отправка текстового сообщения для chat_id {chat_id}")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as response:
                response_text = await response.text()
                print(f"📨 Ответ Telegram API: Status {response.status}")

                # Проверяем статус код
                if response.status != 200:
                    print(f"❌ Telegram API вернул статус {response.status}")
                    print(f"Полный ответ: {response_text}")
                    return False

                # Пытаемся распарсить JSON
                try:
                    result = json.loads(response_text)
                    if result.get('ok'):
                        print(f"✅ Текстовое сообщение отправлено успешно для chat_id {chat_id}")
                        return True
                    else:
                        error_description = result.get('description', 'Неизвестная ошибка')
                        print(f"❌ Ошибка Telegram API: {error_description}")
                        return False
                except json.JSONDecodeError as e:
                    print(f"❌ Ошибка парсинга JSON от Telegram: {e}")
                    return False

    except asyncio.TimeoutError:
        print("❌ Таймаут при отправке сообщения в Telegram")
        return False
    except aiohttp.ClientError as e:
        print(f"❌ Ошибка сети при отправке в Telegram: {e}")
        return False
    except Exception as e:
        print(f"❌ Критическая ошибка при отправке текстового уведомления: {e}")
        return False



async def send_telegram_photo(chat_id, message, image_data, image_filename, image_content_type):
    """Функция отправки фото с подписью в Telegram"""
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        print("❌ Токен бота не настроен в config.py")
        return False

    try:
        # Проверяем валидность chat_id
        if not chat_id or not isinstance(chat_id, (int, str)):
            print(f"❌ Неверный chat_id: {chat_id}")
            return False

        # Лимит подписи для Telegram
        if len(message) > 1024:
            caption = message[:1020] + "..."
        else:
            caption = message

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

        # Создаем FormData для отправки фото
        form_data = aiohttp.FormData()
        form_data.add_field('chat_id', str(chat_id))
        form_data.add_field('caption', caption)
        form_data.add_field('parse_mode', 'HTML')

        # Добавляем изображение как байты
        form_data.add_field(
            'photo',
            image_data,
            filename=image_filename,
            content_type=image_content_type
        )

        print(f"📤 Отправка фото с подписью для chat_id {chat_id}")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data, timeout=30) as response:
                response_text = await response.text()
                print(f"📨 Ответ Telegram API (photo): Status {response.status}")

                # Проверяем статус код
                if response.status != 200:
                    print(f"❌ Telegram API вернул статус {response.status}")
                    print(f"Полный ответ: {response_text[:500]}...")
                    return False

                # Пытаемся распарсить JSON
                try:
                    result = json.loads(response_text)
                    if result.get('ok'):
                        print(f"✅ Фото с подписью отправлено успешно для chat_id {chat_id}")
                        return True
                    else:
                        error_description = result.get('description', 'Неизвестная ошибка')
                        print(f"❌ Ошибка Telegram API при отправке фото: {error_description}")
                        return False
                except json.JSONDecodeError as e:
                    print(f"❌ Ошибка парсинга JSON от Telegram: {e}")
                    return False

    except asyncio.TimeoutError:
        print("❌ Таймаут при отправке фото в Telegram")
        return False
    except aiohttp.ClientError as e:
        print(f"❌ Ошибка сети при отправке фото в Telegram: {e}")
        return False
    except Exception as e:
        print(f"❌ Критическая ошибка при отправке фото: {e}")
        import traceback
        traceback.print_exc()
        return False


# Обработчики API
async def send_notification_handler(request):
    """Обработчик отправки уведомлений с поддержкой FormData и JSON"""
    try:
        print("=== НАЧАЛО ОБРАБОТКИ УВЕДОМЛЕНИЯ ===")

        # Определяем тип контента и парсим данные
        content_type = request.headers.get('Content-Type', '')

        message = ''
        notification_type = 'general'
        images_data = []  # Список для хранения данных изображений
        product_data = None  # Данные о товаре для кнопки

        if 'multipart/form-data' in content_type:
            # Обработка FormData (с изображениями)
            data = await request.post()
            message = data.get('message', '').strip()
            notification_type = data.get('type', 'general')

            # Проверяем, нужно ли добавить кнопку товара
            add_product_button = data.get('add_product_button') == 'true'
            if add_product_button:
                product_name = data.get('product_name', '').strip()
                product_price = data.get('product_price', '').strip()
                product_id = data.get('product_id', '').strip() or str(uuid.uuid4())[:8]

                if not product_name or not product_price:
                    return web.json_response({
                        'success': False,
                        'error': 'При добавлении кнопки "Купить" необходимо указать название и цену товара'
                    })

                try:
                    product_price = float(product_price)
                except ValueError:
                    return web.json_response({
                        'success': False,
                        'error': 'Неверный формат цены товара'
                    })

                product_data = {
                    'id': product_id,
                    'name': product_name,
                    'price': product_price
                }
                print(f"🛍️ Добавлена кнопка товара: {product_name} - {product_price} руб.")

            # Получаем все изображения
            images = data.getall('images', [])
            print(f"Получено изображений: {len(images)}")

            # Проверяем, что при кнопке товара только одно изображение
            if product_data and len(images) != 1:
                return web.json_response({
                    'success': False,
                    'error': 'Для добавления кнопки "Купить" необходимо выбрать ровно одно изображение'
                })

            for i, image_file in enumerate(images):
                if hasattr(image_file, 'file'):
                    # Читаем содержимое файла в память
                    image_file.file.seek(0)  # Перематываем на начало
                    image_data = image_file.file.read()
                    images_data.append({
                        'data': image_data,
                        'filename': image_file.filename,
                        'content_type': image_file.content_type
                    })
                    print(f"Изображение {i + 1}: {image_file.filename}, размер: {len(image_data)} байт")

        elif 'application/json' in content_type:
            # Обработка JSON (без изображений)
            data = await request.json()
            message = data.get('message', '').strip()
            notification_type = data.get('type', 'general')
            print("Получен JSON запрос без изображений")
        else:
            return web.json_response({
                'success': False,
                'error': f'Неподдерживаемый Content-Type: {content_type}'
            })

        print(f"Получено: {message}, тип: {notification_type}")

        if not message:
            return web.json_response({
                'success': False,
                'error': 'Текст уведомления не может быть пустым'
            })

        # Получаем список пользователей
        chat_ids = get_chat_ids_from_db()
        print(f"Найдено пользователей: {len(chat_ids)}")

        if not chat_ids:
            return web.json_response({
                'success': False,
                'error': 'Нет активных пользователей для рассылки'
            })

        # Форматируем сообщение
        prefixes = {
            'sale': ' <b></b>\n\n',
            'new_arrivals': ' <b></b>\n\n',
            'important': ' <b></b>\n\n',
            'technical': ' <b>ТЕХНИЧЕСКИЕ РАБОТЫ</b>\n\n',
            'general': '<b></b>\n\n'
        }
        prefix = prefixes.get(notification_type, ' <b></b>\n\n')
        formatted_message = prefix + message

        # Добавляем информацию о товаре в сообщение если есть
        if product_data:
            formatted_message += f"\n\n🎱 <b>{product_data['name']}</b>\n💰 Цена: {product_data['price']} руб."

        # Отправляем уведомления
        success_count = 0
        fail_count = 0

        print("Начинаем рассылку...")

        for i, chat_id in enumerate(chat_ids):
            print(f"Отправка {i + 1}/{len(chat_ids)}: {chat_id}")

            if images_data:
                # Отправка с изображениями
                if len(images_data) == 1 and product_data:
                    # Одно изображение с кнопкой товара
                    success = await send_telegram_photo_with_button(
                        chat_id,
                        formatted_message,
                        images_data[0]['data'],
                        images_data[0]['filename'],
                        images_data[0]['content_type'],
                        product_data
                    )
                elif len(images_data) == 1:
                    # Одно изображение без кнопки
                    success = await send_telegram_photo(
                        chat_id,
                        formatted_message,
                        images_data[0]['data'],
                        images_data[0]['filename'],
                        images_data[0]['content_type']
                    )
                else:
                    # Несколько изображений - отправляем как медиагруппу
                    success = await send_telegram_media_group(
                        chat_id,
                        formatted_message,
                        images_data
                    )
            else:
                # Отправка только текста
                success = await send_telegram_message(chat_id, formatted_message)

            if success:
                success_count += 1
                print(f"✅ Успешно: {chat_id}")
            else:
                fail_count += 1
                print(f"❌ Ошибка: {chat_id}")

        # Сохраняем в базу
        notification_id = save_notification_to_db(
            notification_type,
            message,
            success_count,
            fail_count
        )

        print(f"=== РЕЗУЛЬТАТ: Успешно: {success_count}, Ошибок: {fail_count} ===")

        return web.json_response({
            'success': True,
            'sent_count': success_count,
            'success_count': success_count,
            'fail_count': fail_count,
            'image_count': len(images_data),
            'total_users': len(chat_ids),
            'notification_id': notification_id
        })

    except Exception as e:
        print(f"❌ Критическая ошибка при отправке уведомления: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({'success': False, 'error': str(e)})


async def send_telegram_photo_with_button(chat_id, message, image_data, image_filename, image_content_type,
                                          product_data):
    """Функция отправки фото с подписью и кнопкой "Купить" """
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        print("❌ Токен бота не настроен в config.py")
        return False

    try:
        # Проверяем валидность chat_id
        if not chat_id or not isinstance(chat_id, (int, str)):
            print(f"❌ Неверный chat_id: {chat_id}")
            return False

        # Лимит подписи для Telegram
        if len(message) > 1024:
            caption = message[:1020] + "..."
        else:
            caption = message

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

        # ОПРЕДЕЛЯЕМ ПРАВИЛЬНЫЙ ФОРМАТ callback_data
        product_id = product_data['id']

        # Получаем информацию о категории товара
        category_info = get_product_category_info(product_id)

        if category_info and category_info.get('category_id') == 8:  # Аксессуары
            # Для аксессуаров - добавление сразу без размера
            callback_data = f"add_{product_id}_0"
        else:
            # Для других товаров - выбор размера
            callback_data = f"select_size_{product_id}"

        keyboard = {
            'inline_keyboard': [[
                {
                    'text': f'🛒 Купить за {product_data["price"]} руб.',
                    'callback_data': callback_data
                }
            ]]
        }

        form_data = aiohttp.FormData()
        form_data.add_field('chat_id', str(chat_id))
        form_data.add_field('caption', caption)
        form_data.add_field('parse_mode', 'HTML')
        form_data.add_field('reply_markup', json.dumps(keyboard))
        form_data.add_field(
            'photo',
            image_data,
            filename=image_filename,
            content_type=image_content_type
        )

        print(f"📤 Отправка фото с кнопкой 'Купить' для chat_id {chat_id}")
        print(f"📦 Product ID: {product_id}, Category: {category_info}")
        print(f"🔘 Callback data: {callback_data}")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data, timeout=30) as response:
                response_text = await response.text()
                print(f"📨 Ответ Telegram API (photo with button): Status {response.status}")

                if response.status != 200:
                    print(f"❌ Telegram API вернул статус {response.status}")
                    print(f"Полный ответ: {response_text[:500]}...")
                    return False

                try:
                    result = json.loads(response_text)
                    if result.get('ok'):
                        print(f"✅ Фото с кнопкой 'Купить' отправлено успешно для chat_id {chat_id}")
                        return True
                    else:
                        error_description = result.get('description', 'Неизвестная ошибка')
                        print(f"❌ Ошибка Telegram API при отправке фото с кнопкой: {error_description}")
                        return False
                except json.JSONDecodeError as e:
                    print(f"❌ Ошибка парсинга JSON от Telegram: {e}")
                    return False

    except Exception as e:
        print(f"❌ Критическая ошибка при отправке фото с кнопкой: {e}")
        import traceback
        traceback.print_exc()
        return False

async def send_telegram_media_group(chat_id, message, images_data):
    """Функция отправки медиагруппы в Telegram"""
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        print("❌ Токен бота не настроен в config.py")
        return False

    try:
        # Проверяем валидность chat_id
        if not chat_id or not isinstance(chat_id, (int, str)):
            print(f"❌ Неверный chat_id: {chat_id}")
            return False

        # Лимит подписи для Telegram
        if len(message) > 1024:
            caption = message[:1020] + "..."
        else:
            caption = message

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"

        # Создаем FormData для отправки медиагруппы
        form_data = aiohttp.FormData()
        form_data.add_field('chat_id', str(chat_id))

        # Формируем медиагруппу
        media = []
        for i, img_data in enumerate(images_data):
            if i == 0:
                # Первое изображение с подписью
                media.append({
                    'type': 'photo',
                    'media': f'attach://photo_{i}',
                    'caption': caption,
                    'parse_mode': 'HTML'
                })
            else:
                # Остальные изображения без подписи
                media.append({
                    'type': 'photo',
                    'media': f'attach://photo_{i}'
                })

        form_data.add_field('media', json.dumps(media))

        # Добавляем изображения
        for i, img_data in enumerate(images_data):
            form_data.add_field(
                f'photo_{i}',
                img_data['data'],
                filename=img_data['filename'],
                content_type=img_data['content_type']
            )

        print(f"📤 Отправка медиагруппы ({len(images_data)} фото) для chat_id {chat_id}")

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=form_data, timeout=30) as response:
                response_text = await response.text()
                print(f"📨 Ответ Telegram API (media group): Status {response.status}")

                # Проверяем статус код
                if response.status != 200:
                    print(f"❌ Telegram API вернул статус {response.status}")
                    print(f"Полный ответ: {response_text[:500]}...")
                    return False

                # Пытаемся распарсить JSON
                try:
                    result = json.loads(response_text)
                    if result.get('ok'):
                        print(f"✅ Медиагруппа отправлена успешно для chat_id {chat_id}")
                        return True
                    else:
                        error_description = result.get('description', 'Неизвестная ошибка')
                        print(f"❌ Ошибка Telegram API при отправке медиагруппы: {error_description}")
                        return False
                except json.JSONDecodeError as e:
                    print(f"❌ Ошибка парсинга JSON от Telegram: {e}")
                    return False

    except asyncio.TimeoutError:
        print("❌ Таймаут при отправке медиагруппы в Telegram")
        return False
    except aiohttp.ClientError as e:
        print(f"❌ Ошибка сети при отправке медиагруппы в Telegram: {e}")
        return False
    except Exception as e:
        print(f"❌ Критическая ошибка при отправке медиагруппы: {e}")
        import traceback
        traceback.print_exc()
        return False


async def notification_history_handler(request):
    """Получение истории уведомлений"""
    try:
        limit = int(request.query.get('limit', 10))
        notifications = get_notifications_from_db(limit)

        return web.json_response({
            'success': True,
            'notifications': notifications
        })

    except Exception as e:
        print(f"Ошибка при получении истории уведомлений: {e}")
        return web.json_response({'success': False, 'error': str(e)})





# Вспомогательные функции
def format_message_for_telegram(message: str, notification_type: str) -> str:
    """Форматирует сообщение для Telegram"""
    prefixes = {
        'sale': ' <b>АКЦИЯ!</b>\n\n',
        'new_arrivals': ' <b>НОВЫЕ ПОСТУПЛЕНИЯ!</b>\n\n',
        'important': ' <b>ВАЖНАЯ ИНФОРМАЦИЯ!</b>\n\n',
        'general': ' <b>УВЕДОМЛЕНИЕ</b>\n\n'
    }

    prefix = prefixes.get(notification_type, ' <b>УВЕДОМЛЕНИЕ</b>\n\n')
    return prefix + message


def is_recent(date_string: str, days: int) -> bool:
    """Проверяет, является ли дата recent (в пределах days дней)"""
    try:
        if isinstance(date_string, str):
            notification_date = datetime.strptime(date_string.split('.')[0], '%Y-%m-%d %H:%M:%S')
        else:
            notification_date = date_string

        delta = datetime.now() - notification_date
        return delta.days <= days
    except:
        return False


def calculate_delivery_rate(notifications: List[Dict]) -> float:
    """Рассчитывает средний процент доставки"""
    if not notifications:
        return 0.0

    total_success = sum(n['success_count'] for n in notifications)
    total_fail = sum(n['fail_count'] for n in notifications)
    total = total_success + total_fail

    if total == 0:
        return 0.0

    return round((total_success / total) * 100, 1)


async def debug_telegram_api():
    """Функция для диагностики Telegram API"""
    import aiohttp
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        return {"error": "Токен бота не настроен"}

    # Проверяем базовую информацию о боте
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                response_text = await response.text()
                print(f"=== DEBUG TELEGRAM API ===")
                print(f"Status: {response.status}")
                print(f"Headers: {dict(response.headers)}")
                print(f"Response: {response_text[:500]}...")  # Первые 500 символов

                # Пробуем распарсить JSON
                try:
                    json_data = await response.json()
                    return {
                        "status": response.status,
                        "json_parsed": True,
                        "data": json_data
                    }
                except Exception as e:
                    return {
                        "status": response.status,
                        "json_parsed": False,
                        "raw_response": response_text,
                        "error": str(e)
                    }

    except Exception as e:
        return {"error": f"Ошибка соединения: {str(e)}"}

@require_auth
async def debug_bot(request):
    """Страница диагностики бота"""
    debug_info = await debug_telegram_api()
    return web.json_response(debug_info)


import aiohttp
import json
import logging

# Настройка логгера
logger = logging.getLogger(__name__)


async def debug_telegram_bot():
    """Диагностика бота Telegram"""
    from config import TELEGRAM_BOT_TOKEN

    if not TELEGRAM_BOT_TOKEN:
        return {"error": "❌ Токен не настроен в config.py"}

    # Проверяем формат токена
    if not TELEGRAM_BOT_TOKEN.startswith('bot'):
        return {"error": f"❌ Неверный формат токена. Должен начинаться с 'bot'"}

    # Проверяем API бота
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                response_text = await response.text()

                print("=== ДИАГНОСТИКА TELEGRAM BOT ===")
                print(f"URL: {url}")
                print(f"Status: {response.status}")
                print(f"Response: {response_text}")

                try:
                    result = json.loads(response_text)
                    if result.get('ok'):
                        bot_info = result.get('result', {})
                        return {
                            "status": "✅ Бот доступен",
                            "bot_username": bot_info.get('username'),
                            "bot_name": bot_info.get('first_name'),
                            "can_join_groups": bot_info.get('can_join_groups'),
                            "can_read_all_group_messages": bot_info.get('can_read_all_group_messages'),
                            "supports_inline_queries": bot_info.get('supports_inline_queries')
                        }
                    else:
                        return {
                            "status": "❌ Ошибка бота",
                            "error": result.get('description', 'Неизвестная ошибка')
                        }
                except json.JSONDecodeError:
                    return {
                        "status": "❌ Невалидный JSON ответ",
                        "raw_response": response_text
                    }

    except Exception as e:
        return {"error": f"❌ Ошибка соединения: {str(e)}"}


async def test_send_to_me():
    """Тестовая отправка себе"""
    from config import TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID

    if not TELEGRAM_BOT_TOKEN:
        return {"error": "Токен не настроен"}

    if not ADMIN_CHAT_ID:
        return {"error": "ADMIN_CHAT_ID не настроен"}

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': ADMIN_CHAT_ID,
        'text': '🧪 <b>Тестовое сообщение от бота</b>\n\nЕсли вы видите это сообщение, бот работает корректно!',
        'parse_mode': 'HTML'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as response:
                response_text = await response.text()
                print(f"Тестовая отправка: Status {response.status}")
                print(f"Response: {response_text}")

                try:
                    result = json.loads(response_text)
                    if result.get('ok'):
                        return {"status": "✅ Тестовое сообщение отправлено"}
                    else:
                        return {"error": f"❌ Ошибка: {result.get('description')}"}
                except:
                    return {"error": f"❌ Ошибка парсинга: {response_text}"}

    except Exception as e:
        return {"error": f"❌ Ошибка отправки: {str(e)}"}


@require_auth
async def get_discounted_products(request):
    """Получение товаров со скидками"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # ИСПРАВЛЕННЫЙ ЗАПРОС - добавлен JOIN с таблицей sizes
        cursor.execute("""
            SELECT 
                p.id, p.name, p.price, p.sku, p.image_url, 
                p.discount_percent, p.quantity, p.brand,
                c.name as category_name,
                s.value as size_name,  -- Получаем значение размера из таблицы sizes
                CASE 
                    WHEN p.discount_percent > 0 THEN 
                        ROUND(p.price * (1 - p.discount_percent / 100.0))
                    ELSE p.price
                END as discount_price
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN sizes s ON p.size_id = s.id  -- JOIN с таблицей размеров
            WHERE p.discount_percent > 0
            ORDER BY p.discount_percent DESC
        """)

        products_data = cursor.fetchall()

        # ДОБАВЬТЕ ОТЛАДОЧНЫЙ ВЫВОД
        print("=== ДЕБАГ ТОВАРОВ СО СКИДКОЙ ===")
        for row in products_data:
            product_dict = dict(row)
            print(f"Товар: {product_dict['name']}, Размер: {product_dict.get('size_name', 'NO FIELD')}, Quantity: {product_dict.get('quantity', 'NO FIELD')}")
        print("=== КОНЕЦ ДЕБАГА ===")

        products = []
        for row in products_data:
            product = dict(row)

            # Обработка изображений
            image_url = product.get('image_url', '')
            product['main_image'] = None
            product['has_image'] = False

            if image_url and image_url != 'None' and image_url != 'null' and image_url.strip():
                if image_url.strip().startswith('['):
                    try:
                        images = json.loads(image_url)
                        if images and len(images) > 0:
                            product['main_image'] = images[0]
                            product['has_image'] = True
                    except json.JSONDecodeError:
                        product['main_image'] = image_url
                        product['has_image'] = True
                else:
                    product['main_image'] = image_url
                    product['has_image'] = True

            products.append(product)

        conn.close()

        return web.json_response({
            'success': True,
            'products': products
        })

    except Exception as e:
        print(f"Ошибка при получении товаров со скидками: {e}")
        return web.json_response({
            'success': False,
            'error': str(e)
        })


async def send_discounts_notification_handler(request):
    """Отправка уведомлений о скидках для выбранных товаров"""
    try:
        data = await request.json()
        product_ids = data.get('product_ids', [])

        if not product_ids:
            return web.json_response({
                'success': False,
                'error': 'Не выбраны товары для рассылки'
            })

        # Получаем информацию о выбранных товарах
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        placeholders = ','.join('?' * len(product_ids))

        # ИСПРАВЛЕННЫЙ ЗАПРОС - добавлен JOIN с таблицей sizes
        cursor.execute(f"""
            SELECT 
                p.id, p.name, p.price, p.image_url, p.discount_percent,
                p.category_id, p.quantity, p.brand,
                c.name as category_name,
                s.value as size_name,  -- Получаем значение размера
                ROUND(p.price * (1 - p.discount_percent / 100.0)) as discount_price
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN sizes s ON p.size_id = s.id  -- JOIN с таблицей размеров
            WHERE p.id IN ({placeholders})
        """, product_ids)

        products_data = cursor.fetchall()
        conn.close()

        if not products_data:
            return web.json_response({
                'success': False,
                'error': 'Товары не найдены'
            })

        # ДОБАВИМ ОТЛАДКУ ДЛЯ ПРОВЕРКИ ДАННЫХ
        print("=== ДЕБАГ: ДАННЫЕ ТОВАРОВ ДЛЯ РАССЫЛКИ ===")
        for product in products_data:
            product_dict = dict(product)
            print(
                f"Товар: {product_dict['name']}, Размер: {product_dict.get('size_name')}, Quantity: {product_dict.get('quantity')}")
        print("=== КОНЕЦ ДЕБАГА ===")

        # Остальной код функции остается без изменений...
        # Получаем список пользователей
        chat_ids = get_chat_ids_from_db()

        if not chat_ids:
            return web.json_response({
                'success': False,
                'error': 'Нет активных пользователей для рассылки'
            })

        success_count = 0
        fail_count = 0

        # Отправляем уведомления
        for chat_id in chat_ids:
            try:
                # Отправляем каждый товар отдельным сообщением
                for product in products_data:
                    product_dict = dict(product)

                    # Формируем сообщение
                    message = await format_discount_message(product_dict)

                    # Определяем правильный callback_data в зависимости от категории
                    category_id = product_dict.get('category_id')

                    # Для аксессуаров (category_id = 8) отправляем без размера
                    # Для других категорий - возможно, нужно будет доработать
                    callback_data = f"add_{product_dict['id']}"

                    # Отправляем сообщение
                    if product_dict.get('image_url'):
                        # Пытаемся отправить с изображением
                        image_success = await send_product_with_image_custom(
                            chat_id,
                            message,
                            product_dict,
                            callback_data
                        )
                        if not image_success:
                            # Если не удалось с изображением, отправляем текстом
                            text_success = await send_telegram_message(chat_id, message)
                            if text_success:
                                success_count += 1
                            else:
                                fail_count += 1
                        else:
                            success_count += 1
                    else:
                        # Только текст
                        text_success = await send_telegram_message(chat_id, message)
                        if text_success:
                            success_count += 1
                        else:
                            fail_count += 1

                    # Небольшая задержка между сообщениями
                    await asyncio.sleep(0.5)

            except Exception as e:
                print(f"Ошибка отправки пользователю {chat_id}: {e}")
                fail_count += 1

        # Сохраняем в историю
        notification_id = save_notification_to_db(
            'sale',
            f'Рассылка о скидках на {len(products_data)} товаров',
            success_count,
            fail_count
        )

        return web.json_response({
            'success': True,
            'sent_count': success_count,
            'fail_count': fail_count,
            'products_count': len(products_data),
            'total_users': len(chat_ids)
        })

    except Exception as e:
        print(f"Ошибка при отправке уведомлений о скидках: {e}")
        return web.json_response({
            'success': False,
            'error': str(e)
        })


async def send_product_with_image_custom(chat_id, message, product, callback_data):
    """Отправляет товар с изображением и кастомной callback_data"""
    from config import TELEGRAM_BOT_TOKEN

    if not product.get('image_url'):
        return False

    try:
        # Скачиваем изображение
        image_url = product['image_url']
        if image_url.startswith('['):
            try:
                images = json.loads(image_url)
                if images:
                    image_url = images[0]
            except:
                pass

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()

                    # Определяем тип контента
                    content_type = response.headers.get('Content-Type', 'image/jpeg')
                    filename = f"product_{product['id']}.jpg"

                    # ИСПРАВЛЕННАЯ ЛОГИКА: Определяем правильный callback_data на основе категории
                    category_id = product.get('category_id')
                    if category_id and category_id != 8:  # Если товар требует размера
                        callback_data = f"select_size_{product['id']}"  # ← ИСПРАВЛЕНО
                    else:
                        # Для товаров без размера используем стандартный формат с size_id=0
                        callback_data = f"add_{product['id']}_0"

                    keyboard = {
                        'inline_keyboard': [[
                            {
                                'text': f'🛒 Купить за {int(float(product["discount_price"]))}₽',
                                'callback_data': callback_data
                            }
                        ]]
                    }

                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                    form_data = aiohttp.FormData()
                    form_data.add_field('chat_id', str(chat_id))
                    form_data.add_field('caption', message)
                    form_data.add_field('parse_mode', 'HTML')
                    form_data.add_field('reply_markup', json.dumps(keyboard))
                    form_data.add_field(
                        'photo',
                        image_data,
                        filename=filename,
                        content_type=content_type
                    )

                    # Добавьте отладочный вывод
                    print(f"🟢 ОТПРАВКА ЧЕРЕЗ send_product_with_image_custom")
                    print(f"📦 Product ID: {product['id']}, Category: {category_id}")
                    print(f"🔘 Callback data: {callback_data}")

                    async with session.post(url, data=form_data, timeout=30) as tg_response:
                        return tg_response.status == 200

    except Exception as e:
        print(f"Ошибка отправки изображения: {e}")
        return False

    return False


async def format_discount_message(product):
    """Форматирует сообщение о скидке на товар в стиле каталога"""
    # Безопасное получение и форматирование цен
    old_price = float(product.get('price', 0))
    discount_percent = int(product.get('discount_percent', 0))

    # Правильно рассчитываем новую цену
    new_price = old_price * (1 - discount_percent / 100)
    economy = old_price - new_price

    # Форматирование цен
    old_price_formatted = f"{int(old_price):,} ₽".replace(',', ' ')
    new_price_formatted = f"{int(new_price):,} ₽".replace(',', ' ')
    economy_formatted = f"{int(economy):,} ₽".replace(',', ' ')

    # Получаем информацию о размере и количестве
    size_name = product.get('size_name', '')
    quantity = product.get('quantity', 1)

    message = f"📉 <b>СКИДКА {discount_percent}%!</b>\n\n"
    message += f"<b>{product['name']}</b>\n\n"

    message += f"💵 Цена: <s>{old_price_formatted}</s> <b>{new_price_formatted}</b>\n"
    message += f"🔥 Экономия: {economy_formatted}\n"

    if size_name and size_name != 'без размера':
        message += f"🎱 Размер: {size_name}\n"

    message += f"📦 В наличии: {quantity} шт."

    return message


async def send_product_with_image(chat_id, message, product):
    """Отправляет товар с изображением и кнопкой"""
    from config import TELEGRAM_BOT_TOKEN

    if not product.get('image_url'):
        return False

    try:
        # Скачиваем изображение
        image_url = product['image_url']
        if image_url.startswith('['):
            try:
                images = json.loads(image_url)
                if images:
                    image_url = images[0]
            except:
                pass

        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()

                    # Определяем тип контента
                    content_type = response.headers.get('Content-Type', 'image/jpeg')
                    filename = f"product_{product['id']}.jpg"

                    # Создаем клавиатуру с кнопкой "Купить"
                    # Используем ваш формат: add_{product_id} (без size_id для начала)
                    keyboard = {
                        'inline_keyboard': [[
                            {
                                'text': f'🛒 Купить за {int(float(product["discounted_price"]))}₽',
                                'callback_data': f'add_{product["id"]}'
                            }
                        ]]
                    }

                    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                    form_data = aiohttp.FormData()
                    form_data.add_field('chat_id', str(chat_id))
                    form_data.add_field('caption', message)
                    form_data.add_field('parse_mode', 'HTML')
                    form_data.add_field('reply_markup', json.dumps(keyboard))
                    form_data.add_field(
                        'photo',
                        image_data,
                        filename=filename,
                        content_type=content_type
                    )

                    async with session.post(url, data=form_data, timeout=30) as tg_response:
                        return tg_response.status == 200

    except Exception as e:
        print(f"Ошибка отправки изображения: {e}")
        return False

    return False


def get_product_category_info(product_id):
    """Получает информацию о категории товара"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT p.category_id, c.name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            WHERE p.id = ?
        """, (product_id,))

        result = cursor.fetchone()
        if result:
            return {'category_id': result[0], 'category_name': result[1]}
        return None
    except Exception as e:
        print(f"Ошибка получения категории товара: {e}")
        return None
    finally:
        conn.close()
async def health_check(request):
    """Простой health check для балансировщика"""
    return web.Response(text="OK")


@require_auth
async def return_order_item(request):
    """
    Возврат отдельной позиции в заказе
    """
    item_id = request.match_info.get('item_id')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Получаем информацию о позиции заказа
        cursor.execute("""
            SELECT oi.*, p.id as product_id, p.name as product_name, 
                   p.quantity as current_stock, o.status as order_status, 
                   o.id as order_id, o.returned_count
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN orders o ON oi.order_id = o.id
            WHERE oi.id = ?
        """, (item_id,))

        item = cursor.fetchone()

        if not item:
            return web.json_response({
                'success': False,
                'error': 'Позиция заказа не найдена'
            })

        # Проверяем, что заказ подтвержден
        if item['order_status'] not in ['confirmed', 'partially_returned']:
            return web.json_response({
                'success': False,
                'error': 'Можно возвращать товары только из подтвержденных заказов'
            })

        # Проверяем, не возвращена ли уже позиция
        returned = 0
        if 'returned' in item.keys():
            returned = item['returned']

        if returned == 1:
            return web.json_response({
                'success': False,
                'error': 'Этот товар уже возвращен'
            })

        # Возвращаем количество на склад
        product_id = item['product_id']
        quantity_to_return = item['quantity']
        current_stock = item['current_stock']
        order_id = item['order_id']

        new_quantity = current_stock + quantity_to_return

        # Обновляем количество на складе
        cursor.execute("""
            UPDATE products 
            SET quantity = ? 
            WHERE id = ?
        """, (new_quantity, product_id))

        # Помечаем позицию как возвращенную
        cursor.execute("""
            UPDATE order_items 
            SET returned = 1 
            WHERE id = ?
        """, (item_id,))

        # Увеличиваем счетчик возвращенных товаров в заказе
        new_returned_count = (item['returned_count'] or 0) + 1

        # Получаем общее количество товаров в заказе
        cursor.execute("""
            SELECT COUNT(*) as total_items
            FROM order_items
            WHERE order_id = ?
        """, (order_id,))
        total_items_result = cursor.fetchone()
        total_items = total_items_result['total_items'] if total_items_result else 0

        # Определяем новый статус заказа
        if new_returned_count == total_items:
            # Все товары возвращены
            new_status = 'returned'
            message = f'Заказ #{order_id} полностью возвращен'
        elif new_returned_count > 0:
            # Частичный возврат
            new_status = 'partially_returned'
            message = f'Товар "{item["product_name"]}" возвращен. Заказ частично возвращен ({new_returned_count}/{total_items} товаров)'
        else:
            new_status = item['order_status']
            message = f'Товар "{item["product_name"]}" возвращен'

        # Обновляем статус заказа и счетчик возвратов
        cursor.execute("""
            UPDATE orders 
            SET status = ?, returned_count = ?, total_amount = total_amount - ?
            WHERE id = ?
        """, (new_status, new_returned_count, item['price'] * quantity_to_return, order_id))

        conn.commit()

        # Отладочная информация
        print(f"DEBUG: Возврат товара - item_id: {item_id}, order_id: {order_id}")
        print(f"DEBUG: Возвращено: {new_returned_count}/{total_items} товаров")
        print(f"DEBUG: Новый статус: {new_status}")

        return web.json_response({
            'success': True,
            'message': message,
            'returned_quantity': quantity_to_return,
            'product_id': product_id,
            'order_status': new_status,
            'returned_count': new_returned_count,
            'total_items': total_items
        })

    except Exception as e:
        conn.rollback()
        print(f"Ошибка при возврате позиции заказа: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return web.json_response({
            'success': False,
            'error': f'Ошибка при возврате товара: {str(e)}'
        })
    finally:
        conn.close()
# Регистрируем роуты
# Добавьте это в список маршрутов
app.router.add_post('/api/order-items/{item_id}/return', return_order_item)
app.router.add_get('/health', health_check)
app.router.add_post('/api/orders/{id}/confirm', confirm_order_handler)
app.router.add_post('/api/orders/{id}/cancel', cancel_order_handler)
app.router.add_get('/api/discounted-products', get_discounted_products)
app.router.add_post('/api/send-discounts-notification', send_discounts_notification_handler)
app.router.add_get('/api/discounted-products', get_discounted_products)
app.router.add_post('/api/send-discounts-notification', send_discounts_notification_handler)
app.router.add_get('/debug-bot', debug_bot)
app.router.add_get('/notifications', notifications_page)
app.router.add_post('/api/send-notification', send_notification_handler)
app.router.add_get('/api/notification-history', notification_history_handler)
app.router.add_post('/api/apply_discount', apply_discounts)
app.router.add_post('/api/discounts/category', apply_category_discount)
app.router.add_post('/api/discounts/product', apply_product_discount)
app.router.add_post('/api/discounts/remove', remove_discount)
app.router.add_get('/api/discounts/category', get_category_discounts)
app.router.add_post('/categories/discount/remove', remove_category_discount)
app.router.add_post('/products/discount', set_product_discount)
app.router.add_static('/static/', path=BASE_DIR / 'static', name='static')
app.router.add_get('/login', login_page)
app.router.add_post('/login', login_handler)
app.router.add_get('/', dashboard)
app.router.add_get('/products', products_list)
app.router.add_get('/sales', sales_list)
app.router.add_post('/sales/return/{sale_id}', return_sale)
app.router.add_get('/logout', logout_handler)
app.router.add_post('/products/delete/{id}', delete_product_handler)
app.router.add_get('/products/edit/{product_id}', edit_product)
app.router.add_post('/products/edit/{product_id}', edit_product)
app.router.add_get('/products/add', add_product)
app.router.add_post('/products/add', add_product)
app.router.add_get('/orders', orders_handler)
app.router.add_post('/api/orders/{id}/update', update_order)
app.router.add_get('/orders/{order_id}', order_detail_handler)
app.router.add_post('/api/orders/{id}/status', update_order_status_handler)
app.router.add_post('/orders/{id}/return', return_order_handler)
app.router.add_post('/returns/{id}', process_return_handler)
if __name__ == '__main__':
    init_bot()
    import os
    host = os.getenv('WEB_ADMIN_HOST', '0.0.0.0')
    port = int(os.getenv('WEB_ADMIN_PORT', 8080))
    print(f"🚀 Starting Stone Admin on {host}:{port}")
    web.run_app(app, host=host, port=port)