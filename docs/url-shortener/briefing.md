# Briefing: URL shortener

## Architecture I expect
- Two services: a FastAPI `api` and a React/Vite `web` single page.
- The web form posts `{url}` to `POST /api/links` and shows `short_url` as text with a Copy button.
- One function, `normalize_url`, validates and normalizes using `urllib.parse`. It is the only way a URL reaches the DB.
- SQLite (WAL, busy timeout) holds `links(code PK, url UNIQUE, created_at)`.
- Create is a single `INSERT ... ON CONFLICT(url) DO NOTHING`, then a fetch if no row was inserted. This gives 201 for new links and 200 for duplicates.
- `GET /{code}` accepts only 7 base62 characters and returns 302 with `Cache-Control: no-store`. Unknown codes return 404.
- The web proxy (Vite in dev, nginx in Docker) forwards `/api` and short codes to the api, so no CORS is needed. Compose has a volume for the DB and healthchecks.

## Riskiest failure modes
1. Concurrent creates of the same URL. The UNIQUE constraint and the single-statement upsert make this safe, with no check-then-act. A code collision (PK) raises `IntegrityError` and retries with a new code.
2. Scheme and URL validation holes, such as `JavaScript:`, ` javascript:`, `good.com@evil.com`, `http:///x`, and tabs or newlines that `urlsplit` silently strips. The design checks characters on the raw string first, then parses, then applies the allowlist, host and userinfo rules. Everything is validated server-side.
3. Normalization over- or under-reach. `http://a.com` and `http://a.com/` must match, while http vs https, trailing slash on a non-empty path, query order and path case must not. The fix is a short, explicit rebuild of the URL, with a test for each case.

Other traps: a generated code equal to `healthz`, 301 or cached redirects, a wrong `short_url` base behind the proxy (the `Host` header must be forwarded), and invalid ports raising `ValueError` and giving a 500.

## What needs the most scrutiny in generated code
- `normalize_url`: order of checks, the control-character and whitespace test before `urlsplit`, port parsing, IPv6 hosts, rebuilding the URL.
- The insert path: confirm there is no SELECT-then-INSERT, that the retry only covers code collisions, and that each request uses its own connection with WAL and busy timeout set.
- Redirect handler: status 302 (not 301), `no-store` also on 404, and `Location` only from the DB.
- UI: no `dangerouslySetInnerHTML`, no `href` from user text, errors shown, stale result cleared, clipboard failure handled.
- Tests: check they are not weakened, and that the concurrency test uses real threads on a real SQLite file.
