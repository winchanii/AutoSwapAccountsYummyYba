import time
import os
from datetime import datetime
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import socket
import subprocess
import psutil

# --- НОВАЯ КОНСТАНТА ---
# Список подстрок, которые НЕ должны присутствовать в заголовке окна EmuRB
# Это поможет исключить окна браузеров и других программ
EMURB_WINDOW_TITLE_EXCLUDES = [
    "chrome", "firefox", "edge", "opera", "safari", "browser", "yummy tracker", "yummytrackstat", "google chrome", "mozilla firefox", "microsoft edge"
]
# --- КОНЕЦ НОВОЙ КОНСТАНТЫ ---

# --- НОВАЯ КОНСТАНТА ДЛЯ ЗАДЕРЖЕК ---
ACTION_DELAY_SECONDS = 10  # Задержка между действиями (в секундах)
RESTART_DELAY_SECONDS = 30  # Задержка после перезапуска EmuRB (в секундах)
# --- КОНЕЦ НОВОЙ КОНСТАНТЫ ---

class EmuRBController:
    def __init__(self):
        self.running = True
        self.emurb_path = "EmuRB.exe"  # Путь к EmuRB, измените при необходимости
        self.need_restart_after_launch = False  # Флаг для перезапуска
        self.last_window = None  # Сохраняем последнее найденное окно
        
    # --- НОВЫЙ МЕТОД ---
    def is_valid_emurb_window_title(self, title):
        """Проверяет, может ли заголовок принадлежать окну EmuRB."""
        if not title or not isinstance(title, str):
            return False
        title_lower = title.lower().strip()
        # Если заголовок содержит любое из запрещенных слов, это не окно EmuRB
        for exclude_word in EMURB_WINDOW_TITLE_EXCLUDES:
            if exclude_word in title_lower:
                return False
        return True
    # --- КОНЕЦ НОВОГО МЕТОДА ---

    def find_emurb_window_by_process(self):
        """Находит окно EmuRB по процессу"""
        try:
            import pygetwindow as gw
            import psutil
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Поиск окна EmuRB по процессам...")
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'emurb' in proc.info['name'].lower() or 'yummyrb' in proc.info['name'].lower():
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Найден процесс: {proc.info['name']} (PID: {proc.info['pid']})")
                        
                        all_windows = gw.getAllWindows()
                        for window in all_windows:
                            # Ищем окна с названием, содержащим "system time" или "emurb"
                            window_title = window.title.lower()
                            # --- ОБНОВЛЕНИЕ: Добавлена проверка is_valid_emurb_window_title ---
                            if (('system time' in window_title or 
                                'emurb' in window_title or 
                                'dead' in window_title) and 
                                len(window.title.strip()) > 0 and
                                self.is_valid_emurb_window_title(window.title)): # <-- ДОБАВЛЕНО
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
    
    def find_emurb_window_by_position(self):
        """Находит окно EmuRB по позиции и содержанию"""
        try:
            import pygetwindow as gw
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Поиск окна по позиции...")
            
            all_windows = gw.getAllWindows()
            for window in all_windows:
                # Проверяем позицию и содержание заголовка
                window_title = window.title.lower()
                # --- ОБНОВЛЕНИЕ: Добавлена проверка is_valid_emurb_window_title ---
                if (((window.left < 200 and window.top < 200) or 
                    ('system time' in window_title) or 
                    ('emurb' in window_title) or 
                    ('yummy' in window_title)) and 
                    len(window.title.strip()) > 0 and
                    self.is_valid_emurb_window_title(window.title)): # <-- ДОБАВЛЕНО
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Потенциальное окно: '{window.title}' (Позиция: {window.left}, {window.top})")
                    if (('system time' in window_title or 
                        'emurb' in window_title or 
                        'yummy' in window_title or 
                        'console' in window_title or 
                        'cmd' in window_title) and
                        self.is_valid_emurb_window_title(window.title)): # <-- ДОБАВЛЕНО
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Выбрано окно: '{window.title}'")
                        self.last_window = window
                        return window
                        
        except Exception as e:
            print(f"[ERROR] Ошибка поиска по позиции: {e}")
        
        return None
    
    def get_emurb_window(self):
        """Получает окно EmuRB (новое или сохраненное)"""
        window = None
        if not window:
            window = self.find_emurb_window_by_process()
        if not window:
            window = self.find_emurb_window_by_position()
        # --- ОБНОВЛЕНИЕ: Усложненная проверка сохраненного окна ---
        if not window and self.last_window:
            # Пытаемся использовать последнее найденное окно
            try:
                # Проверяем существование окна и его заголовок
                if self.last_window.title and self.is_valid_emurb_window_title(self.last_window.title): # <-- ОБНОВЛЕНО
                    window = self.last_window
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Используем сохраненное окно: '{window.title}'")
                else:
                    # Если заголовок не прошел проверку, сбрасываем last_window
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Сохраненное окно '{getattr(self.last_window, 'title', 'Unknown')}' больше не подходит. Сброс.")
                    self.last_window = None
            except Exception as e: # <-- Уточнено исключение
                # Если возникла ошибка при доступе к окну, сбрасываем last_window
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка при проверке сохраненного окна: {e}. Сброс.")
                self.last_window = None
        
        return window
    
    def kill_emurb_processes(self):
        """Завершает все процессы EmuRB"""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Завершение процессов EmuRB...")
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'emurb' in proc.info['name'].lower() or 'yummy' in proc.info['name'].lower():
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Завершение процесса: {proc.info['name']} (PID: {proc.info['pid']})")
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Все процессы EmuRB завершены")
            return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка завершения процессов: {e}")
            return False
    
    def start_emurb(self):
        """Запускает EmuRB"""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск EmuRB: {self.emurb_path}")
            # Запускаем EmuRB
            process = subprocess.Popen(
                [self.emurb_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] EmuRB запущен (PID: {process.pid})")
            time.sleep(3) # Ждем запуск
            return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ошибка запуска EmuRB: {e}")
            return False
    
    def restart_emurb_if_needed(self):
        """Перезапускает EmuRB если это необходимо"""
        if self.need_restart_after_launch:
            print(f"\n{'='*50}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔁 ПЕРЕЗАПУСК EMURB (после launch)")
            print(f"{'='*50}")
            
            result = self.kill_emurb_processes()
            time.sleep(2)
            
            if result:
                result = self.start_emurb()
            
            if result:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ EmuRB перезапущен")
                # Ждем немного, чтобы окно успело появиться
                time.sleep(3)
                # Обновляем ссылку на окно
                self.get_emurb_window()
                # --- ДОБАВЛЕНО: Задержка после перезапуска ---
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Ожидание {RESTART_DELAY_SECONDS} секунд после перезапуска EmuRB...")
                time.sleep(RESTART_DELAY_SECONDS)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Задержка после перезапуска завершена")
                # --- КОНЕЦ ДОБАВЛЕНИЯ ---
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка перезапуска EmuRB")
                
            print(f"{'='*50}\n")
            
            self.need_restart_after_launch = False
            return result
        return True
    
    def send_command_via_keyboard(self, command_sequence):
        """Отправка команд через эмуляцию клавиатуры БЕЗ Ctrl+A и Backspace"""
        try:
            import pyautogui
            
            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0.1
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Поиск окна EmuRB...")
            
            window = self.get_emurb_window()
            
            if window:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 Найдено окно: '{window.title}'")
                try:
                    window.activate()
                    time.sleep(0.5)
                except Exception as e: # <-- Уточнено исключение
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Не удалось активировать, используем текущее окно: {e}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Окно не найдено, используем текущее активное окно")
            
            # Автоматически отправляем команды без ручного подтверждения
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Автоматическая отправка команд...")
            
            for i, cmd in enumerate(command_sequence):
                if cmd == "":
                    pyautogui.press('enter')
                    print(f"[CMD][{datetime.now().strftime('%H:%M:%S')}] >>> ENTER")
                else:
                    # ПЕРЕДЕЛАНО: Только печатаем команду, без выделения и удаления
                    pyautogui.typewrite(cmd)
                    time.sleep(0.2)
                    pyautogui.press('enter')
                    print(f"[CMD][{datetime.now().strftime('%H:%M:%S')}] >>> {cmd}")
                
                # --- ДОБАВЛЕНО: Задержка между действиями ---
                if i < len(command_sequence) - 1:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Ожидание {ACTION_DELAY_SECONDS} секунд между действиями...")
                    time.sleep(ACTION_DELAY_SECONDS)
                # --- КОНЕЦ ДОБАВЛЕНИЯ ---
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Команды отправлены")
            return True
            
        except ImportError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Требуется установка: pip install pyautogui pygetwindow psutil")
            return False
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка отправки: {e}")
            return False
    
    def exit_accounts(self):
        """Выход из аккаунтов: 10, 2, Enter, 999, Enter"""
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚪 ВЫХОД ИЗ АККАУНТОВ")
        print(f"{'='*50}")
        
        # Перезапускаем EmuRB если это необходимо
        self.restart_emurb_if_needed()
        
        commands = ["10", "", "0", "", "999", ""]
        result = self.send_command_via_keyboard(commands)
        
        if result:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Выход из аккаунтов завершен")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка выхода из аккаунтов")
            
        print(f"{'='*50}\n")
        return result
    
    def launch_accounts(self):
        """Запуск аккаунтов: 3, ждем, Enter, 2"""
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] ▶️ ЗАПУСК АККАУНТОВ")
        print(f"{'='*50}")
        
        try:
            import pyautogui
            
            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0.1
            
            window = self.get_emurb_window()
            
            if window:
                try:
                    # Активируем окно перед началом отправки команд
                    window.activate()
                    time.sleep(0.5)
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 Активировано окно: '{window.title}'")
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Не удалось активировать окно: {e}")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Окно EmuRB не найдено перед запуском. Продолжаем, надеясь, что фокус правильный.")
            
            # Автоматически отправляем команды без ручного подтверждения
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Автоматическая отправка команд...")
            
            print(f"[CMD][{datetime.now().strftime('%H:%M:%S')}] >>> 3")
            # ПЕРЕДЕЛАНО: Только печатаем команду, без выделения и удаления
            pyautogui.typewrite("3")
            pyautogui.press('enter')
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Ожидание 7 секунды...")
            time.sleep(7)
            
            print(f"[CMD][{datetime.now().strftime('%H:%M:%S')}] >>> ENTER")
            # ПЕРЕДЕЛАНО: Только нажимаем Enter
            pyautogui.press('enter')
            
            time.sleep(5)
            
            print(f"[CMD][{datetime.now().strftime('%H:%M:%S')}] >>> 2")
            # ПЕРЕДЕЛАНО: Только печатаем команду, без выделения и удаления
            pyautogui.typewrite("2")
            pyautogui.press('enter')
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Запуск аккаунтов завершен")
            print(f"{'='*50}\n")
            
            # Устанавливаем флаг для перезапуска при следующей команде
            self.need_restart_after_launch = True
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 EmuRB будет перезапущен при следующей команде")
            
            return True
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка: {e}")
            print(f"{'='*50}\n")
            return False
    
    def restart_emurb(self):
        """Ручной перезапуск EmuRB"""
        print(f"\n{'='*50}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔁 ПЕРЕЗАПУСК EMURB (ручной)")
        print(f"{'='*50}")
        
        result = self.kill_emurb_processes()
        time.sleep(2)
        
        if result:
            result = self.start_emurb()
        
        if result:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ EmuRB перезапущен")
            self.need_restart_after_launch = False  # Сбрасываем флаг
            # Обновляем ссылку на окно
            time.sleep(3)
            self.get_emurb_window()
            # --- ДОБАВЛЕНО: Задержка после перезапуска ---
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ Ожидание {RESTART_DELAY_SECONDS} секунд после перезапуска EmuRB...")
            time.sleep(RESTART_DELAY_SECONDS)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Задержка после перезапуска завершена")
            # --- КОНЕЦ ДОБАВЛЕНИЯ ---
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Ошибка перезапуска EmuRB")
            
        print(f"{'='*50}\n")
        return result

