"""SQLite 상태 저장. 두 가지를 기억한다:
   1) 채용페이지 해시 — 바뀐 곳만 LLM에 보내려고
   2) 이미 보낸 공고 — 같은 걸 두 번 안 보내려고
"""
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent / "store" / "radar.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS page_hash (
    office_id  TEXT PRIMARY KEY,
    url        TEXT,
    hash       TEXT,
    checked_at TEXT,
    fail_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sent_posting (
    key        TEXT PRIMARY KEY,
    office_id  TEXT,
    title      TEXT,
    source_url TEXT,
    sent_at    TEXT,
    payload    TEXT
);
CREATE TABLE IF NOT EXISTS sweep_log (
    ran_at TEXT PRIMARY KEY
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def posting_key(office_id: str, title: str, source_url: str) -> str:
    """제목이 살짝 바뀌어도 같은 공고로 보이게 — url + 정규화한 제목으로 키를 만든다."""
    norm = "".join(title.split()).lower()
    return hashlib.sha256(f"{office_id}|{norm}|{source_url}".encode()).hexdigest()[:32]


def page_changed(conn, office_id: str, url: str, text: str, now: str) -> bool:
    """해시가 달라졌으면 True. 처음 보는 오피스도 True (한 번은 봐야 하니까)."""
    h = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
    row = conn.execute(
        "SELECT hash FROM page_hash WHERE office_id = ?", (office_id,)
    ).fetchone()
    conn.execute(
        "INSERT INTO page_hash (office_id, url, hash, checked_at, fail_count) "
        "VALUES (?,?,?,?,0) ON CONFLICT(office_id) DO UPDATE SET "
        "url=excluded.url, hash=excluded.hash, checked_at=excluded.checked_at, fail_count=0",
        (office_id, url, h, now),
    )
    conn.commit()
    return row is None or row[0] != h


def record_fetch_failure(conn, office_id: str, url: str, now: str) -> int:
    """가져오기 실패 누적. 계속 실패하면 그 오피스는 LLM 스윕으로 넘긴다."""
    conn.execute(
        "INSERT INTO page_hash (office_id, url, hash, checked_at, fail_count) "
        "VALUES (?,?,NULL,?,1) ON CONFLICT(office_id) DO UPDATE SET "
        "checked_at=excluded.checked_at, fail_count=page_hash.fail_count + 1",
        (office_id, url, now),
    )
    conn.commit()
    return conn.execute(
        "SELECT fail_count FROM page_hash WHERE office_id = ?", (office_id,)
    ).fetchone()[0]


def already_sent(conn, key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sent_posting WHERE key = ?", (key,)
    ).fetchone() is not None


def mark_sent(conn, key: str, posting, now: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sent_posting "
        "(key, office_id, title, source_url, sent_at, payload) VALUES (?,?,?,?,?,?)",
        (key, posting.office_id, posting.title, posting.source_url, now,
         json.dumps(posting.model_dump(), ensure_ascii=False)),
    )
    conn.commit()


def last_sweep(conn) -> Optional[str]:
    row = conn.execute("SELECT MAX(ran_at) FROM sweep_log").fetchone()
    return row[0] if row else None


def log_sweep(conn, now: str) -> None:
    conn.execute("INSERT OR IGNORE INTO sweep_log (ran_at) VALUES (?)", (now,))
    conn.commit()
