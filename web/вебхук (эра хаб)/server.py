import requests
from flask import Flask, request, jsonify
import json
import logging
import os
import time
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import socket
import subprocess
import psutil
from datetime import datetime
from flask_cors import CORS

# --- КОНФИГУРАЦИЯ RAM И TELEGRAM ---
# --- Загрузка конфигурации ---
CONFIG_FILE_PATH = 'cfgas.json' # Путь к файлу конфигурации
try:
    with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as config_file:
        CONFIG = json.load(config_file)
    print(f"[CONFIG] Конфигурация загружена из {CONFIG_FILE_PATH}")
except FileNotFoundError:
    print(f"[CONFIG ERROR] Файл конфигурации {CONFIG_FILE_PATH} не найден!")
    exit(1)
except json.JSONDecodeError:
    print(f"[CONFIG ERROR] Ошибка чтения JSON из {CONFIG_FILE_PATH}!")
    exit(1)
# --- Конец загрузки конфигурации ---

# --- КОНФИГУРАЦИЯ RAM И TELEGRAM (Использование настроек из CONFIG) ---
# Настройки RAM
RAM_CONFIG = CONFIG['ram_settings']
RAM_BASE_URL = f"http://{RAM_CONFIG['host']}:{RAM_CONFIG['port']}"
RAM_PASSWORD = RAM_CONFIG['password']
# Настройки Telegram
TELEGRAM_BOT_TOKEN = CONFIG['telegram_settings']['bot_token']
TELEGRAM_CHAT_ID = CONFIG['telegram_settings']['chat_id']
# Имя файла с логинами и паролями
ACCOUNTS_FILE = CONFIG['paths']['accounts_file']
# URL для получения списка аккаунтов из RAM
GET_ACCOUNTS_URL = f"{RAM_BASE_URL}/GetAccountsJson"
# URL для получения куки аккаунта из RAM
GET_COOKIE_URL = f"{RAM_BASE_URL}/GetCookie"
# ИСПРАВЛЕННЫЙ URL для отправки сообщений в Telegram
TELEGRAM_SEND_MESSAGE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
# --- КОНФИГУРАЦИЯ КУК (Использование настроек из CONFIG) ---
# Путь к файлу для сохранения куки в формате JSON (все полученные куки)
COOKIES_FILE = CONFIG['paths']['cookies_json_file']
# Путь к файлу для сохранения последних 8 куки в формате TXT
COOKIES_TXT_FILE = CONFIG['paths']['cookies_txt_file'] # Используем относительный путь из config
# Количество кук для накопления
TARGET_COOKIE_COUNT = CONFIG['thresholds']['batch_trigger_count'] # Используем значение из config
# --- КОНСТАНТА ДЛЯ ЗАДЕРЖКИ ПОСЛЕ ПЕРЕЗАПУСКА (Использование настроек из CONFIG) ---
RESTART_DELAY_SECONDS = CONFIG['restart_delay_seconds'] # Задержка после перезапуска webrb.exe (в секундах)
# --- КОНЕЦ КОНСТАНТЫ ---
# --- КОНСТАНТА ДЛЯ ИСКЛЮЧЕНИЙ ОКОН (Использование настроек из CONFIG) ---
WEBRB_WINDOW_TITLE_EXCLUDES = CONFIG['webrb_window_title_excludes']
# --- КОНЕЦ КОНСТАНТЫ ---

# --- ИНИЦИАЛИЗАЦИЯ FLASK ПРИЛОЖЕНИЙ ---
app1 = Flask(__name__)  # Для основного функционала
app2 = Flask(__name__)  # Для приема куки
CORS(app2)  # Разрешить CORS для приёма куки

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- ФУНКЦИИ ОСНОВНОГО СКРИПТА ---

def load_accounts_from_file(filename):
    """
    Загружает список аккаунтов из файла в словарь.
    Предполагается, что файл содержит строки в формате username:password.
    """
    accounts = {}
    try:
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if ':' in line:
                    # Разделяем только по первому ':', на случай если в пароле есть ':'
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        username, password = parts[0].strip(), parts[1].strip()
                        if username: # Проверяем, что имя пользователя не пустое
                            accounts[username] = password
        logging.info(f"Загружено {len(accounts)} аккаунтов из {filename}")
    except FileNotFoundError:
        logging.error(f"Файл {filename} не найден.")
    except Exception as e:
        logging.error(f"Ошибка при чтении файла {filename}: {e}")
    return accounts

