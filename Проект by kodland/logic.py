import sqlite3
from datetime import datetime, timedelta
from config import DB_NAME, MUTE_MINUTES

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            current_warns INTEGER DEFAULT 0,
            muted_until TIMESTAMP,
            is_muted BOOLEAN DEFAULT 0,
            banned_until TIMESTAMP,
            is_banned BOOLEAN DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS warn_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS moderation_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            target_id INTEGER,
            action_type TEXT,
            reason TEXT,
            duration_minutes INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

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

def add_warn(telegram_id, reason, admin_id=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    # Проверяем, есть ли пользователь
    cur.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cur.fetchone()
    if not row:
        # Создаём пользователя с минимальными данными
        cur.execute('''
            INSERT INTO users (telegram_id, first_name) VALUES (?, ?)
        ''', (telegram_id, str(telegram_id)))
        conn.commit()
        cur.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
        row = cur.fetchone()
    user_internal_id = row[0]
    cur.execute('INSERT INTO warn_history (user_id, reason) VALUES (?, ?)', (user_internal_id, reason))
    cur.execute('UPDATE users SET current_warns = current_warns + 1 WHERE telegram_id = ?', (telegram_id,))
    cur.execute('SELECT current_warns FROM users WHERE telegram_id = ?', (telegram_id,))
    warns = cur.fetchone()[0]
    if admin_id:
        cur.execute('''
            INSERT INTO moderation_actions (admin_id, target_id, action_type, reason)
            VALUES (?, ?, ?, ?)
        ''', (admin_id, telegram_id, 'warn', reason))
    conn.commit()
    conn.close()
    return warns

def clear_warns(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('UPDATE users SET current_warns = 0 WHERE telegram_id = ?', (telegram_id,))
    conn.commit()
    conn.close()

def mute_user(telegram_id, minutes=MUTE_MINUTES, reason="", admin_id=None):
    muted_until = datetime.now() + timedelta(minutes=minutes)
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET is_muted = 1, muted_until = ?, current_warns = 0 
        WHERE telegram_id = ?
    ''', (muted_until.isoformat(), telegram_id))
    if admin_id:
        cur.execute('''
            INSERT INTO moderation_actions (admin_id, target_id, action_type, reason, duration_minutes)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, telegram_id, 'mute', reason, minutes))
    conn.commit()
    conn.close()
    return muted_until

def unmute_user(telegram_id, admin_id=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_muted = 0, muted_until = NULL WHERE telegram_id = ?', (telegram_id,))
    if admin_id:
        cur.execute('''
            INSERT INTO moderation_actions (admin_id, target_id, action_type, reason)
            VALUES (?, ?, ?, ?)
        ''', (admin_id, telegram_id, 'unmute', 'manual_unmute'))
    conn.commit()
    conn.close()

def is_user_muted(telegram_id):
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
            unmute_user(telegram_id)
    return False

def ban_user(telegram_id, minutes=None, reason="", admin_id=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if minutes is None:
        banned_until = None
        is_banned = 1
    else:
        banned_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        is_banned = 1
    cur.execute('''
        UPDATE users 
        SET is_banned = ?, banned_until = ?, current_warns = 0, is_muted = 0, muted_until = NULL
        WHERE telegram_id = ?
    ''', (is_banned, banned_until, telegram_id))
    if admin_id:
        cur.execute('''
            INSERT INTO moderation_actions (admin_id, target_id, action_type, reason, duration_minutes)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, telegram_id, 'ban', reason, minutes if minutes else 0))
    conn.commit()
    conn.close()

def unban_user(telegram_id, admin_id=None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_banned = 0, banned_until = NULL WHERE telegram_id = ?', (telegram_id,))
    if admin_id:
        cur.execute('''
            INSERT INTO moderation_actions (admin_id, target_id, action_type, reason)
            VALUES (?, ?, ?, ?)
        ''', (admin_id, telegram_id, 'unban', 'manual_unban'))
    conn.commit()
    conn.close()

def is_user_banned(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT is_banned, banned_until FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False
    is_banned, banned_until_str = row
    if not is_banned:
        return False
    if banned_until_str:
        banned_until = datetime.fromisoformat(banned_until_str)
        if banned_until > datetime.now():
            return True
        else:
            unban_user(telegram_id)
            return False
    return True