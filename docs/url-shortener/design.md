SPEC: URL shortener (TinyURL-style) with recent-links list

Version 2. Changes versus v1 (`history/v1/design.md`) are marked "v2". Everything not marked is unchanged from v1 and stays binding.

## Contract
Delivered under `solutions/url-shortener/`:
- `api/`: FastAPI service (Python 3.12+, uv). Validates and normalizes URLs, stores links in SQLite, creates short codes, answers `GET /{code}` with a 302, exposes `GET /healthz`. v2: also exposes `GET /api/links`, the 10 most recent links.
- `web/`: React + TypeScript (Vite) single page. A form takes a long URL and shows the short URL with a copy button and server error messages. v2: under the form, a "Recent links" list. Each row is a link to the short URL that opens in a new tab, with the full URL as plain text. In Docker it is served by nginx, which proxies `/api/*` and `/{code}` to the api.
- `docker-compose.yml`: services `api` and `web`; SQLite file on the named volume `linkdata`.
- `README.md`: run instructions (local and Docker).

Out of scope: auth, aliases, expiry, click counters, rate limiting, deletion, phishing-domain blocking, preview page, normalization beyond the list below. v2: history beyond the fixed top 10 (no paging, search, per-user lists, polling, timestamps in the UI).

## Constraints
- URL input: trimmed first; length 1..2048 characters after trim.
- Code: exactly 7 characters from `[0-9A-Za-z]`, random (`secrets`), never sequential.
- Scale: demo, a few requests per second, thousands of links (tests use up to 10,000 rows).
- Normalization (the only one): lowercase scheme and host; drop `:80` for http and `:443` for https; empty path becomes `/`. Kept as submitted: http vs https, trailing slash on non-empty path, query order and content, path case, fragment, non-default port, IDN, percent-encoding.
- v2: the list size is fixed at 10 (no query parameters). Every visitor sees the same list (no accounts).
- Python 3.12+, SQLite 3.24+ (upsert support).

## Acceptance Scenarios

### Examples
1. Given an empty DB, when `POST /api/links {"url":"https://example.com/docs"}`, then 201 and body `{code, short_url}` with a 7-char base62 code and `short_url` ending in `/<code>`.
2. Given that link exists, when the same URL is posted again, then 200 with the same code.
3. Given the link exists, when `GET /<code>`, then 302, `Location: https://example.com/docs`, `Cache-Control: no-store`.
4. Given `http://a.com` is stored, when `http://a.com/` is posted, then 200 with the same code (and the reverse order gives the same result).
5. Given `HTTP://Example.COM:80/Path` is posted, then the stored and redirected URL is `http://example.com/Path`.
6. Given `https://a.com:443` is posted, then the stored URL is `https://a.com/`.
7. Given `http://a.com?x=1` is posted, then the stored URL is `http://a.com/?x=1`.
8. Given the UI, when the user submits a valid URL, then the short URL is shown as text with a Copy button; clicking Copy writes it to the clipboard and shows "Copied".
9. Given the UI and a 422 from the api, then the server's message is shown and no short URL is displayed.
10. (v2) Given 3 links created in order A, B, C, when `GET /api/links`, then 200 and a JSON array `[C, B, A]`, each item `{code, short_url, url, created_at}`; `short_url` ends in `/<code>` and `url` is the stored normalized URL.
11. (v2) Given 12 links created in order 1..12, when `GET /api/links`, then the array has exactly 10 items, newest first (12 down to 3).
12. (v2) Given the UI with 2 links in the API, when the page opens, then a "Recent links" list shows 2 rows, newest first. Each row has an `<a>` whose `href` is the item's `short_url`, `target="_blank"`, `rel="noopener noreferrer"`, and the full URL as plain text.
13. (v2) Given the page is open, when the user submits a new valid URL successfully, then `GET /api/links` is requested again and the new link appears at the top of the list.

