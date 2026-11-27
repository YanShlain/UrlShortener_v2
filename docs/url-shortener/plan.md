# Plan

## Deliverable and layout
Workspace root:
- `api/`: FastAPI service (Python 3.12, uv).
- `web/`: React + TypeScript (Vite) single page: URL form, shows the short link with a copy button.
- `docker-compose.yml`: api + web, SQLite file on a named volume.

## Architecture
- Web calls `POST /api/links {url}` and gets `{code, short_url}`. Opening `GET /{code}` gives a 302 (404 if unknown), with `Cache-Control: no-store`.
- Validation and normalization in one function using `urllib.parse`: trim; reject empty, over 2048 chars, control characters or whitespace inside, scheme (case-insensitive) not http/https, missing host, and `user:password@`. Then lowercase scheme and host, drop `:80`/`:443` default ports, empty path becomes `/`. The normalized form is what is stored and redirected to.
- Not normalized: http vs https, trailing slash on non-empty paths, query order, path case.
- SQLite table `links(code PRIMARY KEY, url UNIQUE, created_at)`, WAL mode and busy timeout. SQLite: durable, no extra process, unique constraints make concurrent writes safe.
- Codes: random 7-char base62; retry on code collision. Duplicate (normalized) URL returns the existing row (200), a new one gets 201.
- Open redirect: scheme allowlist plus the rules above; no domain blocking or preview page.

## Build order and tests
1. API: validation/normalization, create, redirect, storage. 2. Web UI. 3. Docker compose and run docs.
Risk tests: mixed-case and leading-space `javascript:` rejected, `user:password@host` rejected, missing host/control characters rejected, `http://a.com` and `http://a.com/` same code, `http` and `https` different codes, default-port and host-case normalization, duplicate URL returns same code, concurrent creates of the same URL give one row, code collision retry, unknown code 404, redirect is 302 with no-store, data survives restart. UI (Vitest): form success, error, and copy states.

## How it runs
Local: `uv run uvicorn` in `api/`, `npm run dev` in `web/` (proxies to the API). Docker: `docker compose up`.

## Out of scope
Auth, custom aliases, expiry, click counters, link history, rate limiting, deletion, phishing-domain blocking, preview page, normalization beyond the agreed list (http to https upgrade, trailing slash, query order, path case, fragments, IDN).