def remove_accounts_from_file(filename, accounts_to_remove):
    """Удаляет указанные аккаунты из файла."""
    if not accounts_to_remove:
        logging.info("Нет аккаунтов для удаления из файла.")
        return

    try:
        # Читаем все строки из файла
        with open(filename, 'r') as f:
            lines = f.readlines()

        # Фильтруем строки, оставляя только те, которые НЕ в списке на удаление
        # Сравниваем по нику (часть до ':')
        filtered_lines = []
        removed_count = 0
        for line in lines:
             line_stripped = line.strip()
             if ':' in line_stripped:
                 # Разделяем только по первому ':'
                 parts = line_stripped.split(':', 1)
                 if len(parts) == 2:
                    username, _ = parts[0].strip(), parts[1].strip()
                    if username not in accounts_to_remove:
                         filtered_lines.append(line) # Добавляем исходную строку с \n
                    else:
                         removed_count += 1
                         logging.info(f"Аккаунт '{username}' будет удален из файла.")

        # Перезаписываем файл отфильтрованным содержимым
        with open(filename, 'w') as f:
            f.writelines(filtered_lines)

        logging.info(f"Удалено {removed_count} аккаунтов из {filename}.")
    except Exception as e:
        logging.error(f"Ошибка при удалении аккаунтов из файла {filename}: {e}")

def send_to_telegram(message):
    """Отправляет сообщение в Telegram используя requests."""
    try:
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        response = requests.post(TELEGRAM_SEND_MESSAGE_URL, data=payload)
        response.raise_for_status()
        logging.info(f"Сообщение отправлено в Telegram.")
        return True # Успешно отправлено
    except requests.exceptions.HTTPError as e:
        logging.error(f"Ошибка отправки в Telegram (HTTP {response.status_code}): {e}")
        logging.error(f"Ответ сервера: {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка отправки в Telegram (Request): {e}")
    except Exception as e:
        logging.error(f"Неожиданная ошибка при отправке в Telegram: {e}")
    return False # Ошибка отправки

def get_account_descriptions():
    """Получает список аккаунтов и их описания из RAM."""
    try:
        response = requests.get(GET_ACCOUNTS_URL, params={'Password': RAM_PASSWORD})

        if response.status_code == 200:
            accounts_data = response.json()
            logging.info(f"Получены данные {len(accounts_data)} аккаунтов из RAM.")
            return accounts_data
        else:
            logging.error(f"Ошибка получения аккаунтов из RAM: {response.status_code} - {response.text}")
            # Отправляем сообщение об ошибке в Telegram
            send_to_telegram(f"Ошибка получения аккаунтов из RAM: {response.status_code}")
            return []
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка запроса к RAM API: {e}")
        send_to_telegram(f"Ошибка запроса к RAM API: {e}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка парсинга JSON из RAM: {e}")
        send_to_telegram(f"Ошибка парсинга JSON из RAM: {e}")
        return []

def get_cookie_for_account(username):
    """Получает куки для конкретного аккаунта из RAM."""
    try:
        params = {'Password': RAM_PASSWORD, 'Account': username}
        response = requests.get(GET_COOKIE_URL, params=params)

        if response.status_code == 200:
            cookie = response.text # Куки возвращаются как текст
            logging.info(f"Получены куки для аккаунта '{username}'")
            return cookie
        else:
            logging.error(f"Ошибка получения куки для '{username}' из RAM: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка запроса к RAM API для получения куки '{username}': {e}")
        return None
    except Exception as e:
        logging.error(f"Неожиданная ошибка при получении куки для '{username}': {e}")
        return None

