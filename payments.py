import os
import uuid
import qrcode
import aiofiles
import asyncio
import sqlite3
import requests
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from aiogram.types import FSInputFile, InputMediaPhoto
import base64

# Путь к БД
DB_PATH = "data/shop.db"


class PaymentSystem:
    def __init__(self):
        self.shop_id = os.getenv("YOOKASSA_SHOP_ID")
        self.secret_key = os.getenv("YOOKASSA_SECRET_KEY")
        self.api_url = "https://api.yookassa.ru/v3"
        self.auth = base64.b64encode(f"{self.shop_id}:{self.secret_key}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {self.auth}",
            "Content-Type": "application/json",
            "Idempotence-Key": ""
        }
        self.temp_dir = Path("temp/payments")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def create_payment(self,
                             order_id: int,
                             amount: float,
                             user_id: int,
                             description: str,
                             email: Optional[str] = None,
                             phone: Optional[str] = None) -> Dict[str, Any]:
        """
        Создает платеж в ЮKassa через прямой API вызов
        """
        try:
            # Генерируем уникальный ID для платежа
            payment_id = str(uuid.uuid4())
            idempotence_key = str(uuid.uuid4())

            # Формируем данные платежа
            payment_data = {
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "payment_method_data": {
                    "type": "sbp"
                },
                "confirmation": {
                    "type": "qr",
                    "locale": "ru_RU"
                },
                "capture": True,
                "description": f"Заказ #{order_id}: {description}",
                "metadata": {
                    "order_id": order_id,
                    "user_id": user_id,
                    "bot_payment_id": payment_id
                }
            }

            # Устанавливаем ключ идемпотентности
            self.headers["Idempotence-Key"] = idempotence_key

            # Отправляем запрос к API ЮKassa
            response = requests.post(
                f"{self.api_url}/payments",
                headers=self.headers,
                data=json.dumps(payment_data)
            )

            if response.status_code != 200:
                return {"success": False, "error": f"API error: {response.text}"}

            payment = response.json()

            # Сохраняем информацию о платеже в БД
            await self._save_payment_info(
                payment_id=payment_id,
                yookassa_payment_id=payment['id'],
                order_id=order_id,
                user_id=user_id,
                amount=amount,
                status=payment['status']
            )

            # Извлекаем URL для QR-кода
            qr_url = None
            if 'confirmation' in payment and 'confirmation_url' in payment['confirmation']:
                qr_url = payment['confirmation']['confirmation_url']

            return {
                "success": True,
                "payment_id": payment_id,
                "yookassa_payment_id": payment['id'],
                "amount": amount,
                "status": payment['status'],
                "qr_url": qr_url,
                "confirmation_url": payment['confirmation']['confirmation_url'] if 'confirmation' in payment else None,
                "payment_method": "sbp"
            }

        except Exception as e:
            print(f"Ошибка создания платежа: {e}")
            return {"success": False, "error": str(e)}

    async def generate_qr_code(self, qr_url: str, payment_id: str) -> Optional[str]:
        """
        Генерирует QR-код для оплаты
        """
        try:
            # Создаем QR-код
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_url)
            qr.make(fit=True)

            # Создаем изображение
            img = qr.make_image(fill_color="black", back_color="white")

            # Сохраняем временный файл
            file_path = self.temp_dir / f"{payment_id}.png"
            img.save(file_path)

            return str(file_path)

        except Exception as e:
            print(f"Ошибка генерации QR-кода: {e}")
            return None

    async def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Проверяет статус платежа в ЮKassa через API
        """
        try:
            # Получаем информацию о платеже из БД
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT yookassa_payment_id FROM payments WHERE payment_id = ?",
                (payment_id,)
            )
            result = cursor.fetchone()
            conn.close()

            if not result:
                return {"success": False, "error": "Платеж не найден"}

            yookassa_payment_id = result[0]

            # Генерируем новый ключ идемпотентности
            idempotence_key = str(uuid.uuid4())
            self.headers["Idempotence-Key"] = idempotence_key

            # Запрашиваем статус у ЮKassa
            response = requests.get(
                f"{self.api_url}/payments/{yookassa_payment_id}",
                headers=self.headers
            )

            if response.status_code != 200:
                return {"success": False, "error": f"API error: {response.text}"}

            payment = response.json()

            # Обновляем статус в БД
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE payments SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE payment_id = ?",
                (payment['status'], payment_id)
            )
            conn.commit()
            conn.close()

            return {
                "success": True,
                "payment_id": payment_id,
                "status": payment['status'],
                "paid": payment.get('paid', False),
                "amount": float(payment['amount']['value']) if 'amount' in payment else None,
                "captured_at": payment.get('captured_at')
            }

        except Exception as e:
            print(f"Ошибка проверки статуса платежа: {e}")
            return {"success": False, "error": str(e)}

    async def _save_payment_info(self, payment_id: str, yookassa_payment_id: str,
                                 order_id: int, user_id: int, amount: float, status: str):
        """
        Сохраняет информацию о платеже в БД
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Проверяем существование таблицы payments
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id TEXT UNIQUE NOT NULL,
                    yookassa_payment_id TEXT UNIQUE NOT NULL,
                    order_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                INSERT OR REPLACE INTO payments 
                (payment_id, yookassa_payment_id, order_id, user_id, amount, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (payment_id, yookassa_payment_id, order_id, user_id, amount, status))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"Ошибка сохранения платежа в БД: {e}")

    async def cancel_payment(self, payment_id: str) -> bool:
        """
        Отменяет платеж в ЮKassa
        """
        try:
            # Получаем ID платежа ЮKassa
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT yookassa_payment_id FROM payments WHERE payment_id = ?",
                (payment_id,)
            )
            result = cursor.fetchone()
            conn.close()

            if not result:
                return False

            yookassa_payment_id = result[0]

            # Генерируем ключ идемпотентности
            idempotence_key = str(uuid.uuid4())
            self.headers["Idempotence-Key"] = idempotence_key

            # Отправляем запрос на отмену
            response = requests.post(
                f"{self.api_url}/payments/{yookassa_payment_id}/cancel",
                headers=self.headers
            )

            if response.status_code != 200:
                return False

            # Обновляем статус в БД
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE payments SET status = 'canceled', updated_at = CURRENT_TIMESTAMP WHERE payment_id = ?",
                (payment_id,)
            )
            conn.commit()
            conn.close()

            return True

        except Exception as e:
            print(f"Ошибка отмены платежа: {e}")
            return False


# Глобальный экземпляр платежной системы
payment_system = PaymentSystem()