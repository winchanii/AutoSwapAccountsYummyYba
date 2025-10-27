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

# --- КОНСТАНТА ДЛЯ ЗАДЕРЖКИ ПОСЛЕ ПЕРЕЗАПУСКА ---
RESTART_DELAY_SECONDS = 30  # Задержка после перезапуска webrb.exe (в секундах)
# --- КОНЕЦ КОНСТАНТЫ ---

# --- КОНСТАНТА ДЛЯ ИСКЛЮЧЕНИЙ ОКОН ---
WEBRB_WINDOW_TITLE_EXCLUDES = [
    "chrome", "firefox", "edge", "opera", "safari", "browser", "yummy tracker", "yummytrackstat", "google chrome", "mozilla firefox", "microsoft edge"
]
# --- КОНЕЦ КОНСТАНТЫ ---

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

if __name__ == "__main__":
    if sys.platform == "win32":
        os.system("chcp 65001 > nul")
    
    main()