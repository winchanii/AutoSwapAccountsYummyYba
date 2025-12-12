from flask import Flask, request, jsonify
import json
import logging
import requests
from threading import Thread, Timer
import time
from datetime import datetime
import subprocess
import os
import re # Для парсинга вебхука из content

try:
    import pygetwindow as gw
    import psutil
    GETWINDOW_AVAILABLE = True
except ImportError:
    GETWINDOW_AVAILABLE = False
    print("⚠️ Установите pygetwindow и psutil: pip install pygetwindow psutil")

app = Flask(__name__)

# --- Configuration (Объединённые настройки из обоих файлов) ---
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

# --- Configuration (Использование настроек из CONFIG) ---
SOURCE_RAM_SETTINGS = CONFIG['ram_settings']
TARGET_SERVER_SETTINGS = {
    'host': 'localhost',
    'port': CONFIG['server_ports']['cookie_receiver'] # Порт для отправки кук
}
RESTART_SERVER_SETTINGS = {
    'host': 'localhost',
    'port': CONFIG['server_ports']['webrb_controller'] # Порт для /restart (новый сервер)
}
TRIGGER_SERVER_SETTINGS = {
    'host': 'localhost',
    'port': CONFIG['server_ports']['trigger_handler'] # Порт для /trigger
}
MONEY_THRESHOLD = CONFIG['thresholds']['money']
BATCH_TRIGGER_COUNT = CONFIG['thresholds']['batch_trigger_count']
INACTIVITY_TIMEOUT = CONFIG['thresholds']['inactivity_timeout_seconds'] # 20 минут в секундах
# Путь к файлу cookie.txt (в той же папке, где находится скрипт)
COOKIE_TXT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG['paths']['cookies_txt_file'])
# Время после перезапуска webrb, когда вебхуки игнорируются (в секундах)
IGNORE_WEBHOOKS_AFTER_RESTART = CONFIG['thresholds']['ignore_webhooks_after_restart_seconds'] # 10 минут
DEBUG_MODE = CONFIG['debug']['mode'] 
# --- Конец настроек ---

# --- Глобальные переменные ---
full_accounts = set()  # Аккаунты, которые уже достигли порога и помечены как "FULL"
last_webhook_data = []  # Последние полученные данные с вебхука
is_processing = False
account_last_seen = {}  # Словарь для отслеживания времени последнего вебхука для каждого аккаунта
inactivity_timers = {}  # Таймеры для каждого аккаунта
last_restart_time = 0  # Время последнего перезапуска webrb
# --- Конец глобальных переменных ---

# --- Функции отладки ---
def debug_log(message, data=None):
    if DEBUG_MODE:
        timestamp = datetime.now().isoformat()
        print(f'[DEBUG {timestamp}] {message}')
        if data:
            print(f'  Data: {data}')

def log_money_found(username, money_str, parsed_money):
    debug_log(f'💰 Найдены деньги для {username}: "{money_str}" -> {parsed_money}')

def log_account_processing(account):
    debug_log(f'📋 Обработка аккаунта: {account["username"]}, Деньги: {account["money"]}')

def log_threshold_check(account):
    status = '✅ ДОСТИГНУТ' if account['money'] >= MONEY_THRESHOLD else '❌ НЕ ДОСТИГНУТ'
    debug_log(f'📊 Проверка порога для {account["username"]}: {account["money"]} >= {MONEY_THRESHOLD} {status}')
# --- Конец функций отладки ---

