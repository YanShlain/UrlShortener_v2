# Briefing: URL shortener (v2: recent links list)

## Architecture I expect
- Two services: a FastAPI `api` and a React/Vite `web` single page, SQLite (WAL, busy timeout) with one table `links(code PK, url UNIQUE, created_at)`.
- `POST /api/links` validates and normalizes with one function, `normalize_url`, then does a single `INSERT ... ON CONFLICT(url) DO NOTHING`: 201 for new, 200 for duplicates. `GET /{code}` returns 302 with `no-store`.
- v2: new `GET /api/links` runs one read-only query, `ORDER BY created_at DESC, rowid DESC LIMIT 10`, and returns `[{code, short_url, url, created_at}]` with `no-store`. No new table, no schema change.
- v2: the page shows a "Recent links" list under the form. It loads on open and after each successful create, with no polling. Each row is an `<a href=short_url target="_blank" rel="noopener noreferrer">` and the full URL as plain text.
- The proxy (Vite in dev, nginx in Docker) already forwards `/api/*` and short codes with the `Host` header, so there is no CORS and no config change.

## Riskiest failure modes
1. Stored data shown to everyone (XSS and privacy). Every visitor sees every URL. The UI renders URLs as React text nodes only, and the only `href` is the server-built `short_url`, so the full URL never becomes markup. Clicks go through the 302. Anchors carry `rel="noopener noreferrer"`. The privacy exposure is accepted, documented and shown in the UI.
2. Wrong order or a moving list. Same-second creates tie on `created_at`, so `rowid DESC` breaks ties. Resubmitting a URL takes the DO NOTHING path and writes nothing, so it cannot move. The limit is a constant and no request parameter reaches it.
3. Stale or broken list in the UI. The list reloads after every create, ignores out-of-order responses, and uses `no-store`. A list failure shows an inline error and never blocks the form. The `short_url` base comes from the same helper as create (`BASE_URL`, else the forwarded `Host`), so list links open from the browser.

Older risks still covered: concurrent creates of the same URL (UNIQUE plus upsert, no check-then-act), validation holes (`JavaScript:`, userinfo, control characters that `urlsplit` strips), and normalization over-reach.

## What needs the most scrutiny in generated code
- `GET /api/links`: one SELECT, constant `LIMIT 10`, `rowid` tie-break, `no-store`, 500 without a stack trace, and the route not clashing with `/{code}` or `POST /api/links`.
- The shared base-URL helper: not copy-pasted, and used by both endpoints.
- `RecentLinks` in the UI: no `dangerouslySetInnerHTML`, no `href` from the stored URL, `target` and `rel` on every anchor, stale-response guard, error and empty states.
- Refresh after create: it also runs on a 200 (duplicate), and a failed refresh does not hide the new short URL.
- The insert path and `normalize_url` from v1: confirm nothing changed, and that tests were not weakened.