def process_accounts():
    """Основная логика: получает данные, проверяет описания, ищет в файле, отправляет в TG и удаляет."""
    # 1. Загружаем данные из файла accounts.txt
    file_accounts = load_accounts_from_file(ACCOUNTS_FILE)
    if not file_accounts:
        msg = "Ошибка: Не удалось загрузить аккаунты из файла или файл пуст."
        logging.error(msg)
        send_to_telegram(msg)
        return

    # 2. Получаем данные об аккаунтах из RAM
    ram_accounts_data = get_account_descriptions()
    if not ram_accounts_data:
        msg = "Ошибка: Не удалось получить данные аккаунтов из RAM или список пуст."
        logging.error(msg)
        send_to_telegram(msg)
        return

    # 3. Обрабатываем каждый аккаунт из RAM
    found_accounts_data = [] # Список для отправки в одно сообщение (формат username:password:cookie)
    found_accounts_simple = [] # Новый список для аккаунтов в формате username:password (без куки)
    usernames_to_remove = set() # Используем set для уникальности
    for account in ram_accounts_data:
        username = account.get('Username', '')
        description = account.get('Description', '')

        # Проверяем, есть ли описание (и что оно не пустое/не состоит только из пробелов)
        if description and description.strip():
            logging.info(f"Аккаунт '{username}' имеет описание: '{description}'")

            # Проверяем, есть ли этот ник в нашем файле
            if username in file_accounts:
                password = file_accounts[username]
                # Получаем куки для аккаунта
                cookie = get_cookie_for_account(username)
                if cookie:
                    # Формируем строку в нужном формате
                    account_info = f"{username}:{password}:{cookie}"
                    found_accounts_data.append(account_info)
                    usernames_to_remove.add(username) # Добавляем ник для удаления
                    logging.info(f"Найден аккаунт в файле и получены куки: {username}")
                    
                    # Формируем строку username:password для сводного сообщения
                    simple_account_info = f"{username}:{password}"
                    found_accounts_simple.append(simple_account_info)
                    
                    # Отправляем КАЖДЫЙ найденный аккаунт отдельным сообщением
                    individual_message = f"Найден аккаунт с описанием:\n{account_info}"
                    if send_to_telegram(individual_message):
                        logging.info(f"Сообщение для {username} успешно отправлено в Telegram.")
                    else:
                        logging.error(f"Не удалось отправить сообщение для {username} в Telegram.")
                else:
                    error_msg = f"Найден аккаунт '{username}' в файле, но не удалось получить куки."
                    logging.warning(error_msg)
                    send_to_telegram(error_msg) # Отправляем сообщение об ошибке
            else:
                logging.info(f"Аккаунт '{username}' с описанием НЕ найден в файле.")

    # 4. Отправляем результаты в Telegram
    if found_accounts_data:
        # Отправляем сводное сообщение с аккаунтами в формате username:password (без куки)
        summary_list_text = "\n".join(found_accounts_simple)
        summary_message = f"Найденные аккаунты с описанием (все, без куки):\n{summary_list_text}"
        send_to_telegram(summary_message)
        
        # Отправляем сообщение о количестве найденных аккаунтов
        summary_count_message = f"Проверка завершена. Найдено и обработано {len(found_accounts_data)} аккаунтов с описанием."
        send_to_telegram(summary_count_message)
        
        # 5. Если сообщения успешно отправлены, удаляем аккаунты из файла
        # Удаляем после обработки всех, если хотя бы одно сообщение ушло.
        # Для простоты, удаляем все найденные, независимо от статуса отправки каждого.
        remove_accounts_from_file(ACCOUNTS_FILE, usernames_to_remove)
    else:
        send_to_telegram("Аккаунты с описанием, присутствующие в файле, не найдены.")

# --- МАРШРУТЫ FLASK ДЛЯ ОСНОВНОГО СКРИПТА ---
@app1.route('/trigger', methods=['GET', 'POST'])
def trigger_check():
    """Обработчик HTTP запроса для запуска проверки."""
    logging.info("Получен сигнал по /trigger")
    thread = threading.Thread(target=process_accounts)
    thread.start()
    return "Проверка запущена", 200

# --- ФУНКЦИИ СЕРВЕРА КУК ---

# Создаем директорию для JSON файла, если её нет
json_dir = os.path.dirname(COOKIES_FILE)
if json_dir and not os.path.exists(json_dir):
    os.makedirs(json_dir)

# Создаем пустой JSON файл, если его нет
if not os.path.exists(COOKIES_FILE):
    with open(COOKIES_FILE, 'w') as f:
        json.dump([], f, indent=2)

# Создаем директорию для TXT файла, если её нет
txt_dir = os.path.dirname(COOKIES_TXT_FILE)
if txt_dir and not os.path.exists(txt_dir):
    os.makedirs(txt_dir)