# --- Функции ---
def parse_money_string(money_str):
    if not money_str:
        return 0
    debug_log(f'🔄 Парсинг строки денег: "{money_str}"')
    clean_str = ''.join(c for c in money_str if c.isalnum() or c in '.,').upper().strip()
    if not clean_str:
        return 0
    number_part = clean_str
    multiplier = 1
    debug_log(f'🧹 Очищенная строка: "{clean_str}"')
    if clean_str.endswith('K'):
        number_part = clean_str[:-1]
        multiplier = 1000
        debug_log(f'📈 Найден суффикс K, множитель: {multiplier}')
    elif clean_str.endswith('M'):
        number_part = clean_str[:-1]
        multiplier = 1000000
        debug_log(f'📈 Найден суффикс M, множитель: {multiplier}')
    elif clean_str.endswith('B'):
        number_part = clean_str[:-1]
        multiplier = 1000000000
        debug_log(f'📈 Найден суффикс B, множитель: {multiplier}')

    normalized_number_str = number_part.replace(',', '')
    debug_log(f'🔢 Нормализованная строка числа: "{normalized_number_str}"')

    try:
        number_value = float(normalized_number_str)
    except ValueError:
        print(f'[PARSE MONEY] Could not parse: \'{money_str}\' -> \'{clean_str}\' -> \'{normalized_number_str}\'')
        return 0

    result = number_value * multiplier
    debug_log(f'🔢 Результат парсинга: {number_value} * {multiplier} = {result}')
    return int(result)

def call_ram_api(endpoint, params=None):
    if params is None:
        params = {}
    params_with_password = params.copy()
    if SOURCE_RAM_SETTINGS['password']:
        params_with_password['Password'] = SOURCE_RAM_SETTINGS['password']

    url = f'http://{SOURCE_RAM_SETTINGS["host"]}:{SOURCE_RAM_SETTINGS["port"]}{endpoint}'
    try:
        response = requests.get(url, params=params_with_password, timeout=10)
        debug_log(f'📡 Вызов RAM API: {url} (params: {params_with_password})')
        debug_log(f'📥 Ответ от RAM API ({response.status_code}): {response.text[:200]}')
        if response.status_code == 200:
            try:
                return response.json()
            except:
                if endpoint == '/GetCookie' or endpoint == '/GetDescription':
                    return response.text
                else:
                    raise ValueError(f'Failed to parse JSON response: {response.text}')
        else:
            raise Exception(f'RAM API error ({response.status_code}): {response.text}')
    except Exception as e:
        debug_log(f'❌ Ошибка сети при вызове RAM API: {e}')
        raise

def is_account_in_ram(username):
    try:
        debug_log(f'🔍 Проверка наличия аккаунта в RAM: {username}')
        account_list_response = call_ram_api('/GetAccounts')
        accounts_in_ram = [name.strip() for name in account_list_response.split(',') if name.strip()]
        exists = username in accounts_in_ram
        debug_log(f'📊 Аккаунт {username} {"найден" if exists else "НЕ найден"} в RAM')
        return exists
    except Exception as e:
        print(f'[RAM CHECK] Error for \'{username}\': {e}')
        return True  # Предполагаем что есть, если ошибка

def set_description_in_ram(username, description):
    try:
        debug_log(f'📝 Установка описания для аккаунта {username}: {description}')
        params = {'Password': SOURCE_RAM_SETTINGS['password'], 'Account': username}
        url = f'http://{SOURCE_RAM_SETTINGS["host"]}:{SOURCE_RAM_SETTINGS["port"]}/SetDescription'
        response = requests.post(url, json={'Description': description}, params=params, timeout=10)
        debug_log(f'📡 Вызов RAM API: POST {url}')
        debug_log(f'📥 Ответ от RAM API ({response.status_code}): {response.text[:200]}')
        if response.status_code == 200:
            debug_log(f'✅ Описание для {username} успешно установлено: {description}')
            return True
        else:
            print(f'[SET DESCRIPTION ERROR] Failed for {username}. Status: {response.status_code}', response.text)
            return False
    except Exception as e:
        print(f'[SET DESCRIPTION] Exception for \'{username}\': {e}')
        return False

def get_cookie_from_ram(username):
    try:
        debug_log(f'🍪 Получение куки для аккаунта: {username}')
        cookie_response = call_ram_api('/GetCookie', {'Account': username})
        if cookie_response and isinstance(cookie_response, str) and cookie_response.strip():
            debug_log(f'🔑 Куки для {username}: {cookie_response[:50]}...')
            return cookie_response
        else:
            debug_log(f'⚠️ Куки для {username} пустые или не получены.')
            return None
    except Exception as e:
        print(f'[GET COOKIE] Error for \'{username}\': {e}')
        return None

