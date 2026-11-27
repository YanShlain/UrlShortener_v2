SPEC: URL shortener (TinyURL-style)

## Contract
Delivered at the workspace root:
- `api/`: FastAPI service (Python 3.12+, uv). Validates and normalizes URLs, stores links in SQLite, creates short codes, answers `GET /{code}` with a 302. Exposes `GET /healthz`.
- `web/`: React + TypeScript (Vite) single page. A form takes a long URL and shows the short URL with a copy button and server error messages. In Docker it is served by nginx, which also proxies `/api/*` and `/{code}` to the api.
- `docker-compose.yml`: services `api` and `web`; SQLite file on the named volume `linkdata`.
- `README.md`: run instructions (local and Docker).

Out of scope: auth, aliases, expiry, click counters, history, rate limiting, deletion, phishing-domain blocking, preview page, any normalization beyond the list below.

## Constraints
- URL input: trimmed first; length 1..2048 characters after trim.
- Code: exactly 7 characters from `[0-9A-Za-z]`, random (`secrets`), never sequential.
- Scale: demo, a few requests per second, thousands of links (tests use up to 10,000 rows).
- Normalization (the only one): lowercase scheme and host; drop `:80` for http and `:443` for https; empty path becomes `/`. Kept as submitted: http vs https, trailing slash on non-empty path, query order and content, path case, fragment, non-default port, IDN, percent-encoding.
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

### Boundaries
10. A URL of exactly 2048 characters (after trim) is accepted; 2049 gives 422.
11. Empty string or whitespace-only gives 422.
12. Input with leading/trailing spaces around a valid URL is trimmed and accepted.
13. `http://a.com:8080/` keeps `:8080`; `http://a.com:443/` keeps `:443`; `https://a.com:80/` keeps `:80`.
14. `http://a.com/docs` and `http://a.com/docs/` give different codes.
15. `http://a.com/?a=1&b=2` and `http://a.com/?b=2&a=1` give different codes. `http://a.com/Path` and `http://a.com/path` give different codes.
16. `http://a.com` and `https://a.com` give different codes.
17. `GET /abc` (not 7 chars) and `GET /Zzzzzzz` (unknown 7-char code) give 404 JSON error.

### Traps
18. `javascript:alert(1)`, `JavaScript:alert(1)`, ` javascript:alert(1)`, `data:text/html,x`, `ftp://a.com`, `file:///etc/passwd`, `//a.com`, `a.com` all give 422.
19. `http://good.com@evil.com`, `http://user:pw@a.com` and `http://@a.com` give 422 (userinfo).
20. `http://`, `http:///path`, `http://:80/`, `https://?x=1` give 422 (no host).
21. A URL containing a tab, newline, carriage return, NUL, DEL, a space, or a Unicode whitespace character (e.g. U+00A0, U+2028) inside gives 422. Python's `urlsplit` silently strips tab/CR/LF, so the check runs on the raw string before parsing.
22. `http://a.com:99999/` and `http://a.com:abc/` give 422 (invalid port), never 500.
23. Body `{}`, `{"url":null}`, `{"url":123}`, a non-JSON body, or a JSON array give 422 with the standard error format.
24. A link whose generated code would be `healthz` (or any route name) must not shadow `GET /healthz`: the generator never emits `healthz`.
25. A URL such as `http://a.com/<script>` is shown in the UI as text and is never inserted as HTML.
26. A redirect `Location` value is always the stored normalized URL, never user-supplied header text (no CR/LF possible, see 21).

### Invariants
27. At most one row per normalized URL, and one row per code, at all times, under concurrent creates.
28. N parallel `POST` of the same URL yield exactly one 201, N-1 responses with 200, one code, one row.
29. Every stored `url` has scheme `http`/`https`, a non-empty host, no userinfo, and is in normalized form.
30. After an api restart (new process, same DB file), every earlier code still redirects.
31. A code collision on insert is retried with a new code, and the client still gets a 201 with a valid code.
32. Redirect responses always carry `Cache-Control: no-store`, whether 302 or 404.

