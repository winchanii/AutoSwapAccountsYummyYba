import requests
from flask import Flask
import json
import logging
import os # Для работы с файлами

# --- КОНФИГУРАЦИЯ ---
# Настройки RAM
RAM_BASE_URL = "http://your_ram_api:ram_port" # Исправлено с localhost на ваш IP
RAM_PASSWORD = "pass-ram"

# Настройки Telegram
TELEGRAM_BOT_TOKEN = "token"
TELEGRAM_CHAT_ID = "your_user_id"

# Имя файла с логинами и паролями
ACCOUNTS_FILE = "accounts.txt"

# URL для получения списка аккаунтов из RAM
GET_ACCOUNTS_URL = f"{RAM_BASE_URL}/GetAccountsJson"
# URL для получения куки аккаунта из RAM
GET_COOKIE_URL = f"{RAM_BASE_URL}/GetCookie"

# ИСПРАВЛЕННЫЙ URL для отправки сообщений в Telegram
TELEGRAM_SEND_MESSAGE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" # Исправлена лишняя пробел

# --- ИНИЦИАЛИЗАЦИЯ ---
app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- ФУНКЦИИ ---

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
        # Отправляем сообщение об ошибке в Telegram, если критично
        # send_to_telegram(f"Ошибка при удалении аккаунтов из файла: {e}")


def send_to_telegram(message):
    """Отправляет сообщение в Telegram используя requests."""
    try:
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        # Используем правильный URL
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

# --- МАРШРУТЫ FLASK ---

@app.route('/trigger', methods=['GET', 'POST'])
def trigger_check():
    """Обработчик HTTP запроса для запуска проверки."""
    logging.info("Получен сигнал по /trigger")
    import threading
    thread = threading.Thread(target=process_accounts)
    thread.start()
    return "Проверка запущена", 200

# --- ЗАПУСК ---
if __name__ == '__main__':
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

    logging.info(f"Сервер запущен. Слушаю http://0.0.0.0:5000/trigger")
    app.run(host='0.0.0.0', port=5000)