### Boundaries
14. A URL of exactly 2048 characters (after trim) is accepted; 2049 gives 422.
15. Empty string or whitespace-only gives 422.
16. Input with leading/trailing spaces around a valid URL is trimmed and accepted.
17. `http://a.com:8080/` keeps `:8080`; `http://a.com:443/` keeps `:443`; `https://a.com:80/` keeps `:80`.
18. `http://a.com/docs` and `http://a.com/docs/` give different codes.
19. `http://a.com/?a=1&b=2` and `http://a.com/?b=2&a=1` give different codes. `http://a.com/Path` and `http://a.com/path` give different codes.
20. `http://a.com` and `https://a.com` give different codes.
21. `GET /abc` (not 7 chars) and `GET /Zzzzzzz` (unknown 7-char code) give 404 JSON error.
22. (v2) Empty DB: `GET /api/links` returns 200 and `[]`; the UI shows an empty-state text (for example "No links yet") and no list items.
23. (v2) Exactly 10 links: 10 items returned. Exactly 11: 10 items, the oldest absent.
24. (v2) Links created within the same second (identical `created_at`): order is still newest first, by insertion order (`rowid DESC`).

### Traps
25. `javascript:alert(1)`, `JavaScript:alert(1)`, ` javascript:alert(1)`, `data:text/html,x`, `ftp://a.com`, `file:///etc/passwd`, `//a.com`, `a.com` all give 422.
26. `http://good.com@evil.com`, `http://user:pw@a.com` and `http://@a.com` give 422 (userinfo).
27. `http://`, `http:///path`, `http://:80/`, `https://?x=1` give 422 (no host).
28. A URL containing a tab, newline, carriage return, NUL, DEL, a space, or a Unicode whitespace character (e.g. U+00A0, U+2028) inside gives 422. Python's `urlsplit` silently strips tab/CR/LF, so the check runs on the raw string before parsing.
29. `http://a.com:99999/` and `http://a.com:abc/` give 422 (invalid port), never 500.
30. Body `{}`, `{"url":null}`, `{"url":123}`, a non-JSON body, or a JSON array give 422 with the standard error format.
31. A link whose generated code would be `healthz` (or any route name) must not shadow `GET /healthz`: the generator never emits `healthz`.
32. A URL such as `http://a.com/<script>` is shown in the UI (result and list) as text and is never inserted as HTML.
33. A redirect `Location` value is always the stored normalized URL, never user-supplied header text (no CR/LF possible, see 28).
34. (v2) Resubmitting an existing URL (including its `http://a.com` vs `http://a.com/` variant) returns 200 and does not change the list: the link keeps its original position and no duplicate row appears.
35. (v2) `GET /api/links` is not shadowed by `GET /{code}`, and `POST /api/links` still works; `/api/links` is not a valid 7-char code. Other methods on `/api/links` (PUT, DELETE) give 405 in the `{"detail": string}` format.
36. (v2) The list anchor `href` comes from the api's `short_url` (server-generated `<base>/<code>`), never from the stored full URL. A stored URL like `http://a.com/"><script>` or one starting `javascript:`-like text cannot become an `href`; it appears only as text content.
37. (v2) When `GET /api/links` fails (network error or 500), the UI shows a short error message in the list area (for example "Could not load recent links"); the form still works and a later successful create reloads the list.
38. (v2) A very long full URL (2048 chars) in a row does not break the layout: the text wraps or truncates by CSS; the full text stays in the DOM.

### Invariants
39. At most one row per normalized URL, and one row per code, at all times, under concurrent creates.
40. N parallel `POST` of the same URL yield exactly one 201, N-1 responses with 200, one code, one row.
41. Every stored `url` has scheme `http`/`https`, a non-empty host, no userinfo, and is in normalized form.
42. After an api restart (new process, same DB file), every earlier code still redirects and the list is unchanged.
43. A code collision on insert is retried with a new code, and the client still gets a 201 with a valid code.
44. Redirect responses always carry `Cache-Control: no-store`, whether 302 or 404.
45. (v2) `GET /api/links` returns at most 10 items, sorted by `(created_at, rowid)` descending, and every item's `code` redirects (302) to its `url`.
46. (v2) `GET /api/links` is read-only: it never inserts, updates or deletes, and the row count is the same before and after.
47. (v2) `GET /api/links` carries `Cache-Control: no-store`, so the refresh after a create is never served from a browser or proxy cache.

