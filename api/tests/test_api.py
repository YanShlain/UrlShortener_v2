"""Acceptance tests for the URL shortener api (public HTTP contract only)."""

from __future__ import annotations

import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import count_rows, load_app, stored_urls
from fastapi.testclient import TestClient

CODE_RE = re.compile(r"^[0-9A-Za-z]{7}$")


def post(client: TestClient, url: Any) -> Any:
    return client.post("/api/links", json={"url": url})


def create(client: TestClient, url: str) -> str:
    r = post(client, url)
    assert r.status_code in (200, 201), r.text
    return str(r.json()["code"])


def location(client: TestClient, code: str) -> str:
    r = client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 302
    return str(r.headers["location"])


def assert_error(r: Any, status: int) -> None:
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"detail"}
    assert isinstance(body["detail"], str)
    assert body["detail"]


def force_chars(monkeypatch: pytest.MonkeyPatch, sequence: str) -> None:
    """Make `secrets.choice` emit `sequence` first, then behave normally."""
    queue = list(sequence)
    real = secrets.choice

    def fake(seq: Any) -> Any:
        if queue:
            return queue.pop(0)
        return real(seq)

    monkeypatch.setattr(secrets, "choice", fake)


def run_threads(n: int, target: Any) -> float:
    """Run target(i) in n threads released together by a barrier; return elapsed seconds."""
    barrier = threading.Barrier(n)

    def work(i: int) -> None:
        barrier.wait()
        target(i)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return time.perf_counter() - start


# ---------------------------------------------------------------- examples


def test_example_1_create_new_link(client: TestClient) -> None:
    # Given an empty DB
    # When posting a valid URL
    r = post(client, "https://example.com/docs")
    # Then 201 with a 7-char base62 code and short_url ending in /<code>
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"code", "short_url"}
    assert CODE_RE.match(body["code"])
    assert body["short_url"].endswith("/" + body["code"])


def test_example_2_duplicate_returns_200_same_code(client: TestClient) -> None:
    # Given the link exists
    first = post(client, "https://example.com/docs")
    # When the same URL is posted again
    second = post(client, "https://example.com/docs")
    # Then 200 with the same code
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["code"] == first.json()["code"]


def test_example_3_redirect(client: TestClient) -> None:
    # Given the link exists
    code = create(client, "https://example.com/docs")
    # When GET /<code>
    r = client.get(f"/{code}", follow_redirects=False)
    # Then 302, Location and no-store, empty body
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/docs"
    assert r.headers["cache-control"] == "no-store"
    assert r.content == b""


def test_example_4_trailing_slash_on_empty_path_same_code(tmp_path: Path) -> None:
    # Given http://a.com is stored, when http://a.com/ is posted, then same code (and reverse)
    with load_app(tmp_path / "a.db") as c:
        a = post(c, "http://a.com")
        b = post(c, "http://a.com/")
        assert a.status_code == 201
        assert b.status_code == 200
        assert a.json()["code"] == b.json()["code"]
    with load_app(tmp_path / "b.db") as c:
        a = post(c, "http://a.com/")
        b = post(c, "http://a.com")
        assert a.status_code == 201
        assert b.status_code == 200
        assert a.json()["code"] == b.json()["code"]


def test_example_5_scheme_host_lowercase_default_port(client: TestClient, db_path: Path) -> None:
    # Given HTTP://Example.COM:80/Path is posted
    code = create(client, "HTTP://Example.COM:80/Path")
    # Then stored and redirected URL is http://example.com/Path
    assert location(client, code) == "http://example.com/Path"
    assert stored_urls(db_path) == ["http://example.com/Path"]


def test_example_6_https_443_dropped(client: TestClient, db_path: Path) -> None:
    # Given https://a.com:443 is posted, then the stored URL is https://a.com/
    code = create(client, "https://a.com:443")
    assert location(client, code) == "https://a.com/"
    assert stored_urls(db_path) == ["https://a.com/"]


