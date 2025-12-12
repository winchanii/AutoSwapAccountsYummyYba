import json
import os
import socket
import subprocess
import sys

def install_dependencies():
    """Устанавливает необходимые зависимости, если они не установлены."""
    required_packages = ["flask", "requests", "pygetwindow", "psutil", "flask-cors"]
    missing_packages = []

    print("--- Проверка зависимостей ---")
    for package in required_packages:
        try:
            # Пытаемся импортировать пакет
            __import__(package)
            print(f"✅ {package} уже установлен")
        except ImportError:
            print(f"❌ {package} НЕ установлен")
            missing_packages.append(package)

    if missing_packages:
        print(f"\n--- Установка отсутствующих зависимостей: {', '.join(missing_packages)} ---")
        try:
            # Используем pip для установки
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing_packages)
            print("✅ Все зависимости успешно установлены.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка при установке зависимостей: {e}")
            print("Попробуйте установить вручную: pip install " + " ".join(missing_packages))
            sys.exit(1) # Завершаем скрипт, если установка не удалась
    else:
        print("\n✅ Все зависимости уже присутствуют.")

def get_local_ip():
    """Получает локальный IP-адрес машины."""
    try:
        # Создаем сокет и подключаемся к внешнему адресу (не отправляем данные)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # Если не получилось, возвращаем localhost
        return "127.0.0.1"

def main():
    config_template = {
        # --- RAM Settings (Запрашиваем у пользователя) ---
        "ram_settings": {
            "host": "localhost",
            "port": 7963,  # Будет заменен пользовательским значением
            "password": "42424242"  # Будет заменен пользовательским значением
        },
        # --- Telegram Settings (Запрашиваем у пользователя) ---
        "telegram_settings": {
            "bot_token": "8439472881:AAFbj7oWAoK9k_vZOs1X-tYB9HX9bjjTVXc", # Будет заменен пользовательским значением
            "chat_id": "1030528296" # Будет заменен пользовательским значением
        },
        # --- Server Ports (Запрашиваем webhook_port, остальные по умолчанию) ---
        "server_ports": {
            "webhook_listener": 4242,  # Будет заменен пользовательским значением
            "cookie_receiver": 8081,
            "webrb_controller": 8080,
            "trigger_handler": 5000
        },
        # --- Thresholds (Запрашиваем batch_trigger_count, остальные по умолчанию) ---
        "thresholds": {
            "money": 1000000,
            "batch_trigger_count": 8, # Будет заменен пользовательским значением
            "ignore_webhooks_after_restart_seconds": 600,
            "inactivity_timeout_seconds": 1200
        },
        # --- Paths (по умолчанию) ---
        "paths": {
            "accounts_file": "accounts.txt",
            "cookies_json_file": "received_cookies.json",
            "cookies_txt_file": "cookie.txt",
            "webrb_executable": "webrb.exe"
        },
        # --- Debug (Запрашиваем у пользователя) ---
        "debug": {
            "mode": True # Будет заменен пользовательским значением
        },
        # --- Other settings (по умолчанию) ---
        "restart_delay_seconds": 30,
        "webrb_window_title_excludes": [
            "chrome", "firefox", "edge", "opera", "safari", "browser", "yummy tracker", "yummytrackstat", "google chrome", "mozilla firefox", "microsoft edge"
        ]
    }

    print("--- Установщик конфигурации и зависимостей ---")

    # Устанавливаем зависимости
    install_dependencies()

    print("\n--- Настройка конфигурации ---")

    # 1. RAM Port
    while True:
        try:
            ram_port_input = input("Введите порт RAM (например, 7963): ").strip()
            if not ram_port_input: # Проверяем, пустая ли строка
                print("❌ Поле обязательно для заполнения. Пожалуйста, введите порт.")
                continue
            ram_port = int(ram_port_input)
            if 1 <= ram_port <= 65535:
                break
            else:
                print("❌ Порт должен быть числом от 1 до 65535.")
        except ValueError:
            print("❌ Пожалуйста, введите корректное число для порта.")

    # 2. RAM Password
    ram_password = input("Введите пароль от RAM: ").strip()
    while not ram_password: # Проверяем, пустая ли строка
        print("❌ Поле обязательно для заполнения. Пожалуйста, введите пароль.")
        ram_password = input("Введите пароль от RAM: ").strip()

    # 3. Telegram Bot Token
    telegram_bot_token = input("Введите токен Telegram-бота (создать его можно в @botfather , после создания обязательно запустите): ").strip()
    while not telegram_bot_token: # Проверяем, пустая ли строка
        print("❌ Поле обязательно для заполнения. Пожалуйста, введите токен.")
        telegram_bot_token = input("Введите токен Telegram-бота: ").strip()

    # 4. Telegram Chat ID
    telegram_chat_id = input("Введите ваш ID telegram (бот будем вам присылать все аккаунты и т.д, узнать можно через @TheGetAnyID_bot): ").strip()
    while not telegram_chat_id: # Проверяем, пустая ли строка
        print("❌ Поле обязательно для заполнения. Пожалуйста, введите ID чата.")
        telegram_chat_id = input("Введите ID чата Telegram (куда отправлять сообщения): ").strip()

    # 6. Batch Trigger Count
    while True:
        try:
            batch_count_input = input("Введите количество аккаунтов для срабатывания автосвапа (сколько аккаунтов у вас фармится, допустим 8): ").strip()
            if not batch_count_input: # Проверяем, пустая ли строка
                print("❌ Поле обязательно для заполнения. Пожалуйста, введите число.")
                continue
            batch_count = int(batch_count_input)
            if batch_count > 0:
                break
            else:
                print("❌ Количество должно быть положительным числом.")
        except ValueError:
            print("❌ Пожалуйста, введите корректное число.")

    # 7. Debug Mode
    # debug_mode необязательный параметр, если ввод пустой, используем False
    debug_choice = input("Включить режим отладки? (y/N): ").strip().lower()
    debug_mode = debug_choice in ['y', 'yes', '1', 'true']

    # Применяем введенные значения к шаблону
    config_template['ram_settings']['port'] = ram_port
    config_template['ram_settings']['password'] = ram_password
    config_template['telegram_settings']['bot_token'] = telegram_bot_token
    config_template['telegram_settings']['chat_id'] = telegram_chat_id
    config_template['thresholds']['batch_trigger_count'] = batch_count
    config_template['debug']['mode'] = debug_mode

    # Путь к файлу конфига
    config_filename = 'cfgas.json'

    # Сохраняем конфигурацию в файл
    try:
        with open(config_filename, 'w', encoding='utf-8') as config_file:
            json.dump(config_template, config_file, indent=2, ensure_ascii=False)
        print(f"\n✅ Конфигурация успешно сохранена в файл {config_filename}")
    except Exception as e:
        print(f"\n❌ Ошибка при сохранении файла конфигурации: {e}")
        return
 
    # Выводим инструкцию по отправке вебхука
    webhook_url = f"http://localhost:4242/webhook"
    print("\n--- Информация для настройки ---")
    print(f"📁 Конфигурационный файл: {config_filename}")
    print(f"🌐 Адрес для отправки вебхуков: {webhook_url}")
    print(f"   (Этот адрес вы вставляете в ваш скрипт в строку с вебхуком, также не забудьте выключить локалхост подключение предупреждение в вашем инжекторе")
    print("\n🚀 Теперь вы можете запускать скрипты с помощью start.bat, они будут использовать созданный config.json.")


if __name__ == '__main__':
    main()