def send_cookies_to_target_pc(cookie_single):
    """
    Отправляет ОДНУ куки на сервер куки отдельным запросом
    """
    debug_log(f'📤 Отправка одной куки на сервер куки:', cookie_single[:50] + '...' if len(cookie_single) > 50 else cookie_single)
    # Отправляем только одну куки как текст
    cookies_text = cookie_single + '\n' # Добавляем символ новой строки в конце, как в оригинальном формате
    url = f'http://{TARGET_SERVER_SETTINGS["host"]}:{TARGET_SERVER_SETTINGS["port"]}/receive_cookie'
    try:
        response = requests.post(url, data=cookies_text, headers={'Content-Type': 'text/plain'}, timeout=30)
        debug_log(f'📥 Ответ от сервера куки ({response.status_code}): {response.text[:200]}')
        if response.status_code == 200:
            debug_log(f'✅ Одна кука успешно отправлена на сервер куки')
            return True
        else:
            print(f'[SEND SINGLE COOKIE ERROR] Failed. Status: {response.status_code}', response.text)
            return False
    except Exception as e:
        debug_log(f'❌ Ошибка сети при отправке одной куки на сервер: {e}')
        return False

def get_accounts_with_descriptions():
    try:
        debug_log('📋 Получение списка аккаунтов с описаниями из RAM')
        accounts_response = call_ram_api('/GetAccountsJson')
        debug_log(f'📊 Получено {len(accounts_response)} аккаунтов из RAM')
        return accounts_response
    except Exception as e:
        print(f'[GET ACCOUNTS WITH DESCRIPTIONS] Error: {e}')
        return []

def get_accounts_without_description(limit=BATCH_TRIGGER_COUNT):
    try:
        debug_log(f'📋 Получение списка аккаунтов без описания из RAM (лимит: {limit})')
        ram_accounts = get_accounts_with_descriptions()
        available_accounts = []
        for ram_account in ram_accounts:
            username = ram_account.get('Username', '')
            description = ram_account.get('Description', '') or ""
            if not description or description.strip() == "":
                available_accounts.append(username)
                debug_log(f'➕ Добавлен аккаунт {username} в список доступных для отправки')
            if len(available_accounts) >= limit:
                break
        debug_log(f'✅ Найдено {len(available_accounts)} аккаунтов без описания для отправки:', available_accounts)
        return available_accounts
    except Exception as e:
        print(f'[GET ACCOUNTS WITHOUT DESCRIPTION] Error: {e}')
        return []

def send_cookies_for_accounts(account_list):
    debug_log(f'📤 Начало отправки куки для {len(account_list)} аккаунтов по одному:', [acc for acc in account_list])
    success_count = 0
    # Проходим по списку аккаунтов циклом
    for username in account_list:
        debug_log(f'📤 Обработка аккаунта для отправки: {username}')
        try:
            cookie = get_cookie_from_ram(username)
            if cookie:
                debug_log(f'✅ Куки успешно получены для {username}')
                # Отправляем куки отдельным запросом
                if send_cookies_to_target_pc(cookie):
                    debug_log(f'✅ Куки для {username} успешно отправлены на сервер.')
                    success_count += 1
                else:
                    debug_log(f'❌ Ошибка отправки куки для {username} на сервер.')
            else:
                error_msg = f'⚠️ Не удалось получить куки для {username} или куки пустые.'
                debug_log(error_msg)
                # Не увеличиваем success_count
        except Exception as e:
            error_msg = f'⚠️ Ошибка при обработке аккаунта {username}: {e}'
            debug_log(error_msg)
            # Не увеличиваем success_count
            # Продолжаем обработку следующих аккаунтов

    debug_log(f'🏁 Отправка куки для партии завершена. Успешно отправлено: {success_count}/{len(account_list)}.')
    return success_count

def send_get_request(url):
    debug_log(f'📡 Отправка GET-запроса: {url}')
    try:
        response = requests.get(url, timeout=10)
        debug_log(f'📥 Ответ от {url} ({response.status_code}): {response.text}')
        if 200 <= response.status_code < 300:
            return response
        else:
            raise Exception(f'HTTP error {response.status_code}: {response.reason}')
    except Exception as e:
        debug_log(f'❌ Ошибка сети при отправке запроса {url}: {e}')
        raise

# Функция clear_cookies_on_target_server УДАЛЕНА

