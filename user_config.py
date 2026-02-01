# Создайте новый файл user_config.py или добавьте в существующий код:

USER_CONFIGS = {
    "user1": {
        "name": "Ваше имя/никнейм",
        "device_name": "iPhone iOS 17.5.1",
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        "ip_addresses": ["31.43.37.220", "31.43.37.157"],
        "location": {
            "city": "Lubny",
            "region": "Poltava Oblast",
            "country": "Ukraine",
            "timezone": "Europe/Kyiv"
        },
        "isp": "Ukrainian Telecommunication Group LLC",
        "proxy": None,  # Если нужен прокси, укажите здесь
        "browser_profile": None,  # Путь к профилю Chrome если есть
        "additional_data": {
            "platform": "iPhone",
            "screen": "375x812",
            "languages": ["ru"],
            "media_devices": {
                "microphone": True,
                "camera": True
            }
        }
    }
}
