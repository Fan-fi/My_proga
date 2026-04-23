# logic.py
import sqlite3
from datetime import datetime, timedelta
from config import DB_NAME, MUTE_MINUTES, WARN_LIMIT
from better_profanity import profanity

# ---------- ПОЛЬЗОВАТЕЛИ ----------
def get_user(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
    user = cur.fetchone()
    conn.close()
    return user

def create_user(telegram_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (telegram_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
    ''', (telegram_id, username, first_name, last_name))
    conn.commit()
    conn.close()

def get_user_warns(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT current_warns FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def add_warn(telegram_id, reason):
    """Добавляет предупреждение, возвращает новое количество предупреждений"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Получаем внутренний id пользователя
    cur.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return 0
    user_internal_id = row[0]
    # Добавляем запись в историю
    cur.execute('INSERT INTO warn_history (user_id, reason) VALUES (?, ?)', (user_internal_id, reason))
    # Увеличиваем счётчик
    cur.execute('UPDATE users SET current_warns = current_warns + 1 WHERE telegram_id = ?', (telegram_id,))
    cur.execute('SELECT current_warns FROM users WHERE telegram_id = ?', (telegram_id,))
    warns = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return warns

def mute_user(telegram_id, minutes=MUTE_MINUTES):
    muted_until = datetime.now() + timedelta(minutes=minutes)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET is_muted = 1, muted_until = ?, current_warns = 0 
        WHERE telegram_id = ?
    ''', (muted_until.isoformat(), telegram_id))
    conn.commit()
    conn.close()
    return muted_until

def unmute_user(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_muted = 0, muted_until = NULL WHERE telegram_id = ?', (telegram_id,))
    conn.commit()
    conn.close()

def is_user_muted(telegram_id):
    """Проверяет, заблокирован ли пользователь, и снимает мут, если время вышло"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT is_muted, muted_until FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    is_muted, muted_until_str = row
    if is_muted and muted_until_str:
        muted_until = datetime.fromisoformat(muted_until_str)
        if muted_until > datetime.now():
            return True
        else:
            unmute_user(telegram_id)   # время истекло – снимаем мут
    return False


def add_banned_word(word, added_by_telegram_id):
    """Добавляет слово в таблицу banned_words, возвращает True/False"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO banned_words (word, added_by) VALUES (?, ?)', (word, added_by_telegram_id))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    conn.close()
    if success:
        # Сразу обновляем фильтр better_profanity
        from better_profanity import profanity
        profanity.add_censor_words([word])
    return success

def remove_banned_word(word):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('DELETE FROM banned_words WHERE word = ?', (word,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    if deleted:
        # Перезагружаем весь словарь (стандарт + оставшиеся кастомные)
        from better_profanity import profanity
        profanity.load_censor_words()
        # Добавляем все слова, которые остались в БД
        conn2 = sqlite3.connect(DB_NAME)
        cur2 = conn2.cursor()
        cur2.execute('SELECT word FROM banned_words')
        remaining = [row[0] for row in cur2.fetchall()]
        conn2.close()
        for w in remaining:
            profanity.add_censor_words([w])
    return deleted

def get_all_banned_words():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT word FROM banned_words')
    words = [row[0] for row in cur.fetchall()]
    conn.close()
    return words


def contains_bad_words(text: str) -> bool:
    """Обёртка над better_profanity для проверки текста"""
    return profanity.contains_profanity(text)