def wait_for_cookies_to_be_saved():
    """Ждем, пока куки-сервер накопит 8 кук и запишет их в файл"""
    debug_log('⏳ Ожидание, пока куки-сервер накопит 8 кук и запишет в файл...')
    # Ожидаем небольшое время, чтобы куки-сервер обработал запрос
    time.sleep(2)
    # Проверяем, есть ли 8 кук в TXT файле (последние 8 кук, как они должны быть записаны в cookie.txt)
    url = f'http://{TARGET_SERVER_SETTINGS["host"]}:{TARGET_SERVER_SETTINGS["port"]}/cookies/txt'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            # Ответ - это текстовый формат, каждая кука на новой строке
            txt_content = response.text
            # Разбиваем по строкам и убираем пустые строки
            cookies_in_txt = [line for line in txt_content.split('\n') if line.strip()]
            if len(cookies_in_txt) >= 8:
                debug_log(f'✅ Куки-сервер записал {len(cookies_in_txt)} кук в TXT файл, последние 8 успешно сохранены.')
                return True
            else:
                debug_log(f'⚠️ Куки-сервер записал только {len(cookies_in_txt)} кук в TXT файл, ожидаем 8.')
                return False
        else:
            debug_log(f'❌ Ошибка получения TXT кук от сервера: {response.status_code}')
            return False
    except Exception as e:
        debug_log(f'❌ Ошибка при ожидании накопления кук: {e}')
        return False

def perform_post_restart_actions():
    debug_log('🚀 Начало выполнения действий после перезапуска webrb')
    try:
        # 1. Подождать 10 секунд
        debug_log('⏳ Ожидание 10 секунд после перезапуска webrb...')
        time.sleep(10)
        # 2. Отправить /trigger на порт 5000
        trigger_url = f'http://{TRIGGER_SERVER_SETTINGS["host"]}:{TRIGGER_SERVER_SETTINGS["port"]}/trigger'
        send_get_request(trigger_url)
        debug_log('✅ Команда /trigger отправлена успешно')
        debug_log('🏁 Все действия после перезапуска webrb выполнены успешно')
    except Exception as e:
        print(f'[POST RESTART ACTIONS] Ошибка при выполнении действий: {e}')
        debug_log(f'❌ Ошибка в perform_post_restart_actions: {e}')
        # Не останавливаем основной поток, продолжаем проверки

def perform_restart_action():
    debug_log('🚀 Начало выполнения действия перезапуска')
    global last_restart_time
    try:
        # Отправить /restart на порт 8080 (новый сервер) с увеличенным таймаутом
        restart_url = f'http://{RESTART_SERVER_SETTINGS["host"]}:{RESTART_SERVER_SETTINGS["port"]}/restart'
        # Увеличиваем таймаут до 40 секунд, чтобы дождаться завершения перезапуска (30 сек + немного запаса)
        response = requests.get(restart_url, timeout=40)
        debug_log(f'📥 Ответ от /restart ({response.status_code}): {response.text[:200]}')
        debug_log('✅ Команда /restart отправлена успешно и выполнена')
        # Обновляем время последнего перезапуска
        last_restart_time = time.time()
        # Закрываем все окна RobloxPlayerBeta после перезапуска
        close_roblox_players()
        # Выполняем действия после перезапуска
        perform_post_restart_actions()
        debug_log('✅ Выполнены действия после перезапуска webrb.')
        debug_log('🏁 Действие перезапуска и post-actions выполнены успешно')
    except Exception as e:
        print(f'[RESTART ACTION] Ошибка при выполнении перезапуска: {e}')
        debug_log(f'❌ Ошибка в perform_restart_action: {e}')
        # Не останавливаем основной поток, продолжаем проверки