## Performance SLA
- Agreed load: ~5 requests per second, up to 10,000 stored links.
- Targets (single uvicorn worker, local disk): `POST /api/links` p95 < 100 ms; `GET /{code}` p95 < 30 ms; `GET /healthz` p95 < 20 ms.
- Perf test input: DB pre-seeded with 10,000 links; then 200 sequential creates of new URLs, 200 duplicate creates, and 1,000 sequential redirects through `TestClient`/httpx. Time budget: the whole test finishes in under 15 seconds (a correct solution needs roughly 2-4 s), and the 20-thread concurrent-create test finishes in under 5 seconds.

## API Contract
Error format for every error: `{"detail": "<human-readable message>"}` (string, never a list). FastAPI's default validation error shape is replaced by a handler that returns this format with status 422.

### `POST /api/links`
- Request: `Content-Type: application/json`, `{"url": "<string>"}`.
- 201: `{"code": "aB3dE9x", "short_url": "<base>/aB3dE9x"}` for a new link.
- 200: same body when the normalized URL already exists.
- 422: invalid input (missing/non-string `url`, empty, > 2048, scheme, host, userinfo, control chars/whitespace, bad port, malformed body). `detail` carries a specific message (e.g. "URL must start with http:// or https://").
- 500: `{"detail": "Internal error"}` for anything unexpected (e.g. code retries exhausted); no stack trace in the body.
- `<base>` is `BASE_URL` (trailing slash stripped) if set, otherwise the request origin (`scheme://host` from the request, which respects the `Host` header the proxy forwards).

### `GET /{code}`
- Route accepts only `[0-9A-Za-z]{7}`; anything else is 404.
- 302: `Location: <stored normalized url>`, `Cache-Control: no-store`, empty body.
- 404: `{"detail": "Not found"}` with `Cache-Control: no-store`.

### `GET /healthz`
- 200 `{"status": "ok"}`. Runs `SELECT 1` on the DB; 503 `{"detail": "database unavailable"}` if that fails. Registered before `/{code}`.

### Web service
- `GET /healthz` on nginx returns 200 `ok` (Docker healthcheck).
- Proxy rules (nginx in Docker, Vite `server.proxy` in dev), forwarding the original `Host`: `/api/*` to api; `^/[0-9A-Za-z]{7}$` to api; everything else serves the SPA.

## Data Model
SQLite file, path from env `DB_PATH` (default `api/data/links.db`; `/data/links.db` in Docker on the volume).

```sql
CREATE TABLE IF NOT EXISTS links (
  code       TEXT PRIMARY KEY CHECK (length(code) = 7),
  url        TEXT NOT NULL UNIQUE CHECK (length(url) > 0),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
```
- `code` primary key gives the lookup index for redirects; `url` UNIQUE gives the duplicate index. No other indexes.
- Connection settings per connection: `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA synchronous=NORMAL`. One connection per request (or per thread); no shared connection across threads.
- Create flow (no check-then-act): `INSERT INTO links(code,url) VALUES(?,?) ON CONFLICT(url) DO NOTHING`. If `rowcount == 1`: 201 with the new code. Else `SELECT code FROM links WHERE url=?` and return 200. A `sqlite3.IntegrityError` (the code PK collided, since the url conflict is absorbed by the upsert) triggers a retry with a new code, up to 5 attempts, then 500.
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
| Redirect never cached | Middleware/response headers `Cache-Control: no-store` on 302 and 404 |
| Redirect target is the stored value | Handler reads `url` from DB only; no request data in `Location` |

