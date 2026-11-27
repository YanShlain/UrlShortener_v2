STATUS: READY

## What was built
v2 of the api: `GET /api/links` (10 newest links, `{code, short_url, url, created_at}`, `Cache-Control: no-store`) in `app/main.py`, `db.recent_links()` in `app/db.py`, and `base_url()` shared with POST. A "visible to everyone" notice was added to `solutions/url-shortener/README.md` (FM-22 test reads it). v1 behaviour is unchanged.

## Where each invariant and failure mode is handled
- FM-18 ordering: `app/db.py` `recent_links`, `ORDER BY created_at DESC, rowid DESC LIMIT ?` (limit is the constant `RECENT_LIMIT`).
- FM-13 routing: `app/main.py` `list_links` is registered before `/{code}`; 405 goes through `http_error`.
- FM-14 DB failure: `list_links` catches `sqlite3.Error` and returns 500 "Internal error".
- FM-16 base: `base_url()` in `app/main.py`, used by both handlers.
- FM-20 freshness: `NO_STORE` header on the list response.
- FM-22: README section "recent links (v2)".
- FM-1/2/7/10 etc.: unchanged from v1 (`app/db.py` `create_link`, `app/urls.py`).

## Decisions and trade-offs
No index added, as the design says. The README is outside the api folder, so I appended a short section because a locked test requires it.

## Local check results
ruff clean, `mypy --strict app tests` clean, pytest 144 passed, uvicorn boot: `/healthz` returns 200 and `/api/links` returns `[]`.