## Performance SLA
- Agreed load: ~5 requests per second, up to 10,000 stored links.
- Targets (single uvicorn worker, local disk): `POST /api/links` p95 < 100 ms; `GET /{code}` p95 < 30 ms; `GET /healthz` p95 < 20 ms. v2: `GET /api/links` p95 < 50 ms with 10,000 rows.
- Perf test input: DB pre-seeded with 10,000 links; then 200 sequential creates of new URLs, 200 duplicate creates, 1,000 sequential redirects and 200 sequential `GET /api/links` through `TestClient`/httpx. Time budget: the whole test finishes in under 15 seconds (a correct solution needs roughly 2-4 s), and the 20-thread concurrent-create test finishes in under 5 seconds.

## API Contract
Error format for every error: `{"detail": "<human-readable message>"}` (string, never a list). FastAPI's default validation error shape is replaced by a handler that returns this format with status 422.

### `POST /api/links`
- Request: `Content-Type: application/json`, `{"url": "<string>"}`.
- 201: `{"code": "aB3dE9x", "short_url": "<base>/aB3dE9x"}` for a new link.
- 200: same body when the normalized URL already exists.
- 413: body over 8 KB.
- 422: invalid input (missing/non-string `url`, empty, > 2048, scheme, host, userinfo, control chars/whitespace, bad port, malformed body). `detail` carries a specific message (e.g. "URL must start with http:// or https://").
- 500: `{"detail": "Internal error"}` for anything unexpected (e.g. code retries exhausted); no stack trace in the body.
- `<base>` is `BASE_URL` (trailing slash stripped) if set, otherwise the request origin (`scheme://host` from the request, which respects the `Host` header the proxy forwards). v2: the same base logic is shared with `GET /api/links` (one helper, not two copies).

### `GET /api/links` (v2)
- Request: no body, no query parameters (unknown parameters are ignored).
- 200: JSON array of at most 10 objects, newest first:
  `[{"code": "aB3dE9x", "short_url": "<base>/aB3dE9x", "url": "https://example.com/docs", "created_at": "2026-11-27T10:15:00Z"}]`
  An empty DB gives `[]`. `url` is the stored normalized URL. `created_at` is the stored UTC string, returned as is (the UI does not show it).
- Headers: `Cache-Control: no-store`.
- 500: `{"detail": "Internal error"}` if the DB read fails (`sqlite3.Error`); no stack trace or path.
- 405 for other methods on this path (same `{"detail"}` format).
- Public by design: no auth, anyone who can reach the api sees all listed URLs (see Security).

### `GET /{code}`
- Route accepts only `[0-9A-Za-z]{7}`; anything else is 404.
- 302: `Location: <stored normalized url>`, `Cache-Control: no-store`, empty body.
- 404: `{"detail": "Not found"}` with `Cache-Control: no-store`.

### `GET /healthz`
- 200 `{"status": "ok"}`. Runs `SELECT 1` on the DB; 503 `{"detail": "database unavailable"}` if that fails. Registered before `/{code}`.

### Web service
- `GET /healthz` on nginx returns 200 `ok` (Docker healthcheck).
- Proxy rules (nginx in Docker, Vite `server.proxy` in dev), forwarding the original `Host`: `/api/*` to api (already covers `GET /api/links`, so no config change); `^/[0-9A-Za-z]{7}$` to api; everything else serves the SPA.
- v2 UI behavior:
  - `web/src/api.ts` gains `listLinks(): Promise<LinkItem[]>` (`GET /api/links`), with the same error mapping as create. `LinkItem = {code, short_url, url, created_at}`.
  - `App.tsx` (or a small `RecentLinks` component next to it) loads the list on mount and again after each successful create (200 or 201). It has three states: loading/ok/error. A failed list load never clears or blocks the form and never shows as the form's error.
  - Each row: `<a href={short_url} target="_blank" rel="noopener noreferrer">{short_url}</a>` followed by the full `url` as a text node. No `dangerouslySetInnerHTML`; React keys by `code`.
  - Out-of-order responses: if two list loads overlap, only the latest request may set the state (ignore stale results).
  - "Chrome" in the request is read as "a new browser tab": `target="_blank"`, no browser-specific code.

## Data Model
SQLite file, path from env `DB_PATH` (default `data/links.db` relative to the api folder; `/data/links.db` in Docker on the volume). v2: no schema change and no migration; the existing table and `created_at` column are reused.