# Создаем пустой TXT файл, если его нет
if not os.path.exists(COOKIES_TXT_FILE):
    with open(COOKIES_TXT_FILE, 'w') as f:
        pass  # Создаем пустой файл

@app2.route('/')
def home():
    return jsonify({
        "message": "Cookie receiver server is running",
        "target_count": TARGET_COOKIE_COUNT,
        "files": {
            "json": COOKIES_FILE,
            "txt": COOKIES_TXT_FILE
        },
        "endpoints": {
            "POST /receive_cookie": "Receive and save cookie (text/plain)",
            "GET /cookies": "Get all saved cookies",
            "GET /cookies/txt": f"Get last {TARGET_COOKIE_COUNT} cookies as they would appear in the TXT file",
            "DELETE /cookies": "Clear all cookies"
        }
    })

@app2.route('/receive_cookie', methods=['POST'])
def receive_cookie():
    try:
        # Получаем куки как текст из тела запроса
        cookie = request.get_data(as_text=True)
        # Проверяем, что куки не пустые
        if not cookie:
            print("❌ Получены пустые куки")
            return jsonify({'success': False, 'message': 'Empty cookie received'}), 400
        print(f"📥 Получены куки (длина: {len(cookie)})")

        # --- ЛОГИКА НАКОПЛЕНИЯ И СОХРАНЕНИЯ ---
        # 1. Загружаем существующие куки из JSON
        cookies_data_json = []
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                try:
                    cookies_data_json = json.load(f)
                except json.JSONDecodeError:
                    print(f"⚠️ Ошибка чтения JSON файла {COOKIES_FILE}. Создается новый список.")
                    cookies_data_json = []

        # 2. Добавляем новую куку в конец списка JSON
        cookies_data_json.append({
            'cookie': cookie,
            'receivedAt': datetime.now().isoformat()
        })

        # 3. Сохраняем обновленный JSON файл (все куки)
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies_data_json, f, indent=2)

        # 4. Проверяем, набралось ли нужное количество кук
        if len(cookies_data_json) >= TARGET_COOKIE_COUNT:
            print(f"🎉 Накоплено {len(cookies_data_json)} кук. Сохраняем последние {TARGET_COOKIE_COUNT} в TXT файл.")
            
            # Берем последние TARGET_COOKIE_COUNT кук
            latest_cookies = [item['cookie'] for item in cookies_data_json[-TARGET_COOKIE_COUNT:]]
            
            # 5. Записываем последние 8 кук в TXT файл, каждая с новой строки
            with open(COOKIES_TXT_FILE, 'w', encoding='utf-8') as f:
                # Записываем куки по одной на строку
                f.write('\n'.join(latest_cookies))
                # Убедимся, что файл заканчивается символом новой строки, как в оригинале
                f.write('\n') 
            
            print(f"✅ Последние {TARGET_COOKIE_COUNT} кук успешно сохранены в {COOKIES_TXT_FILE}")
            
            return jsonify({
                'success': True, 
                'message': f'Cookie received. Total {len(cookies_data_json)} cookies accumulated. Last {TARGET_COOKIE_COUNT} saved to TXT.'
            }), 200
        else:
            # Если кук еще недостаточно
            current_count = len(cookies_data_json)
            needed_count = TARGET_COOKIE_COUNT - current_count
            print(f"🍪 Куки накоплены: {current_count}/{TARGET_COOKIE_COUNT}. Нужно еще {needed_count}.")
            return jsonify({
                'success': True, 
                'message': f'Cookie received and stored. Accumulated {current_count}/{TARGET_COOKIE_COUNT} cookies. Need {needed_count} more.'
            }), 200

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f'❌ Ошибка при сохранении куки: {str(e)}')
        print(f"Детали ошибки:\n{error_details}")
        return jsonify({'success': False, 'message': 'Error saving cookie'}), 500


@app2.route('/cookies', methods=['GET'])
def get_cookies():
    try:
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                try:
                    cookies_data = json.load(f)
                except json.JSONDecodeError:
                    cookies_data = []
        else:
            cookies_data = []
        return jsonify(cookies_data), 200
    except Exception as e:
        print(f'❌ Ошибка при чтении куки: {str(e)}')
        return jsonify({'error': 'Error reading cookies'}), 500


