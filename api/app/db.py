"""SQLite storage. One connection per call (never shared across threads)."""

import os
import secrets
import sqlite3
import string
from collections.abc import Iterator
from contextlib import contextmanager

ALPHABET = string.digits + string.ascii_letters
RESERVED = {"healthz"}  # route names a code must never equal
MAX_ATTEMPTS = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
  code       TEXT PRIMARY KEY CHECK (length(code) = 7),
  url        TEXT NOT NULL UNIQUE CHECK (length(url) > 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
)
"""


class CodesExhausted(Exception):
    pass


def db_path() -> str:
    return os.environ.get("DB_PATH", "data/links.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path(), timeout=5)
    try:
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    os.makedirs(os.path.dirname(os.path.abspath(db_path())), exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # persists in the file
        conn.execute(SCHEMA)
        conn.commit()


def new_code() -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(7))
        if code not in RESERVED:
            return code


def ping() -> None:
    with connect() as conn:
        conn.execute("SELECT 1").fetchone()


def get_url(code: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT url FROM links WHERE code=?", (code,)).fetchone()
    return None if row is None else str(row[0])


def create_link(url: str) -> tuple[str, bool]:
    """Return (code, created). Insert-or-fetch with no check-then-act."""
    with connect() as conn:
        for _ in range(MAX_ATTEMPTS):
            code = new_code()
            try:
                # url UNIQUE + DO NOTHING absorbs duplicates; a code PK clash raises.
                cur = conn.execute(
                    "INSERT INTO links(code,url) VALUES(?,?) ON CONFLICT(url) DO NOTHING",
                    (code, url),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                continue  # code collision: retry with a fresh code
            if cur.rowcount == 1:
                conn.commit()
                return code, True
            row = conn.execute("SELECT code FROM links WHERE url=?", (url,)).fetchone()
            return str(row[0]), False
    raise CodesExhausted
