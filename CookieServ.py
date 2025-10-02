from flask import Flask, request, jsonify
import json
import os
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Разрешить CORS для всех origins

# --- Конфигурация ---
# Путь к файлу для сохранения куки в формате JSON (все полученные куки)
COOKIES_FILE = 'received_cookies.json'
# Путь к файлу для сохранения последних 8 куки в формате TXT
COOKIES_TXT_FILE = r'C:\Yummyemu\YummyEmuPlayer\cookie.txt'
# Количество кук для накопления
TARGET_COOKIE_COUNT = 8
# --- Конец конфигурации ---

# Создаем директорию, если её нет
cookies_dir = os.path.dirname(COOKIES_TXT_FILE)
if not os.path.exists(cookies_dir):
    os.makedirs(cookies_dir)

# Создаем пустой JSON файл, если его нет
if not os.path.exists(COOKIES_FILE):
    with open(COOKIES_FILE, 'w') as f:
        json.dump([], f, indent=2)

# Создаем пустой TXT файл, если его нет
if not os.path.exists(COOKIES_TXT_FILE):
    with open(COOKIES_TXT_FILE, 'w') as f:
        pass  # Создаем пустой файл

@app.route('/')
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

@app.route('/receive_cookie', methods=['POST'])
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

@app.route('/cookies', methods=['GET'])
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

@app.route('/cookies/txt', methods=['GET'])
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

@app.route('/cookies', methods=['DELETE'])
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

if __name__ == '__main__':
    print("🚀 Сервер запущен на http://0.0.0.0:8081")
    print(f"📁 Файл куки JSON (все): {COOKIES_FILE}")
    print(f"📁 Файл куки TXT (последние {TARGET_COOKIE_COUNT}): {COOKIES_TXT_FILE}")
    print(f"🎯 Целевое количество кук для срабатывания: {TARGET_COOKIE_COUNT}")
    print("📊 Доступные endpoints:")
    print("   POST /receive_cookie - Принять куки (только текст куки)")
    print("   GET /cookies - Получить все накопленные куки (JSON)")
    print(f"   GET /cookies/txt - Получить последние {TARGET_COOKIE_COUNT} кук в формате TXT")
    print("   DELETE /cookies - Очистить все куки")
    print("   GET / - Информация о сервере")
    # Запуск сервера на всех интерфейсах, порт 8081
    app.run(host='0.0.0.0', port=8081, debug=True)