class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, controller, *args, **kwargs):
        self.controller = controller
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Обработка GET запросов"""
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
        
        if path == "/launch":
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔧 Запуск аккаунтов")
            try:
                result = self.controller.launch_accounts()
                if result:
                    response = {"status": "success", "message": "Запуск аккаунтов выполнен. EmuRB будет перезапущен при следующей команде"}
                else:
                    response = {"status": "error", "message": "Ошибка запуска аккаунтов"}
            except Exception as e:
                response = {"status": "error", "message": f"Ошибка: {str(e)}"}
                
        elif path == "/exit":
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚪 Выход из аккаунтов")
            try:
                result = self.controller.exit_accounts()
                if result:
                    response = {"status": "success", "message": "Выход из аккаунтов выполнен"}
                else:
                    response = {"status": "error", "message": "Ошибка выхода из аккаунтов"}
            except Exception as e:
                response = {"status": "error", "message": f"Ошибка: {str(e)}"}
                
        elif path == "/restart":
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔁 Перезапуск EmuRB")
            try:
                result = self.controller.restart_emurb()
                if result:
                    response = {"status": "success", "message": "EmuRB перезапущен"}
                else:
                    response = {"status": "error", "message": "Ошибка перезапуска EmuRB"}
            except Exception as e:
                response = {"status": "error", "message": f"Ошибка: {str(e)}"}
                
        elif path == "/status":
            need_restart = self.controller.need_restart_after_launch
            response = {
                "status": "running", 
                "message": "EmuRB Controller активен",
                "need_restart_after_launch": need_restart
            }
            
        elif path == "/":
            need_restart = self.controller.need_restart_after_launch
            response = {
                "status": "running", 
                "message": "EmuRB Controller API",
                "ip": self.server.server_address[0],
                "port": self.server.server_address[1],
                "need_restart_after_launch": need_restart,
                "endpoints": {
                    "/launch": "Запуск аккаунтов (помечает для перезапуска)",
                    "/exit": "Выход из аккаунтов (перезапуск если был launch)",
                    "/restart": "Ручной перезапуск EmuRB",
                    "/status": "Статус системы"
                }
            }
        
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
    
    def do_POST(self):
        """Обработка POST запросов"""
        self.do_GET()
    
    def do_OPTIONS(self):
        """Обработка CORS preflight запросов"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