@app2.route('/cookies/txt', methods=['GET'])
def get_cookies_txt_format():
    """Возвращает последние TARGET_COOKIE_COUNT кук в том же формате, что и в файле cookie.txt."""
    try:
        cookies_data_json = []
        if os.path.exists(COOKIES_FILE):
            with open(COOKIES_FILE, 'r') as f:
                try:
                    cookies_data_json = json.load(f)
                except json.JSONDecodeError:
                    cookies_data_json = []

        if len(cookies_data_json) >= TARGET_COOKIE_COUNT:
            latest_cookies = [item['cookie'] for item in cookies_data_json[-TARGET_COOKIE_COUNT:]]
            # Форматируем как в файле TXT: каждая кука на новой строке, завершается \n
            txt_content = '\n'.join(latest_cookies) + '\n'
            return txt_content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        else:
            return f"Not enough cookies. Have {len(cookies_data_json)}, need {TARGET_COOKIE_COUNT}.\n", 400, {'Content-Type': 'text/plain; charset=utf-8'}

    except Exception as e:
        print(f'❌ Ошибка при формировании TXT куки: {str(e)}')
        return 'Error generating cookie list\n', 500, {'Content-Type': 'text/plain; charset=utf-8'}

@app2.route('/cookies', methods=['DELETE'])
def clear_cookies():
    try:
        # Очищаем JSON файл
        with open(COOKIES_FILE, 'w') as f:
            json.dump([], f, indent=2)
        # Очищаем TXT файл
        with open(COOKIES_TXT_FILE, 'w') as f:
            pass  # Создаем пустой файл
        print('🗑️ Все куки очищены')
        return jsonify({'success': True, 'message': 'All cookies cleared'}), 200
    except Exception as e:
        print(f'❌ Ошибка при очистке куки: {str(e)}')
        return jsonify({'success': False, 'message': 'Error clearing cookies'}), 500

# --- КЛАСС УПРАВЛЕНИЯ WEBRB ---

class WebRBController:
    def __init__(self):
        self.running = True
        self.webrb_path = "webrb.exe"  # Путь к webrb.exe
        self.last_window = None
        
    def is_valid_webrb_window_title(self, title):
        """Проверяет, может ли заголовок принадлежать окну webrb."""
        if not title or not isinstance(title, str):
            return False
        title_lower = title.lower().strip()
        for exclude_word in WEBRB_WINDOW_TITLE_EXCLUDES:
            if exclude_word in title_lower:
                return False
        return True

    def find_webrb_window_by_process(self):
        """Находит окно webrb по процессу"""
        try:
            import pygetwindow as gw
            import psutil
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Поиск окна webrb по процессам...")
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'webrb' in proc.info['name'].lower():
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Найден процесс: {proc.info['name']} (PID: {proc.info['pid']})")
                        
                        all_windows = gw.getAllWindows()
                        for window in all_windows:
                            window_title = window.title.lower()
                            if (('system time' in window_title or 
                                'webrb' in window_title or 
                                'dead' in window_title) and 
                                len(window.title.strip()) > 0 and
                                self.is_valid_webrb_window_title(window.title)):
                                print(f"[{datetime.now().strftime('%H:%M:%S')}] Найдено окно: '{window.title}'")
                                self.last_window = window
                                return window
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except ImportError:
            pass
        except Exception as e:
            print(f"[ERROR] Ошибка поиска по процессам: {e}")
        
        return None

    def find_webrb_window_by_position(self):
        """Находит окно webrb по позиции и содержанию"""
        try:
            import pygetwindow as gw
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Поиск окна по позиции...")
            
            all_windows = gw.getAllWindows()
            for window in all_windows:
                window_title = window.title.lower()
                if (((window.left < 200 and window.top < 200) or 
                    ('system time' in window_title) or 
                    ('webrb' in window_title) or 
                    ('yummy' in window_title)) and 
                    len(window.title.strip()) > 0 and
                    self.is_valid_webrb_window_title(window.title)):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Потенциальное окно: '{window.title}' (Позиция: {window.left}, {window.top})")
                    if (('system time' in window_title or 
                        'webrb' in window_title or 
                        'yummy' in window_title or 
                        'console' in window_title or 
                        'cmd' in window_title) and
                        self.is_valid_webrb_window_title(window.title)):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Выбрано окно: '{window.title}'")
                        self.last_window = window
                        return window
                        
        except Exception as e:
            print(f"[ERROR] Ошибка поиска по позиции: {e}")
        
        return None
    
    def get_webrb_window(self):
        """Получает окно webrb (новое или сохраненное)"""
        window = None
        if not window:
            window = self.find_webrb_window_by_process()
        if not window:
            window = self.find_webrb_window_by_position()
        if not window and self.last_window:
            try:
                if self.last_window.title and self.is_valid_webrb_window_title(self.last_window.title):
                    window = self.last_window
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Используем сохраненное окно: '{window.title}'")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Сохраненное окно '{getattr(self.last_window, 'title', 'Unknown')}' больше не подходит. Сброс.")
                    self.last_window = None
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка при проверке сохраненного окна: {e}. Сброс.")
                self.last_window = None
        
        return window

    def kill_webrb_processes(self):
        """Завершает все процессы webrb"""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Завершение процессов webrb...")
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'webrb' in proc.info['name'].lower():
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Завершение процесса: {proc.info['name']} (PID: {proc.info['pid']})")
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Все процессы webrb завершены")
            return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка завершения процессов: {e}")
            return False
    
    def start_webrb(self):
        """Запускает webrb"""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск webrb: {self.webrb_path}")
            process = subprocess.Popen(
                [self.webrb_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] webrb запущен (PID: {process.pid})")
            time.sleep(3)
            return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка запуска webrb: {e}")
            return False

    def restart_webrb(self):
        """Перезапускает webrb"""
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔁 ПЕРЕЗАПУСК WEBRB")
        print(f"{'='*50}")
        
        result = self.kill_webrb_processes()
        time.sleep(2)
        
        if result:
            result = self.start_webrb()
        
        if result:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ webrb перезапущен")
            time.sleep(3)
            self.get_webrb_window()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Ожидание {RESTART_DELAY_SECONDS} секунд после перезапуска webrb...")
            time.sleep(RESTART_DELAY_SECONDS)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Задержка после перезапуска завершена")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка перезапуска webrb")
            
        print(f"{'='*50}\n")
        return result

