"""Shared fixtures: a fresh app + temporary SQLite file per test."""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parent.parent
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def load_app(db_path: Path, base_url: str | None = None) -> TestClient:
    """Import a fresh `app.main:app` bound to `db_path` (simulates a new process)."""
    os.environ["DB_PATH"] = str(db_path)
    if base_url is None:
        os.environ.pop("BASE_URL", None)
    else:
        os.environ["BASE_URL"] = base_url
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[name]
    importlib.invalidate_caches()
    main = importlib.import_module("app.main")
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "links.db"


@pytest.fixture
def client(db_path: Path) -> Iterator[TestClient]:
    with load_app(db_path) as c:
        yield c


def count_rows(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("SELECT count(*) FROM links").fetchone()[0])
    finally:
        conn.close()


def stored_urls(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [str(r[0]) for r in conn.execute("SELECT url FROM links")]
    finally:
        conn.close()
