import sqlite3
from better_profanity import profanity


API_TOKEN = ""   # Токен бота
MUTE_MINUTES = 10                                 # Время мута в минутах
WARN_LIMIT = 3                                    # Предупреждений до мута
DB_NAME = "moderator.db"                          # Имя файла базы данных


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            current_warns INTEGER DEFAULT 0,
            muted_until TIMESTAMP,
            is_muted BOOLEAN DEFAULT 0
        )
    ''')
    # Таблица запрещённых слов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS banned_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL,
            added_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Таблица истории предупреждений
    cur.execute('''
        CREATE TABLE IF NOT EXISTS warn_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def load_custom_words_into_profanity():
    """Читает все кастомные слова из banned_words и добавляет в better_profanity"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT word FROM banned_words')
    words = [row[0] for row in cur.fetchall()]
    conn.close()
    for w in words:
        profanity.add_censor_words([w])