```sql
CREATE TABLE IF NOT EXISTS links (
  code       TEXT PRIMARY KEY CHECK (length(code) = 7),
  url        TEXT NOT NULL UNIQUE CHECK (length(url) > 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
```
- `code` primary key gives the lookup index for redirects; `url` UNIQUE gives the duplicate index. No other indexes: at the agreed size (thousands of rows) the list query sorts at most 10,000 rows in a few ms. If the table grows far beyond that, add `CREATE INDEX idx_links_created ON links(created_at, rowid)`; not needed now.
- Connection settings per connection: `PRAGMA journal_mode=WAL` (set once in `init_db`, persists in the file), `timeout=5` (busy timeout), `PRAGMA synchronous=NORMAL`. One connection per call; no shared connection across threads.
- Create flow (no check-then-act): `INSERT INTO links(code,url) VALUES(?,?) ON CONFLICT(url) DO NOTHING`. If `rowcount == 1`: 201 with the new code. Else `SELECT code FROM links WHERE url=?` and return 200. A `sqlite3.IntegrityError` (the code PK collided) triggers a retry with a new code, up to 5 attempts, then 500.
- v2 list query (single statement, parameterized, read-only): `SELECT code, url, created_at FROM links ORDER BY created_at DESC, rowid DESC LIMIT 10`. `rowid` breaks ties inside the same second; it grows with each insert, and rows are never deleted, so it equals insertion order. Resubmits take the DO NOTHING path and write nothing, so order never changes.
- Schema is created at startup (`CREATE TABLE IF NOT EXISTS`); no migrations needed.

## Invariants
| Invariant | Enforced by |
|---|---|
| One row per normalized URL | `UNIQUE` on `links.url` plus `ON CONFLICT(url) DO NOTHING` (single statement, no prior SELECT) |
| Code unique | `PRIMARY KEY` on `links.code`; retry on `IntegrityError` |
| Code is 7 chars | `CHECK (length(code)=7)` plus generator |
| Only safe, normalized URLs stored | Single `normalize_url()` function that is the only path to the INSERT; DB `CHECK` on non-empty |
| No lost/duplicate concurrent creates | SQLite write serialization, WAL, busy timeout 5 s |
| Durability across restarts | SQLite file on a Docker named volume |
| Redirect never cached | Response headers `Cache-Control: no-store` on 302 and 404 |
| Redirect target is the stored value | Handler reads `url` from DB only; no request data in `Location` |
| (v2) List is at most 10 and newest first | `ORDER BY created_at DESC, rowid DESC LIMIT 10` in one SQL statement; the limit is a constant, never taken from the request |
| (v2) Resubmit does not reorder | The upsert writes nothing on conflict; the list sorts by the immutable `created_at`/`rowid` (no `updated_at`, no row rewrite) |
| (v2) List is read-only and fresh | The handler runs one `SELECT` only; `Cache-Control: no-store` on the response |
| (v2) Listed URLs cannot become markup or `href` | React text nodes only; `href` is the server-built `short_url`; no `dangerouslySetInnerHTML` |

