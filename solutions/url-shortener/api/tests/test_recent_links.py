"""v2 acceptance tests: GET /api/links (recent links list)."""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from conftest import count_rows, load_app
from fastapi.testclient import TestClient

CODE_RE = re.compile(r"^[0-9A-Za-z]{7}$")
KEYS = {"code", "short_url", "url", "created_at"}


def create(client: TestClient, url: str) -> tuple[int, str]:
    r = client.post("/api/links", json={"url": url})
    assert r.status_code in (200, 201), r.text
    return r.status_code, str(r.json()["code"])


def listing(client: TestClient) -> list[dict[str, Any]]:
    r = client.get("/api/links")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    return [dict(item) for item in body]


def urls_of(items: list[dict[str, Any]]) -> list[str]:
    return [str(i["url"]) for i in items]


def seed(db_path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Insert (code, url, created_at) rows in order (rowid grows with each)."""
    conn = sqlite3.connect(db_path)
    conn.executemany("INSERT INTO links(code,url,created_at) VALUES(?,?,?)", rows)
    conn.commit()
    conn.close()


def code_for(i: int) -> str:
    return f"s{i:06d}"


# ---------------------------------------------------------------- examples


def test_example_10_three_links_newest_first(client: TestClient) -> None:
    # Given 3 links created in order A, B, C
    _, a = create(client, "http://a.example/A")
    _, b = create(client, "http://a.example/B")
    _, c = create(client, "http://a.example/C")
    # When GET /api/links
    r = client.get("/api/links")
    # Then 200 and [C, B, A] with the four fields
    assert r.status_code == 200
    items = r.json()
    assert [i["code"] for i in items] == [c, b, a]
    assert urls_of(items) == ["http://a.example/C", "http://a.example/B", "http://a.example/A"]
    for item in items:
        assert set(item) == KEYS
        assert CODE_RE.match(item["code"])
        assert item["short_url"].endswith("/" + item["code"])
        assert isinstance(item["created_at"], str) and item["created_at"]


def test_example_11_twelve_links_returns_newest_ten(client: TestClient) -> None:
    # Given 12 links created in order 1..12
    for i in range(1, 13):
        create(client, f"http://a.example/{i}")
    # When GET /api/links
    items = listing(client)
    # Then exactly 10 items, 12 down to 3
    assert urls_of(items) == [f"http://a.example/{i}" for i in range(12, 2, -1)]


# ---------------------------------------------------------------- boundaries


def test_edge_22_empty_db_returns_empty_array(client: TestClient) -> None:
    # Given an empty DB / When GET /api/links / Then 200 and []
    r = client.get("/api/links")
    assert r.status_code == 200
    assert r.json() == []


def test_edge_23_exactly_10_and_11_links(client: TestClient) -> None:
    # Given exactly 10 links, then 10 items
    for i in range(10):
        create(client, f"http://b.example/{i}")
    assert len(listing(client)) == 10
    # Given an 11th link, then still 10 items and the oldest is absent
    create(client, "http://b.example/10")
    items = listing(client)
    assert len(items) == 10
    assert "http://b.example/0" not in urls_of(items)
    assert items[0]["url"] == "http://b.example/10"


def test_edge_24_same_second_orders_by_insertion(db_path: Path) -> None:
    # Given 5 rows with identical created_at
    with load_app(db_path) as c:
        stamp = "2026-01-01T00:00:00Z"
        seed(db_path, [(code_for(i), f"http://same.example/{i}", stamp) for i in range(5)])
        # Then newest first by insertion order
        items = listing(c)
    assert urls_of(items) == [f"http://same.example/{i}" for i in range(4, -1, -1)]


def test_edge_created_at_dominates_rowid(db_path: Path) -> None:
    """Order is by created_at first: an older stamp inserted later stays lower."""
    with load_app(db_path) as c:
        seed(
            db_path,
            [
                (code_for(1), "http://t.example/new", "2026-05-01T00:00:00Z"),
                (code_for(2), "http://t.example/old", "2026-01-01T00:00:00Z"),
            ],
        )
        items = listing(c)
    assert urls_of(items) == ["http://t.example/new", "http://t.example/old"]


def test_edge_query_params_ignored(client: TestClient) -> None:
    for i in range(12):
        create(client, f"http://q.example/{i}")
    r = client.get("/api/links", params={"limit": 1, "offset": 5, "foo": "bar"})
    assert r.status_code == 200
    assert len(r.json()) == 10
    assert r.json()[0]["url"] == "http://q.example/11"


# ---------------------------------------------------------------- traps


def test_edge_34_resubmit_does_not_reorder(client: TestClient) -> None:
    # Given A, B, C created
    _, a = create(client, "http://r.example/A")
    create(client, "http://r.example/B")
    create(client, "http://r.example/C")
    before = listing(client)
    # When A is resubmitted (and an empty-path variant of another URL)
    status, code = create(client, "http://r.example/A")
    create(client, "http://norm.example")
    status2, _ = create(client, "http://norm.example/")
    # Then 200, same code, A keeps its position, no duplicate rows
    assert status == 200 and code == a
    assert status2 == 200
    after = listing(client)
    assert after[1:] == before
    assert after[0]["url"] == "http://norm.example/"
    assert len(after) == 4
    assert len({i["code"] for i in after}) == 4


def test_edge_35_route_not_shadowed_and_methods(client: TestClient) -> None:
    # GET and POST on the same path both work
    assert client.post("/api/links", json={"url": "http://m.example/"}).status_code == 201
    assert client.get("/api/links").status_code == 200
    assert isinstance(client.get("/api/links").json(), list)
    # Other methods give 405 with the standard error format
    for method in ("PUT", "DELETE"):
        r = client.request(method, "/api/links")
        assert r.status_code == 405
        assert set(r.json()) == {"detail"}
        assert isinstance(r.json()["detail"], str)


def test_edge_short_url_base_url_env(db_path: Path) -> None:
    with load_app(db_path, base_url="https://sho.rt/") as c:
        _, code = create(c, "http://base.example/")
        items = listing(c)
    assert items[0]["short_url"] == f"https://sho.rt/{code}"


def test_edge_short_url_uses_forwarded_host(client: TestClient) -> None:
    _, code = create(client, "http://host.example/")
    r = client.get("/api/links", headers={"Host": "short.example:8080"})
    assert r.json()[0]["short_url"] == f"http://short.example:8080/{code}"
    assert "testserver" not in r.json()[0]["short_url"]


def test_edge_list_failure_is_generic_500(db_path: Path) -> None:
    """A broken DB gives the generic 500 and leaks nothing."""
    with load_app(db_path) as c:
        create(c, "http://x.example/")
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        db_path.mkdir()
        r = c.get("/api/links")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert "Traceback" not in r.text
    assert str(db_path) not in r.text
    assert "sqlite" not in r.text.lower()


# ---------------------------------------------------------------- invariants


def test_edge_45_every_listed_code_redirects_to_its_url(client: TestClient) -> None:
    for i in range(12):
        create(client, f"HTTP://Mixed.Example:80/P{i}")
    items = listing(client)
    assert len(items) <= 10
    for item in items:
        r = client.get(f"/{item['code']}", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == item["url"]
        assert item["url"].startswith("http://mixed.example/P")


def test_edge_46_list_is_read_only(client: TestClient, db_path: Path) -> None:
    for i in range(3):
        create(client, f"http://ro.example/{i}")
    before = count_rows(db_path)
    first = listing(client)
    for _ in range(5):
        assert listing(client) == first
    assert count_rows(db_path) == before


def test_edge_47_list_is_no_store(client: TestClient) -> None:
    r = client.get("/api/links")
    assert r.headers["cache-control"] == "no-store"
    create(client, "http://ns.example/")
    assert client.get("/api/links").headers["cache-control"] == "no-store"


def test_api_list_survives_restart(db_path: Path) -> None:
    with load_app(db_path) as c1:
        for i in range(3):
            create(c1, f"http://rs.example/{i}")
        before = listing(c1)
    with load_app(db_path) as c2:
        assert listing(c2) == before


# ---------------------------------------------------------------- risk (v2 failure modes)


def test_risk_fm18_ordering_and_tiebreaks(db_path: Path) -> None:
    """FM-18: same-second ties by rowid, resubmit keeps position, only newest 10."""
    with load_app(db_path) as c:
        stamp = "2026-02-02T02:02:02Z"
        seed(db_path, [(code_for(i), f"http://o.example/{i}", stamp) for i in range(12)])
        items = listing(c)
        assert urls_of(items) == [f"http://o.example/{i}" for i in range(11, 1, -1)]
        # resubmitting the oldest listed URL must not move it
        status, _ = create(c, "http://o.example/2")
        assert status == 200
        assert listing(c) == items
        # resubmitting an unlisted old URL must not bring it in
        status, _ = create(c, "http://o.example/0")
        assert status == 200
        assert listing(c) == items
        # a brand-new link goes to the top and pushes the oldest listed out
        create(c, "http://o.example/new")
        after = listing(c)
        assert after[0]["url"] == "http://o.example/new"
        assert urls_of(after[1:]) == urls_of(items[:9])


def test_risk_fm19_list_failure_is_isolated(db_path: Path) -> None:
    """FM-19: DB read failure gives generic 500; the service recovers once the DB is back."""
    with load_app(db_path) as c:
        create(c, "http://f.example/1")
        moved = Path(str(db_path) + ".bak")
        for suffix in ("-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        db_path.rename(moved)
        db_path.mkdir()
        r = c.get("/api/links")
        assert r.status_code == 500
        assert r.json() == {"detail": "Internal error"}
        db_path.rmdir()
        moved.rename(db_path)
        assert urls_of(listing(c)) == ["http://f.example/1"]
        assert c.post("/api/links", json={"url": "http://f.example/2"}).status_code == 201
        assert len(listing(c)) == 2


def test_risk_fm20_fresh_after_create_no_store(client: TestClient) -> None:
    """FM-20: each list read right after a create includes it and is never cacheable."""
    for i in range(4):
        r = client.post("/api/links", json={"url": f"http://fresh.example/{i}"})
        assert r.status_code == 201
        lr = client.get("/api/links")
        assert lr.headers["cache-control"] == "no-store"
        assert lr.json()[0]["code"] == r.json()["code"]
        assert lr.json()[0]["short_url"] == r.json()["short_url"]


def test_risk_fm22_privacy_notice_in_readme() -> None:
    """FM-22: the README documents that every visitor sees the recent links."""
    readme = Path(__file__).resolve().parent.parent.parent / "README.md"
    text = readme.read_text(encoding="utf-8").lower()
    assert "recent links" in text
    assert "visible to everyone" in text or "visible to all" in text


def test_risk_fm23_hostile_stored_data_is_inert_json(client: TestClient) -> None:
    """FM-23: markup, quotes, 2048-char and Unicode URLs come back verbatim as JSON strings."""
    long_url = "http://long.example/" + "a" * (2048 - len("http://long.example/"))
    script_url = 'http://a.com/"><script>alert(1)</script>'
    submitted = [
        script_url,
        "http://a.com/<img/src=x/onerror=alert(1)>?q='\"",
        long_url,
        "http://例え.example/‮אב",
    ]
    assert len(long_url) == 2048
    for u in submitted:
        create(client, u)
    r = client.get("/api/links")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    items = r.json()
    assert len(items) == 4
    returned = {i["url"] for i in items}
    assert long_url in returned
    assert script_url in returned
    for item in items:
        assert re.match(r"^http://[^/<>\"' ]+/[0-9A-Za-z]{7}$", item["short_url"])


# ---------------------------------------------------------------- perf


def test_perf_list_10k_rows(db_path: Path) -> None:
    """10,000 rows seeded; 200 sequential GET /api/links, p95 < 50 ms, total < 15 s."""
    rows = [
        (code_for(i), f"http://seed.example/{i}", f"2026-01-01T00:{i // 3600 % 60:02d}:00Z")
        for i in range(10_000)
    ]
    with load_app(db_path) as c:
        seed(db_path, rows)
        durations: list[float] = []
        start = time.perf_counter()
        for _ in range(200):
            t0 = time.perf_counter()
            r = c.get("/api/links")
            durations.append(time.perf_counter() - t0)
            assert r.status_code == 200
            assert len(r.json()) == 10
        total = time.perf_counter() - start
    durations.sort()
    assert durations[int(len(durations) * 0.95) - 1] < 0.05
    assert total < 15
