import sqlite3
from datetime import datetime

DB_PATH = "posts.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            scheduled_at DATETIME,
            sent_at DATETIME,
            status TEXT DEFAULT 'pending',
            "order" INTEGER DEFAULT 0,
            type TEXT DEFAULT 'regular'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

class Post:
    def __init__(self, id, text, folder_path, scheduled_at, sent_at, status, order=0, type='regular'):
        self.id = id
        self.text = text
        self.folder_path = folder_path
        self.scheduled_at = scheduled_at
        self.sent_at = sent_at
        self.status = status
        self.order = order
        self.type = type

    @staticmethod
    def from_row(row):
        return Post(
            id=row["id"],
            text=row["text"],
            folder_path=row["folder_path"],
            scheduled_at=row["scheduled_at"],
            sent_at=row["sent_at"],
            status=row["status"],
            order=row["order"],
            type=row["type"] if "type" in row.keys() else "regular"
        )

def set_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else None
