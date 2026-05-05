# file: database.py
import json

DB_FILE = "mafia_database.json"

def load_data():
    """Загружает данные из JSON-файла. Если файла нет, возвращает пустой словарь."""
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    """Сохраняет данные в JSON-файл."""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