def close_roblox_players():
    try:
        debug_log('CloseOperation: Закрытие всех окон RobloxPlayerBeta')
        # Закрываем все процессы RobloxPlayerBeta.exe
        subprocess.run(['taskkill', '/f', '/im', 'RobloxPlayerBeta.exe'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        debug_log('CloseOperation: Все окна RobloxPlayerBeta закрыты')
    except Exception as e:
        debug_log(f'CloseOperation: Ошибка при закрытии RobloxPlayerBeta: {e}')

def reset_inactivity_timer(username):
    # Отменяем предыдущий таймер, если он существует
    if username in inactivity_timers:
        inactivity_timers[username].cancel()
    # Создаем новый таймер
    timer = Timer(INACTIVITY_TIMEOUT, lambda: handle_inactivity(username))
    timer.daemon = True  # Таймер завершится при завершении основного процесса
    timer.start()
    inactivity_timers[username] = timer
    debug_log(f'Таймер активности сброшен для аккаунта {username} (новый таймаут через {INACTIVITY_TIMEOUT}s)')

def handle_inactivity(username):
    debug_log(f'ИНФОРМАЦИЯ: Аккаунт {username} не активен в течение {INACTIVITY_TIMEOUT} секунд. Закрываем окно с названием аккаунта.')
    close_roblox_players_by_username(username) # Эта функция не определена, оставлю как есть из 234.txt
    # Сбрасываем таймер после закрытия окна
    if username in inactivity_timers:
        inactivity_timers[username].cancel()
        del inactivity_timers[username]
        debug_log(f'Таймер для аккаунта {username} сброшен после закрытия окна.')

def close_roblox_players_by_username(username): # Заглушка, так как в 234.txt она использует gw, которого может не быть
    try:
        debug_log(f'CloseOperationByUser: Попытка закрытия окна для {username} (не реализовано полностью)')
        # Реализация через psutil/gw была бы сложнее, оставлю сообщение
        # или можно использовать subprocess для закрытия всех, как в close_roblox_players
        close_roblox_players()
    except Exception as e:
        debug_log(f'CloseOperationByUser: Ошибка при закрытии окна {username}: {e}')

def check_accounts_from_webhook():
    global is_processing, full_accounts, last_webhook_data
    if is_processing:
        debug_log('⏭️ Обработка уже выполняется, пропускаем')
        return
    is_processing = True
    debug_log('🚀 Запуск цикла проверки аккаунтов из вебхука')
    try:
        # 1. Используем данные из вебхука
        accounts_from_webhook = last_webhook_data
        debug_log(f'📊 Обработка {len(accounts_from_webhook)} аккаунтов из вебхука')

        # 2. Обновляем время последнего вебхука для каждого аккаунта
        for account in accounts_from_webhook:
            username = account['username']
            account_last_seen[username] = time.time()
            # Сбрасываем таймер неактивности, если аккаунт в списке "полных"
            if username in full_accounts:
                debug_log(f'🔄 Сброс таймера для "полного" аккаунта {username}')
            # Сбрасываем таймер неактивности
            reset_inactivity_timer(username)

        # 2. Проверяем, достигли ли аккаунты порога
        new_full_accounts_count = 0
        for account in accounts_from_webhook:
            log_account_processing(account)
            if isinstance(account['money'], float) and account['money'] != account['money']:  # NaN check
                debug_log(f'⚠️ Значение денег для {account["username"]} является NaN. Пропускаем.')
                continue
            log_threshold_check(account)
            # Проверяем, не был ли аккаунт уже помечен как "FULL"
            if account['username'] in full_accounts:
                debug_log(f'⏭️ Аккаунт {account["username"]} уже в списке "полных". Пропускаем.')
                continue

            if account['money'] >= MONEY_THRESHOLD:
                debug_log(f'🎉 Порог достигнут для {account["username"]}: {account["money"]} >= {MONEY_THRESHOLD}')
                if is_account_in_ram(account['username']):
                    debug_log(f'✅ Аккаунт {account["username"]} подтвержден в RAM.')
                    # Установить описание "FULL"
                    if set_description_in_ram(account['username'], 'FULL'):
                        debug_log(f'✅ Описание установлено для {account["username"]}')
                        # Добавляем аккаунт в список "полных"
                        full_accounts.add(account['username'])
                        new_full_accounts_count += 1
                        debug_log(f'💾 Аккаунт {account["username"]} добавлен в список "полных"')
                        # Удаляем таймер неактивности для "полного" аккаунта
                        if account['username'] in inactivity_timers:
                            inactivity_timers[account['username']].cancel()
                            del inactivity_timers[account['username']]
                            debug_log(f'🗑️ Таймер удален для "полного" аккаунта {account["username"]}')
                    else:
                        debug_log(f'⚠️ Не удалось установить описание для {account["username"]}')
                else:
                    debug_log(f'⚠️ Аккаунт {account["username"]} достиг порога, но НЕ найден в RAM. Пропускаем.')
            else:
                debug_log(f'📉 {account["username"]}: {account["money"]} < {MONEY_THRESHOLD} - ниже порога')

        debug_log(f'📊 Новых "полных" аккаунтов за этот цикл: {new_full_accounts_count}')
        debug_log(f'📊 Общее количество "полных" аккаунтов: {len(full_accounts)}')

        # 3. Проверяем, нужно ли отправлять куки
        if len(full_accounts) >= BATCH_TRIGGER_COUNT:
            debug_log(f'🎉 Достигнуто пороговое количество "полных" аккаунтов ({len(full_accounts)} >= {BATCH_TRIGGER_COUNT}). Инициируем отправку куки.')
            # Получаем список аккаунтов без описания для отправки
            accounts_to_send = get_accounts_without_description(BATCH_TRIGGER_COUNT)
            if len(accounts_to_send) >= BATCH_TRIGGER_COUNT:
                # Отправляем куки и ждем результата (теперь по одному)
                sent_count = send_cookies_for_accounts(accounts_to_send)
                debug_log(f'✅ Обработано аккаунтов: {sent_count}.')
                # --- ИЗМЕНЕНА ЛОГИКА ---
                # Выполняем действие перезапуска и post-actions
                # если все куки были успешно отправлены.
                if sent_count == BATCH_TRIGGER_COUNT:
                    # Ждем, пока куки-сервер накопит 8 кук и запишет в файл
                    if wait_for_cookies_to_be_saved():
                        # Очищаем накопленные куки на сервере куки после успешной отправки
                        # УБРАНО: clear_cookies_on_target_server()
                        perform_restart_action()  # Перезапуск + post-actions
                        debug_log('✅ Выполнено действие перезапуска и post-actions.')
                    else:
                        debug_log(f'⚠️ Куки-сервер не накопил 8 кук, пропускаем перезапуск.')
                else:
                    debug_log(f'⚠️ Не все куки были отправлены успешно ({sent_count}/{BATCH_TRIGGER_COUNT}), пропускаем перезапуск.')
                # --- КОНЕЦ ИЗМЕНЕНИЙ ---
            else:
                debug_log(f'⚠️ Недостаточно аккаунтов без описания для отправки ({len(accounts_to_send)} < {BATCH_TRIGGER_COUNT}). Отправка отменена.')
            # Очищаем список "полных" аккаунтов после отправки
            # Аккаунты без описания будут обработаны внешним сервером
            full_accounts.clear()
            debug_log('🗑️ Список "полных" аккаунтов очищен.')
        else:
            debug_log(f'⏳ Количество "полных" аккаунтов ({len(full_accounts)}) меньше порога ({BATCH_TRIGGER_COUNT}). Ожидаем следующего цикла.')
    except Exception as e:
        print(f'[ERROR] During webhook check cycle: {e}')
    finally:
        is_processing = False
        debug_log('🏁 Цикл проверки аккаунтов из вебхука завершен')

def process_webhook_data(webhook_payload):
    global last_webhook_data
    try:
        debug_log('📥 Получены данные вебхука:', webhook_payload)
        # Проверяем, прошло ли достаточно времени после перезапуска
        current_time = time.time()
        if last_restart_time > 0 and (current_time - last_restart_time) < IGNORE_WEBHOOKS_AFTER_RESTART:
            debug_log(f'⚠️ Вебхук получен в течение {IGNORE_WEBHOOKS_AFTER_RESTART} секунд после перезапуска, игнорируем.')
            return

        # Извлекаем данные из вебхука (формат зависит от источника)
        accounts = []
        # Пример обработки для Discord-вебхука (из 234.txt)
        if 'embeds' in webhook_payload and isinstance(webhook_payload['embeds'], list):
            # Словарь для хранения данных по аккаунтам
            account_data = {}
            for embed in webhook_payload['embeds']:
                if 'fields' in embed and isinstance(embed['fields'], list):
                    username = None
                    money = 0
                    arrows = 0
                    for field in embed['fields']:
                        if 'name' in field and 'value' in field:
                            field_name = field['name'].lower()
                            field_value = field['value'].replace('> ', '').strip()
                            if any(keyword in field_name for keyword in ['client', 'name', 'аккаунт']):
                                username = field_value
                            elif any(keyword in field_name for keyword in ['balance', 'money', 'баланс']):
                                money = parse_money_string(field_value)
                            elif any(keyword in field_name for keyword in ['lucky arrows', 'стрелы', 'arrows']):
                                arrows = parse_money_string(field_value)
                    # Если есть имя аккаунта, добавляем или обновляем данные
                    if username:
                        if username in account_data:
                            # Обновляем существующие данные, если есть новые значения
                            if money > 0:
                                account_data[username]['money'] = money
                            if arrows > 0:
                                account_data[username]['arrows'] = arrows
                        else:
                            # Создаем новую запись
                            account_data[username] = {
                                'username': username,
                                'money': money,
                                'arrows': arrows
                            }

            # Преобразуем словарь в список
            accounts = list(account_data.values())

        # Если не нашли в embeds, пробуем извлечь из content или других полей (из 234.txt)
        if not accounts and 'content' in webhook_payload:
            content = webhook_payload['content']
            # Простой парсинг из текста (может потребоваться доработка) (из 234.txt)
            # --- Используем логику из 123.txt для парсинга content ---
            regex = r'([A-Za-z0-9_]+):\s*([0-9.,KMBkmb]+)'
            matches = re.findall(regex, content)
            for match in matches:
                username = match[0]
                money_str = match[1]
                money = parse_money_string(money_str)
                if money > 0:
                    accounts.append({'username': username, 'money': money, 'arrows': 0})
                    log_money_found(username, money_str, money)
            # --- Конец использования логики из 123.txt ---

        last_webhook_data = accounts
        debug_log(f'✅ Обработано {len(accounts)} аккаунтов из вебхука')

        # Выводим краткую информацию в консоль для всех аккаунтов
        for account in accounts:
            print(f'[WEBHOOK DATA] {account["username"]} - {account["money"]}, {account["arrows"]}')

        # Запускаем проверку сразу после получения данных
        thread = Thread(target=check_accounts_from_webhook)
        thread.start()

    except Exception as e:
        print(f'[WEBHOOK PROCESS] Error: {e}')
        debug_log(f'❌ Ошибка обработки вебхука: {e}', e.__traceback__)

@app.route('/webhook', methods=['POST'])
def webhook_receiver():
    try:
        data = request.get_json()
        process_webhook_data(data)
        return jsonify({'status': 'received', 'message': 'Вебхук успешно получен'}), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Сервер запущен'})

if __name__ == '__main__':
    print('[INIT] Combined Webhook Parser & Account Manager v1.0.3 (Отправка кук по одному, без очистки, исправлен синтаксис)')
    debug_log('🔧 Инициализация скрипта вебхука')
    debug_log('⚙️ Конфигурация:', {
        'SOURCE_RAM_SETTINGS': SOURCE_RAM_SETTINGS,
        'TARGET_SERVER_SETTINGS': TARGET_SERVER_SETTINGS,   # Порт 8081 для кук
        'RESTART_SERVER_SETTINGS': RESTART_SERVER_SETTINGS,  # Порт 8080 для /restart (новый сервер)
        'TRIGGER_SERVER_SETTINGS': TRIGGER_SERVER_SETTINGS,  # Порт 5000 для /trigger
        'MONEY_THRESHOLD': MONEY_THRESHOLD,
        'BATCH_TRIGGER_COUNT': BATCH_TRIGGER_COUNT,
        'INACTIVITY_TIMEOUT': INACTIVITY_TIMEOUT,
        'IGNORE_WEBHOOKS_AFTER_RESTART': IGNORE_WEBHOOKS_AFTER_RESTART,
        'COOKIE_TXT_FILE': COOKIE_TXT_FILE,
        'DEBUG_MODE': DEBUG_MODE
    })
    app.run(host='0.0.0.0', port=4242, debug=False)