## Security
- Trust boundary: the browser and any HTTP client are untrusted. All validation runs in the api; UI checks are convenience only.
- Validation order in `normalize_url(raw)`: (1) type is str; (2) trim; (3) non-empty and length <= 2048; (4) reject any character that is a control character (`ord < 32` or `== 127`) or `str.isspace()`, checked on the raw trimmed string before parsing; (5) `urlsplit` (catch `ValueError`); (6) `scheme.lower()` in `{http, https}`, and the string must carry `://` after the scheme (so `javascript:` and `a.com` fail); (7) `hostname` non-empty; (8) no `@` in `netloc` (userinfo); (9) `.port` access validated (0-65535, catches `ValueError`); (10) rebuild with lowercase scheme and host, default port dropped, empty path `/`.
- Abuse cases:
  - `javascript:`/`data:` XSS via redirect or UI: scheme allowlist, case-insensitive; UI renders text only (React escaping, no `dangerouslySetInnerHTML`, short URL shown as text and not as an `href` built from user input).
  - Phishing `good.com@evil.com`: userinfo rejected.
  - Header injection via CR/LF in the URL: rejected before parsing; Starlette also rejects them.
  - Oversized input: 2048 limit on the string, and a request-body cap of 8 KB at the app level (reject larger body with 413 or 422).
  - SQL injection: parameterized queries only; no string formatting into SQL.
  - Code enumeration: random 7-char base62 (62^7 ~ 3.5e12).
  - Open redirect to an attacker site: accepted by design (out of scope); documented in the README.
  - Rate limiting and blocklists: not implemented (agreed).
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
- FM-10: Restart: data written, process/app recreated on the same DB file. Expected: all codes still resolve; startup is idempotent on an existing DB.
- FM-11: Malformed requests: missing `url`, wrong type, invalid JSON, array body, oversized body, wrong content type. Expected: 422 (or 413 for oversized) in the `{"detail": string}` format, never 500.
- FM-12: Invalid port (`:99999`, `:abc`, `:-1`). Expected: 422, not an unhandled `ValueError`.
- FM-13: Route shadowing: generated code equal to `healthz`. Expected: never generated; `/healthz` stays 200.
- FM-14: Database unavailable (file not writable, locked longer than the timeout). Expected: `/healthz` returns 503; POST returns 500 with the generic message; no stack trace or path leaks.
- FM-15: UI error paths: api returns 422, 500, or the network fails; clipboard API missing or rejected. Expected: an error message is shown, the UI stays usable, and no stale short URL remains from the previous success.
- FM-16: Short URL base: behind the proxy the `Host` header must be forwarded, otherwise `short_url` would point at the internal api host. Expected: `BASE_URL` wins when set; otherwise the request origin.
- FM-17: XSS via displayed data: a URL with `<script>` or HTML in query/path is rendered as plain text.

## Scaling
At demo scale one uvicorn worker and one SQLite file are enough. Writes are serialized by SQLite, so the first limit is write throughput (hundreds of inserts per second in WAL mode), far above the target of a few requests per second. Redirect reads are single primary-key lookups. Beyond demo scale: add an in-process or Redis cache for code-to-URL (safe, since links are immutable), then move to Postgres for multiple api replicas (SQLite on a shared volume does not support multiple writer hosts). Rate limiting at the proxy is the next control if abused.

## Deployment
Local:
- api: `cd api && uv sync && uv run uvicorn app.main:app --port 8000`
- web: `cd web && npm install && npm run dev` (Vite on 5173, proxies `/api` and `^/[0-9A-Za-z]{7}$` to `http://localhost:8000`, with `Host` preserved).
- Env: `DB_PATH` (default `api/data/links.db`), `BASE_URL` (optional).

Docker:
- `api/Dockerfile`: python:3.12-slim, uv install, non-root user, `EXPOSE 8000`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `web/Dockerfile`: multi-stage, `node:22` build then `nginx:alpine` with `nginx.conf` (proxy rules above, `proxy_set_header Host $http_host`, `/healthz` returns 200).
- `docker-compose.yml`: `api` (env `DB_PATH=/data/links.db`, volume `linkdata:/data`, healthcheck calling `/healthz` with Python urllib, not curl, since slim images lack curl) and `web` (port `8080:80`, `depends_on: api: condition: service_healthy`, healthcheck `wget -qO- http://localhost/healthz`). Users open `http://localhost:8080`.
- No Kubernetes manifests (DEPLOY is docker).

Service layout conventions:
- Python service (`api/`): uv project, `pyproject.toml` with dev deps ruff, mypy, pytest, httpx; code in `app/` (`main.py` exposes `app`, plus `urls.py` for `normalize_url`, `db.py` for storage); tests in `tests/`. Commands: `uv run pytest`, `uv run ruff check .`, `uv run mypy app`.
- React service (`web/`): Vite + TypeScript, `package.json` scripts `typecheck` (`tsc --noEmit`), `test` (`vitest run`), `build` (`vite build`); tests next to code as `*.test.tsx` (Vitest + Testing Library, jsdom).