def get_local_ip():
    """Получает локальный IP адрес"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def run_server(controller, host='0.0.0.0', port=8080):
    """Запуск HTTP сервера"""
    local_ip = get_local_ip()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Запуск HTTP сервера на всех интерфейсах")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Локальный IP: {local_ip}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Порт: {port}")
    
    server = HTTPServer((host, port), lambda *args, **kwargs: RequestHandler(controller, *args, **kwargs))
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Сервер запущен и готов принимать запросы")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Доступные endpoints:")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]   GET/POST http://{local_ip}:{port}/launch   - Запуск аккаунтов")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]   GET/POST http://{local_ip}:{port}/exit     - Выход из аккаунтов (перезапуск если нужно)")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]   GET/POST http://{local_ip}:{port}/restart  - Ручной перезапуск EmuRB")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]   GET/POST http://{local_ip}:{port}/status   - Статус")
    print(f"[{datetime.now().strftime('%H:%M:%S')}]   GET/POST http://{local_ip}:{port}/         - Главная страница")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💡 Доступ из локальной сети по: http://{local_ip}:{port}")
    print("-" * 70)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Получен сигнал остановки сервера...")
        server.shutdown()

def show_help():
    """Показывает справку"""
    local_ip = get_local_ip()
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              EMURB NETWORK CONTROLLER v3.0                   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║ 📋 ОПИСАНИЕ:                                                 ║
║   HTTP-сервер для управления EmuRB из локальной сети         ║
║   с отложенным перезапуском после launch                     ║
║                                                              ║
║ 🌐 ВАШ АДРЕС: {local_ip:15}                              ║
║ 📡 ПОРТ: 8080                                                ║
║                                                              ║
║ 🎯 ДОСТУПНЫЕ КОМАНДЫ:                                       ║
║   • /launch  - Запуск аккаунтов (помечает для перезапуска)   ║
║   • /exit    - Выход из аккаунтов (перезапуск если был launch)║
║   • /restart - Ручной перезапуск EmuRB                      ║
║   • /status  - Статус системы                              ║
║                                                              ║
║ 🔄 ОТЛОЖЕННЫЙ ПЕРЕЗАПУСК:                                   ║
║   1. Отправьте /launch                                      ║
║   2. EmuRB помечается для перезапуска                       ║
║   3. Отправьте следующую команду (/exit или другую)         ║
║   4. Перед выполнением команды EmuRB перезапускается        ║
║                                                              ║
║ ⏳ ЗАДЕРЖКИ:                                                ║
║   • Между действиями: {ACTION_DELAY_SECONDS} секунд          ║
║   • После перезапуска EmuRB: {RESTART_DELAY_SECONDS} секунд   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

def main():
    print("🚀 Запуск EmuRB Network Controller...")
    show_help()
    
    try:
        import pyautogui
        import pygetwindow as gw
        import psutil
    except ImportError as e:
        print("❌ Установите необходимые библиотеки:")
        print("   pip install pyautogui pygetwindow psutil")
        input("Нажмите Enter для выхода...")
        return
    
    controller = EmuRBController()
    
    server_thread = threading.Thread(target=run_server, args=(controller,), daemon=True)
    server_thread.start()
    
    print("✅ HTTP сервер запущен!")
    print("📝 Сервер готов принимать запросы из локальной сети")
    print("❌ Для завершения нажмите Ctrl+C\n")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n\n[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Получен сигнал прерывания...")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Работа завершена")

if __name__ == "__main__":
    if sys.platform == "win32":
        os.system("chcp 65001 > nul")
    
    main()