def test_example_7_empty_path_with_query(client: TestClient) -> None:
    # Given http://a.com?x=1 is posted, then the stored URL is http://a.com/?x=1
    code = create(client, "http://a.com?x=1")
    assert location(client, code) == "http://a.com/?x=1"


# ---------------------------------------------------------------- edges


def _url_of_length(n: int) -> str:
    prefix = "http://a.com/"
    return prefix + "x" * (n - len(prefix))


def test_edge_10_length_limit(client: TestClient) -> None:
    assert post(client, _url_of_length(2048)).status_code == 201
    assert_error(post(client, _url_of_length(2049)), 422)


def test_edge_10_length_limit_counts_after_trim(client: TestClient) -> None:
    assert post(client, "  " + _url_of_length(2048) + "  ").status_code == 201


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_edge_11_empty_or_whitespace(client: TestClient, value: str) -> None:
    assert_error(post(client, value), 422)


def test_edge_12_trimmed(client: TestClient) -> None:
    r = post(client, "   https://example.com/t   ")
    assert r.status_code == 201
    assert location(client, r.json()["code"]) == "https://example.com/t"


@pytest.mark.parametrize(
    "submitted,expected",
    [
        ("http://a.com:8080/", "http://a.com:8080/"),
        ("http://a.com:443/", "http://a.com:443/"),
        ("https://a.com:80/", "https://a.com:80/"),
    ],
)
def test_edge_13_non_default_ports_kept(client: TestClient, submitted: str, expected: str) -> None:
    assert location(client, create(client, submitted)) == expected


@pytest.mark.parametrize(
    "a,b",
    [
        ("http://a.com/docs", "http://a.com/docs/"),
        ("http://a.com/?a=1&b=2", "http://a.com/?b=2&a=1"),
        ("http://a.com/Path", "http://a.com/path"),
        ("http://a.com", "https://a.com"),
        ("http://a.com/p", "http://a.com/p#frag"),
    ],
)
def test_edge_14_16_distinct_urls_distinct_codes(client: TestClient, a: str, b: str) -> None:
    ra, rb = post(client, a), post(client, b)
    assert ra.status_code == 201
    assert rb.status_code == 201
    assert ra.json()["code"] != rb.json()["code"]


@pytest.mark.parametrize("path", ["/abc", "/Zzzzzzz", "/aaaaaaaa", "/..%2f", "/nope"])
def test_edge_17_unknown_code_404(client: TestClient, path: str) -> None:
    r = client.get(path, follow_redirects=False)
    assert_error(r, 404)
    assert r.json()["detail"] == "Not found"
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        " javascript:alert(1)",
        "data:text/html,x",
        "ftp://a.com",
        "file:///etc/passwd",
        "//a.com",
        "a.com",
    ],
)
def test_edge_18_bad_scheme(client: TestClient, db_path: Path, url: str) -> None:
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize("url", ["http://good.com@evil.com", "http://user:pw@a.com", "http://@a.com"])
def test_edge_19_userinfo(client: TestClient, db_path: Path, url: str) -> None:
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize("url", ["http://", "http:///path", "http://:80/", "https://?x=1"])
def test_edge_20_no_host(client: TestClient, db_path: Path, url: str) -> None:
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://a.com/a\tb",
        "http://a.com/a\nb",
        "http://a.com/a\rb",
        "http://a.com/a\x00b",
        "http://a.com/a\x7fb",
        "http://a.com/a b",
        "http://a.com/a b",
        "http://a.com/a b",
        "htt\tp://a.com/",
        "http://a.\ncom/",
    ],
)
def test_edge_21_control_and_whitespace(client: TestClient, db_path: Path, url: str) -> None:
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize("url", ["http://a.com:99999/", "http://a.com:abc/", "http://a.com:-1/"])
def test_edge_22_bad_port(client: TestClient, db_path: Path, url: str) -> None:
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize(
    "body",
    [{}, {"url": None}, {"url": 123}, {"url": ["http://a.com"]}, [], ["http://a.com"]],
)
def test_edge_23_bad_json_shapes(client: TestClient, body: Any) -> None:
    assert_error(client.post("/api/links", json=body), 422)