class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        # Отключаем логирование по умолчанию
        self.log_message = lambda *args: None
        
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path.lower()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Получен запрос от {self.client_address[0]}: {self.path}")
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
        
        response = {"status": "error", "message": "Неизвестная команда"}
        
        if path == "/restart":
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔁 Перезапуск webrb")
            try:
                result = self.controller.restart_webrb()
                if result:
                    response = {"status": "success", "message": "webrb перезапущен"}
                else:
                    response = {"status": "error", "message": "Ошибка перезапуска webrb"}
            except Exception as e:
                response = {"status": "error", "message": f"Ошибка: {str(e)}"}
                
        elif path == "/status":
            response = {
                "status": "running", 
                "message": "WebRB Controller активен"
            }
            
        elif path == "/":
            response = {
                "status": "running", 
                "message": "WebRB Controller API",
                "ip": self.server.server_address[0],
                "port": self.server.server_address[1],
                "endpoints": {
                    "/restart": "Перезапуск webrb.exe",
                    "/status": "Статус системы"
                }
            }
        
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
    
    def do_POST(self):
        self.do_GET()
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def run_server(controller, host='0.0.0.0', port=8080):
    local_ip = get_local_ip()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Запуск HTTP сервера на всех интерфейсах")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Локальный IP: {local_ip}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Порт: {port}")
    
    # Создаем сервер с параметрами для стабильной работы
    server = HTTPServer((host, port), lambda *args, **kwargs: RequestHandler(controller, *args, **kwargs))
    server.timeout = 1  # Уменьшаем таймаут для быстрого реагирования
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Сервер запущен и готов принимать запросы")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Доступные endpoints:")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]   GET/POST http://{local_ip}:{port}/restart  - Перезапуск webrb.exe")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]   GET/POST http://{local_ip}:{port}/status   - Статус")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💡 Доступ из локальной сети по: http://{local_ip}:{port}")
    print("-" * 70)
    
    try:
        while True:
            server.handle_request()  # Обрабатываем запросы по одному, без блокировки
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Получен сигнал остановки сервера...")
        server.shutdown()