## Security
- Trust boundary: the browser and any HTTP client are untrusted. All validation runs in the api; UI checks are convenience only.
- Validation order in `normalize_url(raw)`: (1) type is str; (2) trim; (3) non-empty and length <= 2048; (4) reject any character that is a control character (`ord < 32` or `== 127`) or `str.isspace()`, checked on the raw trimmed string before parsing; (5) `urlsplit` (catch `ValueError`); (6) `scheme.lower()` in `{http, https}`, and the string must carry `://` after the scheme (so `javascript:` and `a.com` fail); (7) `hostname` non-empty; (8) no `@` in `netloc` (userinfo); (9) `.port` access validated (0-65535, catches `ValueError`); (10) rebuild with lowercase scheme and host, default port dropped, empty path `/`.
- Abuse cases:
  - `javascript:`/`data:` XSS via redirect or UI: scheme allowlist, case-insensitive; UI renders text only. v2: the only `href` the UI builds is the api's `short_url`; the full URL is shown as text, so even a stored URL never reaches an `href` in the page. Clicking the short link goes through the 302, where the stored URL is already limited to http/https.
  - Phishing `good.com@evil.com`: userinfo rejected.
  - Header injection via CR/LF in the URL: rejected before parsing; Starlette also rejects them.
  - Oversized input: 2048 limit on the string, and a request-body cap of 8 KB (413).
  - SQL injection: parameterized queries only; no string formatting into SQL.
  - Code enumeration: random 7-char base62 (62^7 ~ 3.5e12).
  - Open redirect to an attacker site: accepted by design (out of scope); documented in the README.
  - Rate limiting and blocklists: not implemented (agreed).
  - (v2) Privacy exposure: `GET /api/links` makes every submitted URL readable by any visitor, including URLs with secrets in query strings (tokens, signed links). This is accepted (clarification 15) and must be stated in the README and the UI (a short line near the list, for example "Recent links are visible to everyone"). Mitigation by design is limited to the fixed 10-item window; no other filtering.
  - (v2) Tabnabbing via `target="_blank"`: `rel="noopener noreferrer"` on every list anchor.
  - (v2) Stored XSS through a list row: URL text goes through React text nodes only; `<script>` and quotes stay inert.
  - (v2) Scraping or load on the new endpoint: fixed small result, single indexed-size query; no parameters to abuse (no `limit`, no offset); rate limiting stays out of scope.
  - (v2) Stale or cross-visitor cache of the list: `no-store`.
- No CORS: same-origin through the proxy. No secrets exist; `BASE_URL` is not secret.
- Containers run as a non-root user.

## Failure Modes
- FM-1: Concurrent creates of the same URL. Expected: exactly one row and one code; one 201, the others 200 with the same code; no 500 and no "database is locked" surfaced.
- FM-2: Code collision on insert (forced via a patched generator). Expected: retry with a fresh code; 201; after 5 straight collisions return 500 with the generic error and no partial row.
- FM-3: `javascript:` in any case or with leading whitespace, `data:`, `file:`, `ftp:`, scheme-relative `//host`. Expected: 422, nothing stored.
- FM-4: Userinfo (`user:pw@host`, `good.com@evil.com`, `@host`). Expected: 422, nothing stored.
- FM-5: Missing host (`http://`, `http:///path`, `http://:80`). Expected: 422.
- FM-6: Control characters or whitespace (tab, CR, LF, NUL, DEL, space, U+00A0) inside the URL, including those `urlsplit` would silently strip. Expected: 422.
- FM-7: Duplicate detection around normalization: `http://a.com` vs `http://a.com/`, host case, default ports collapse to one code; http vs https, trailing slash on non-empty path, query order and path case stay distinct.
- FM-8: Unknown or malformed code (`/nope`, `/Zzzzzzz`, `/aaaaaaaa`, `/..%2f`). Expected: 404 JSON, `no-store`, never 500.
- FM-9: Caching surprise: redirect must be 302 (not 301) with `Cache-Control: no-store`, so a second request hits the api.
- FM-10: Restart: data written, process/app recreated on the same DB file. Expected: all codes still resolve and the list is unchanged; startup is idempotent on an existing DB.
- FM-11: Malformed requests: missing `url`, wrong type, invalid JSON, array body, oversized body, wrong content type. Expected: 422 (or 413 for oversized) in the `{"detail": string}` format, never 500.
- FM-12: Invalid port (`:99999`, `:abc`, `:-1`). Expected: 422, not an unhandled `ValueError`.
- FM-13: Route shadowing: generated code equal to `healthz`. Expected: never generated; `/healthz` stays 200. v2: `GET /api/links` is also never captured by `/{code}` (it has a slash and 3 segments of letters is not a 7-char code), and POST and GET on the same path both work.
- FM-14: Database unavailable (file not writable, locked longer than the timeout). Expected: `/healthz` returns 503; POST returns 500 with the generic message; v2: `GET /api/links` returns 500 with the generic message; no stack trace or path leaks.
- FM-15: UI error paths: api returns 422, 500, or the network fails; clipboard API missing or rejected. Expected: an error message is shown, the UI stays usable, and no stale short URL remains from the previous success.
- FM-16: Short URL base: behind the proxy the `Host` header must be forwarded, otherwise `short_url` would point at the internal api host. Expected: `BASE_URL` wins when set; otherwise the request origin. v2: this applies to the list too; a list link that pointed at `http://api:8000/<code>` would not open from the browser.
- FM-17: XSS via displayed data: a URL with `<script>` or HTML in query/path is rendered as plain text, in the result box and in the list.
- FM-18 (v2): Ordering and tie-breaks. Links created in the same second must still be ordered newest first (`rowid DESC`); resubmitting an old URL must not move it; with more than 10 links only the newest 10 appear. Expected: exact order asserted in tests.
- FM-19 (v2): List load fails (api down, 500, network error, invalid JSON). Expected: an inline error in the list area; the form keeps working; the next successful create or page load recovers the list.
- FM-20 (v2): Stale list after create, or a race between two loads. Expected: the list is reloaded after every successful create; an older response never overwrites a newer one; `no-store` stops cached results.
- FM-21 (v2): Link opens in the same tab or exposes `window.opener`. Expected: every anchor has `target="_blank"` and `rel="noopener noreferrer"`.
- FM-22 (v2): Privacy exposure: URLs submitted by one visitor appear for all visitors, including sensitive query strings. Expected: documented and visible in the UI; not filtered (accepted). A test asserts the notice text is present.
- FM-23 (v2): Hostile stored data in the list: a URL with markup, quotes, a 2048-char string, or Unicode (IDN, RTL characters). Expected: shown as inert text, no layout break, no `href` built from it.