def test_edge_23_non_json_body(client: TestClient) -> None:
    hdr = {"Content-Type": "application/json"}
    r = client.post("/api/links", content=b"not json{", headers=hdr)
    assert_error(r, 422)


def test_edge_24_code_never_healthz(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    force_chars(monkeypatch, "healthz")
    r = post(client, "http://a.com/x")
    assert r.status_code == 201
    assert r.json()["code"] != "healthz"
    h = client.get("/healthz")
    assert h.status_code == 200
    assert h.json() == {"status": "ok"}


def test_edge_26_location_is_stored_value(client: TestClient) -> None:
    code = create(client, "http://a.com/p?q=1")
    r = client.get(f"/{code}", headers={"Location": "http://evil.com"}, follow_redirects=False)
    assert r.headers["location"] == "http://a.com/p?q=1"


def test_edge_29_stored_urls_are_normalized(client: TestClient, db_path: Path) -> None:
    for u in ["HTTP://A.com:80", "https://B.COM:443/X", "http://c.com:81/?q", "https://d.com"]:
        create(client, u)
    urls = stored_urls(db_path)
    assert sorted(urls) == sorted(
        ["http://a.com/", "https://b.com/X", "http://c.com:81/?q", "https://d.com/"]
    )


def test_edge_30_restart(db_path: Path) -> None:
    with load_app(db_path) as c1:
        codes = {u: create(c1, u) for u in ["http://a.com/1", "https://b.com/2?x=1"]}
    with load_app(db_path) as c2:
        for u, code in codes.items():
            assert location(c2, code) == u
        assert post(c2, "http://a.com/1").status_code == 200


def test_edge_32_no_store_on_redirect_and_404(client: TestClient) -> None:
    code = create(client, "http://a.com/ns")
    assert client.get(f"/{code}", follow_redirects=False).headers["cache-control"] == "no-store"
    assert client.get("/Zzzzzzz", follow_redirects=False).headers["cache-control"] == "no-store"


def test_edge_healthz_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------- api


def test_api_short_url_base_from_request_origin(client: TestClient) -> None:
    r = client.post(
        "/api/links", json={"url": "http://a.com/h"}, headers={"Host": "short.test:8080"}
    )
    assert r.json()["short_url"] == f"http://short.test:8080/{r.json()['code']}"


def test_api_short_url_base_url_env_wins(db_path: Path) -> None:
    with load_app(db_path, base_url="https://sho.rt/") as c:
        r = c.post("/api/links", json={"url": "http://a.com/h"}, headers={"Host": "other.test"})
        assert r.status_code == 201
        assert r.json()["short_url"] == f"https://sho.rt/{r.json()['code']}"


def test_api_codes_random_not_sequential(client: TestClient) -> None:
    codes = [create(client, f"http://a.com/{i}") for i in range(30)]
    assert len(set(codes)) == 30
    assert all(CODE_RE.match(c) for c in codes)
    assert codes != sorted(codes)


def test_api_error_bodies_are_detail_strings(client: TestClient) -> None:
    r = post(client, "ftp://a.com")
    assert isinstance(r.json()["detail"], str)


# ---------------------------------------------------------------- risk


def test_risk_fm1_concurrent_same_url(db_path: Path) -> None:
    """FM-1: concurrent creates of the same URL give one row, one 201, the rest 200."""
    n = 20
    with load_app(db_path) as primary:
        clients = [TestClient(primary.app, raise_server_exceptions=False) for _ in range(n)]
        results: list[Any] = [None] * n

        def work(i: int) -> None:
            results[i] = clients[i].post("/api/links", json={"url": "http://a.com/race"})

        elapsed = run_threads(n, work)
    assert elapsed < 5
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200] * (n - 1) + [201]
    assert len({r.json()["code"] for r in results}) == 1
    assert count_rows(db_path) == 1