def show_help():
    local_ip = get_local_ip()
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              WEBRB RESTART CONTROLLER v1.0                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║ 📋 ОПИСАНИЕ:                                                 ║
║   HTTP-сервер для перезапуска процесса webrb.exe             ║
║                                                              ║
║ 🌐 ВАШ АДРЕС: {local_ip:15}                              ║
║ 📡 ПОРТ: 8080                                                ║
║                                                              ║
║ 🎯 ДОСТУПНЫЕ КОМАНДЫ:                                       ║
║   • /restart - Перезапуск webrb.exe                         ║
║   • /status  - Статус системы                              ║
║                                                              ║
║ ⏳ ЗАДЕРЖКА:                                                 ║
║   • После перезапуска webrb.exe: {RESTART_DELAY_SECONDS} секунд   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

def main():
    print("🚀 Запуск WebRB Restart Controller...")
    show_help()
    
    try:
        import pygetwindow as gw
        import psutil
    except ImportError as e:
        print("❌ Установите необходимые библиотеки:")
        print("   pip install pygetwindow psutil")
        input("Нажмите Enter для выхода...")
        return
    
    controller = WebRBController()
    
    # Запускаем сервер в основном потоке с правильной обработкой
    run_server(controller)

# --- ЗАПУСК СЕРВЕРОВ ---

def start_flask_app1():
    """Запуск основного Flask-приложения"""
    # Простая проверка конфигурации
    if RAM_PASSWORD == "42424242":
        logging.warning("!!! ИСПОЛЬЗУЕТСЯ ПАРОЛЬ ПО УМОЛЧАНИЮ (42424242). Убедитесь, что он безопасен !!!")
    # Проверка наличия токена и chat_id
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "1":
        logging.error("!!! НЕ НАСТРОЕН TELEGRAM_BOT_TOKEN В КОНФИГУРАЦИИ !!!")
        exit(1)
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "1":
        logging.error("!!! НЕ НАСТРОЕН TELEGRAM_CHAT_ID В КОНФИГУРАЦИИ !!!")
        exit(1)
    logging.info(f"Сервер 1 запущен. Слушаю http://0.0.0.0:{CONFIG['server_ports']['trigger_handler']}/trigger") # Используем порт из config
    app1.run(host='0.0.0.0', port=CONFIG['server_ports']['trigger_handler'], debug=False, use_reloader=False) # Используем порт из config


def start_flask_app2():
    """Запуск Flask-приложения для приема куки"""
    print(f"🚀 Сервер куки запущен на http://0.0.0.0:{CONFIG['server_ports']['cookie_receiver']}") # Используем порт из config
    print(f"📁 Файл куки JSON (все): {COOKIES_FILE}")
    print(f"📁 Файл куки TXT (последние {TARGET_COOKIE_COUNT}): {COOKIES_TXT_FILE}")
    print(f"🎯 Целевое количество кук для срабатывания: {TARGET_COOKIE_COUNT}")
    print("📊 Доступные endpoints:")
    print("   POST /receive_cookie - Принять куки (только текст куки)")
    print("   GET /cookies - Получить все накопленные куки (JSON)")
    print(f"   GET /cookies/txt - Получить последние {TARGET_COOKIE_COUNT} кук в формате TXT")
    print("   DELETE /cookies - Очистить все куки")
    print("   GET / - Информация о сервере")
    app2.run(host='0.0.0.0', port=CONFIG['server_ports']['cookie_receiver'], debug=False, use_reloader=False) # Используем порт из config


def start_webrb_server():
    """Запуск WebRB сервера"""
    main()

if __name__ == '__main__':
    if sys.platform == "win32":
        os.system("chcp 65001 > nul")
    
    # Запускаем все три сервера в отдельных потоках
    thread1 = threading.Thread(target=start_flask_app1, daemon=True)
    thread2 = threading.Thread(target=start_flask_app2, daemon=True)
    thread3 = threading.Thread(target=start_webrb_server, daemon=True)
    
    thread1.start()
    thread2.start()
    thread3.start() # Запускаем поток WebRB сервера
    
    # Ждем завершения потоков (или Ctrl+C)
    try:
        thread1.join()
        thread2.join()
        thread3.join() # Ждем завершения потока WebRB сервера
    except KeyboardInterrupt:
        print("\nПолучен сигнал остановки...")
        sys.exit(0)