## Scaling
At demo scale one uvicorn worker and one SQLite file are enough. Writes are serialized by SQLite, so the first limit is write throughput (hundreds of inserts per second in WAL mode), far above the target of a few requests per second. Redirect reads are single primary-key lookups. v2: the list is a 10-row read that sorts the table by `created_at`; this stays in the low milliseconds up to tens of thousands of rows and is the first read that degrades with table size. The fix is the composite index `(created_at, rowid)`, then a short in-process cache (for example 1-2 s, invalidated on create), then a Redis cache. The web page makes one extra GET per page load and per create, which is negligible at a few requests per second. Beyond demo scale: add an in-process or Redis cache for code-to-URL (safe, since links are immutable), then move to Postgres for multiple api replicas (SQLite on a shared volume does not support multiple writer hosts). Rate limiting at the proxy is the next control if abused.

## Deployment
Local (from `solutions/url-shortener/`):
- api: `cd api && uv sync && uv run uvicorn app.main:app --port 8000`
- web: `cd web && npm install && npm run dev` (Vite on 5173, proxies `/api` and `^/[0-9A-Za-z]{7}$` to `http://localhost:8000`, with `Host` preserved).
- Env: `DB_PATH` (default `data/links.db` in the api folder), `BASE_URL` (optional).

Docker:
- `api/Dockerfile`: python:3.12-slim, uv install, non-root user, `EXPOSE 8000`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `web/Dockerfile`: multi-stage, `node:22` build then `nginx:alpine` with `nginx.conf` (proxy rules above, `proxy_set_header Host $http_host`, `/healthz` returns 200).
- `docker-compose.yml`: `api` (env `DB_PATH=/data/links.db`, volume `linkdata:/data`, healthcheck calling `/healthz` with Python urllib, not curl) and `web` (port `8080:80`, `depends_on: api: condition: service_healthy`, healthcheck `wget -qO- http://localhost/healthz`). Users open `http://localhost:8080`. v2: no compose or nginx change; the existing volume keeps old links, which appear in the new list.
- No Kubernetes manifests (DEPLOY is docker).

Service layout conventions:
- Python service (`api/`): uv project, `pyproject.toml` with dev deps ruff, mypy, pytest, httpx; code in `app/` (`main.py` exposes `app`, plus `urls.py` for `normalize_url`, `db.py` for storage; v2 adds `db.recent_links(limit)` and the `GET /api/links` handler in `main.py`); tests in `tests/`. Commands: `uv run pytest`, `uv run ruff check .`, `uv run mypy app`.
- React service (`web/`): Vite + TypeScript, `package.json` scripts `typecheck` (`tsc --noEmit`), `test` (`vitest run`), `build` (`vite build`); tests next to code as `*.test.ts(x)` (Vitest + Testing Library, jsdom). v2: tests mock `fetch` for `GET /api/links` and check anchor attributes, text rendering, refresh after create and list-error handling.