def test_edge_concurrent_distinct_urls(db_path: Path) -> None:
    """Concurrent creates of distinct URLs never surface 500 or locked."""
    n = 20
    with load_app(db_path) as primary:
        clients = [TestClient(primary.app, raise_server_exceptions=False) for _ in range(n)]
        results: list[Any] = [None] * n

        def work(i: int) -> None:
            results[i] = clients[i].post("/api/links", json={"url": f"http://a.com/{i}"})

        run_threads(n, work)
    assert all(r.status_code == 201 for r in results)
    assert count_rows(db_path) == n


def test_risk_fm2_collision_retry_then_exhausted(
    client: TestClient, db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FM-2: code collision retries; 5 straight collisions give generic 500, no partial row."""
    existing = create(client, "http://a.com/existing")
    force_chars(monkeypatch, existing)
    r = post(client, "http://a.com/second")
    assert r.status_code == 201
    assert CODE_RE.match(r.json()["code"])
    assert r.json()["code"] != existing
    assert count_rows(db_path) == 2
    force_chars(monkeypatch, existing * 5)
    r = post(client, "http://a.com/third")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal error"}
    assert count_rows(db_path) == 2
    assert "http://a.com/third" not in stored_urls(db_path)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "  javascript:alert(1)",
        "data:text/html,x",
        "file:///etc/passwd",
        "ftp://a.com/",
        "//a.com/x",
        "vbscript:x",
    ],
)
def test_risk_fm3_dangerous_schemes(client: TestClient, db_path: Path, url: str) -> None:
    """FM-3: non-http(s) schemes give 422 and nothing is stored."""
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize(
    "url",
    ["http://user:pw@a.com/", "http://good.com@evil.com", "http://@a.com", "https://u@a.com"],
)
def test_risk_fm4_userinfo(client: TestClient, db_path: Path, url: str) -> None:
    """FM-4: userinfo gives 422 and nothing is stored."""
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize(
    "url", ["http://", "http:///path", "http://:80", "https://", "http://:80/x"]
)
def test_risk_fm5_missing_host(client: TestClient, db_path: Path, url: str) -> None:
    """FM-5: missing host gives 422."""
    assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize("ch", ["\t", "\r", "\n", "\x00", "\x7f", " ", " ", " ", "\x0b"])
def test_risk_fm6_control_chars(client: TestClient, db_path: Path, ch: str) -> None:
    """FM-6: control or whitespace chars (even ones urlsplit strips) give 422."""
    for url in (f"http://a.com/x{ch}y", f"http://a{ch}.com/", f"http://a.com/?q={ch}z"):
        assert_error(post(client, url), 422)
    assert count_rows(db_path) == 0


def test_risk_fm7_normalization_duplicates(client: TestClient, db_path: Path) -> None:
    """FM-7: normalization collapses exactly the agreed variants and nothing else."""
    same = ["http://a.com", "http://a.com/", "HTTP://A.COM", "http://A.com:80", "http://a.com:80/"]
    assert len({create(client, u) for u in same}) == 1
    https_same = ["https://a.com", "https://a.com:443/", "HTTPS://A.com"]
    assert len({create(client, u) for u in https_same}) == 1
    distinct = [
        "http://a.com/d",
        "http://a.com/d/",
        "http://a.com/D",
        "http://a.com/d?a=1&b=2",
        "http://a.com/d?b=2&a=1",
        "https://a.com/d",
        "http://a.com:8080/d",
    ]
    assert len({create(client, u) for u in distinct}) == len(distinct)
    assert count_rows(db_path) == 2 + len(distinct)


@pytest.mark.parametrize("path", ["/nope", "/Zzzzzzz", "/aaaaaaaa", "/..%2f", "/a%20b", "/%00"])
def test_risk_fm8_unknown_code(client: TestClient, path: str) -> None:
    """FM-8: unknown or malformed codes give 404 JSON with no-store, never 500."""
    r = client.get(path, follow_redirects=False)
    assert_error(r, 404)
    assert r.headers["cache-control"] == "no-store"


def test_risk_fm9_redirect_is_302_not_301(client: TestClient) -> None:
    """FM-9: redirect is exactly 302 with no-store, on repeated requests."""
    code = create(client, "http://a.com/c")
    for _ in range(2):
        r = client.get(f"/{code}", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["cache-control"] == "no-store"


def test_risk_fm10_restart_idempotent(db_path: Path) -> None:
    """FM-10: restart on an existing DB keeps all codes and startup is idempotent."""
    codes: dict[str, str] = {}
    with load_app(db_path) as c:
        for i in range(25):
            codes[f"http://a.com/{i}"] = create(c, f"http://a.com/{i}")
    for _ in range(2):
        with load_app(db_path) as c:
            for u, code in codes.items():
                assert location(c, code) == u
    assert count_rows(db_path) == 25


def test_risk_fm11_malformed_requests(client: TestClient, db_path: Path) -> None:
    """FM-11: malformed requests give 422 (413 if oversized) in detail-string format."""
    json_hdr = {"Content-Type": "application/json"}
    assert_error(client.post("/api/links", content=b"", headers=json_hdr), 422)
    assert_error(client.post("/api/links", content=b"{bad", headers=json_hdr), 422)
    assert_error(client.post("/api/links", json={"nourl": "x"}), 422)
    assert_error(client.post("/api/links", json={"url": 5}), 422)
    assert_error(client.post("/api/links", json=["http://a.com"]), 422)
    assert_error(
        client.post(
            "/api/links",
            content=b'{"url":"http://a.com/"}',
            headers={"Content-Type": "text/plain"},
        ),
        422,
    )
    big = client.post("/api/links", json={"url": "http://a.com/" + "x" * 20000})
    assert big.status_code in (413, 422)
    assert isinstance(big.json()["detail"], str)
    assert count_rows(db_path) == 0


@pytest.mark.parametrize("port", ["99999", "abc", "-1", "65536", "1x"])
def test_risk_fm12_invalid_port(client: TestClient, db_path: Path, port: str) -> None:
    """FM-12: invalid ports give 422, never a 500."""
    assert_error(post(client, f"http://a.com:{port}/"), 422)
    assert count_rows(db_path) == 0


def test_risk_fm13_healthz_never_shadowed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FM-13: generator never emits 'healthz' even when forced; /healthz stays 200."""
    force_chars(monkeypatch, "healthz" * 3)
    r = post(client, "http://a.com/shadow")
    assert r.status_code == 201
    assert r.json()["code"] != "healthz"
    h = client.get("/healthz", follow_redirects=False)
    assert h.status_code == 200
    assert h.json() == {"status": "ok"}


def test_risk_fm14_database_unavailable(db_path: Path) -> None:
    """FM-14: unusable DB gives healthz 503 and POST 500, no stack trace or path leaks."""
    with load_app(db_path) as c:
        create(c, "http://a.com/before")
        assert c.get("/healthz").status_code == 200
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        db_path.mkdir()  # a directory where the file should be: every connect fails
        h = c.get("/healthz")
        assert h.status_code == 503
        assert h.json() == {"detail": "database unavailable"}
        r = post(c, "http://a.com/after")
        assert r.status_code == 500
        assert r.json() == {"detail": "Internal error"}
        for text in (h.text, r.text):
            assert "Traceback" not in text
            assert str(db_path) not in text
            assert "sqlite" not in text.lower()


def test_risk_fm15_api_errors_are_displayable(client: TestClient, db_path: Path) -> None:
    """FM-15 (api side): 422 and 500 both carry a plain-string detail the UI can show."""
    r422 = post(client, "ftp://a.com")
    assert_error(r422, 422)
    assert "Traceback" not in r422.text
    mp = pytest.MonkeyPatch()
    try:
        existing = create(client, "http://a.com/e")
        force_chars(mp, existing * 5)
        r500 = post(client, "http://a.com/f")
    finally:
        mp.undo()
    assert r500.status_code == 500
    assert r500.json() == {"detail": "Internal error"}
    assert count_rows(db_path) == 1


def test_risk_fm16_base_url_precedence(db_path: Path) -> None:
    """FM-16: BASE_URL wins when set (trailing slash stripped); otherwise request origin."""
    with load_app(db_path, base_url="https://sho.rt///") as c:
        r = c.post("/api/links", json={"url": "http://a.com/b"}, headers={"Host": "internal:8000"})
        assert r.json()["short_url"] == f"https://sho.rt/{r.json()['code']}"
    with load_app(db_path) as c:
        r = c.post("/api/links", json={"url": "http://a.com/b"}, headers={"Host": "localhost:8080"})
        assert r.status_code == 200
        assert r.json()["short_url"] == f"http://localhost:8080/{r.json()['code']}"


def test_risk_fm17_html_in_url_is_data_only(client: TestClient) -> None:
    """FM-17 (api side): HTML-looking URL is data only, never rendered as an HTML response."""
    url = "http://a.com/<script>alert(1)</script>?q=<b>"
    code = create(client, url)
    r = client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("content-type", "").split(";")[0] != "text/html"
    assert r.content == b""


# ---------------------------------------------------------------- perf


def _seed(db_path: Path, n: int) -> list[str]:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS links ("
        "code TEXT PRIMARY KEY CHECK (length(code) = 7),"
        "url TEXT NOT NULL UNIQUE CHECK (length(url) > 0),"
        "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')))"
    )
    codes = [f"s{i:06d}" for i in range(n)]
    conn.executemany(
        "INSERT INTO links(code,url) VALUES(?,?)",
        [(code, f"http://seed.example/{i}") for i, code in enumerate(codes)],
    )
    conn.commit()
    conn.close()
    return codes


def test_perf_10k_links(db_path: Path) -> None:
    """Agreed load: 10,000 seeded links; 200 creates, 200 dupes, 1000 redirects < 15 s."""
    codes = _seed(db_path, 10_000)
    new_urls = [f"http://new.example/{i}" for i in range(200)]
    with load_app(db_path) as c:
        start = time.perf_counter()
        created: list[str] = []
        for u in new_urls:
            r = c.post("/api/links", json={"url": u})
            assert r.status_code == 201
            created.append(r.json()["code"])
        for u, code in zip(new_urls, created, strict=True):
            r = c.post("/api/links", json={"url": u})
            assert r.status_code == 200
            assert r.json()["code"] == code
        for i in range(1000):
            r = c.get(f"/{codes[(i * 7) % len(codes)]}", follow_redirects=False)
            assert r.status_code == 302
        assert c.get("/healthz").status_code == 200
        assert time.perf_counter() - start < 15


def test_perf_concurrent_creates_under_5s(db_path: Path) -> None:
    """20 concurrent creates over a seeded DB finish in under 5 s."""
    _seed(db_path, 10_000)
    n = 20
    with load_app(db_path) as primary:
        clients = [TestClient(primary.app, raise_server_exceptions=False) for _ in range(n)]
        out: list[int] = [0] * n

        def work(i: int) -> None:
            r = clients[i].post("/api/links", json={"url": f"http://p.example/{i}"})
            out[i] = r.status_code

        elapsed = run_threads(n, work)
    assert elapsed < 5
    assert out == [201] * n
