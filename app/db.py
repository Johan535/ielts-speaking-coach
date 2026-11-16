"""SQLite 数据层：练习记录、评分、弱点档案、语料库、打卡"""
import sqlite3
from pathlib import Path

from .paths import db_path

DB_PATH = db_path()

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,             -- YYYY-MM-DD
    topic TEXT NOT NULL,
    rounds INTEGER DEFAULT 0,
    comment TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    fluency REAL, vocabulary REAL, grammar REAL, pronunciation REAL,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS weaknesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL UNIQUE,      -- 错句摘要，如 "I very like -> I really like"
    category TEXT DEFAULT 'general',
    topic TEXT DEFAULT '',
    count INTEGER DEFAULT 1,
    last_seen TEXT,
    resolved INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS corpus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expression TEXT NOT NULL UNIQUE,
    translation TEXT DEFAULT '',
    source TEXT DEFAULT 'dialogue',
    times_reviewed INTEGER DEFAULT 0,
    next_review_at TEXT,
    mastered INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS checkins (
    date TEXT PRIMARY KEY,
    session_id INTEGER,
    completed INTEGER DEFAULT 1
);
"""


def connect(db_path=None):
    """打开数据库并初始化表结构。db_path 可以是路径或 ':memory:'（测试用）。"""
    if db_path is None:
        db_path = DB_PATH
    if str(db_path) == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        p = Path(db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
