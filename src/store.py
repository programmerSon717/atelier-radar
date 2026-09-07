"""SQLite 상태 저장. 두 가지를 기억한다:
   1) 채용페이지 해시 — 바뀐 곳만 LLM에 보내려고
   2) 이미 보낸 공고 — 같은 걸 두 번 안 보내려고
"""
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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


# 잡보드 링크에는 검색어·세션 같은 게 붙어 매번 달라진다. 그대로 키에 넣으면
# 같은 공고가 다음 실행에 새 공고로 보인다. 공고를 특정하는 파라미터만 남긴다.
_ID_PARAMS = ("rec_idx", "jobno", "j", "id", "no", "idx", "gi_no")


def normalize_url(url: str) -> str:
    try:
        u = urlparse(url)
    except ValueError:
        return url
    keep = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=False)
            if k.lower() in _ID_PARAMS]
    keep.sort()
    return urlunparse((u.scheme, u.netloc.lower(), u.path.rstrip("/"), "",
                       urlencode(keep), ""))


def posting_key(office_id: str, title: str, source_url: str) -> str:
    """제목이 살짝 바뀌어도, 링크에 추적 파라미터가 붙어도 같은 공고로 본다."""
    norm = "".join(title.split()).lower()
    return hashlib.sha256(
        f"{office_id}|{norm}|{normalize_url(source_url)}".encode()
    ).hexdigest()[:32]


def page_hash_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def page_changed(conn, office_id: str, text: str) -> bool:
    """해시가 달라졌으면 True. 처음 보는 오피스도 True (한 번은 봐야 하니까).

    ★ 여기서 저장하지 않는다. 추출과 발송까지 성공한 뒤에 commit_page_hash 로 저장한다.
    먼저 저장해 버리면, 추출이 실패(무료 티어 한도 등)했을 때 다음 실행이
    "안 바뀌었네" 하고 건너뛰어 그 공고를 영영 못 본다."""
    row = conn.execute(
        "SELECT hash FROM page_hash WHERE office_id = ?", (office_id,)
    ).fetchone()
    return row is None or row[0] != page_hash_of(text)


def commit_page_hash(conn, office_id: str, url: str, text: str, now: str) -> None:
    """이 오피스를 끝까지 처리했다. 이제 본 것으로 기록한다."""
    conn.execute(
        "INSERT INTO page_hash (office_id, url, hash, checked_at, fail_count) "
        "VALUES (?,?,?,?,0) ON CONFLICT(office_id) DO UPDATE SET "
        "url=excluded.url, hash=excluded.hash, checked_at=excluded.checked_at, fail_count=0",
        (office_id, url, page_hash_of(text), now),
    )
    conn.commit()


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
