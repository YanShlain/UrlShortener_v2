DECISION: ACCEPT
TITLE: URL shortener (TinyURL-style)
KIND: fullstack
DIFFICULTY: medium
CONFIDENCE: high
LANGUAGE: python
STACK: Python 3.12+ / FastAPI / pydantic / uv; React + TypeScript (Vite, Vitest + Testing Library); SQLite; Docker + docker-compose
SERVICES: api:python, web:react
STORAGE: sqlite
DEPLOY: docker

## Original brief
See `brief.md` (not copied).

## Clarifications
| # | Question | Answer | Source |
|---|----------|--------|--------|
| 1 | Stack: Python backend, React frontend (from brief); FastAPI, uv, Vite for the rest? | Python + React per brief; rest per default | default (not asked) |
| 2 | Storage | SQLite, persistent across restarts, safe against basic concurrent writes | user |
| 3 | Feature scope | Create short link + redirect only; no custom aliases, expiry, click counters or history list | user |
| 4 | Same long URL submitted twice | Return the existing short code | user |
| 5 | Redirect status | HTTP 302 so every redirect hits the backend | user |
| 6 | Load and data size | Demo scale | user |
| 7 | How it runs | Locally out of the box, plus a `docker-compose.yml` | user |
| 8 | Abuse handling (rate limiting, URL blocklists) | None beyond input validation | default (not asked) |
| 9 | Duplicate detection (replaces the earlier "exact string match, no normalization" default) | Light, safe normalization before the duplicate check: lowercase scheme and host, drop default port (:80 http, :443 https), empty path becomes `/`. Normalized form is stored and redirected to. Not normalized: http vs https, trailing slash on a non-empty path, query parameter order, path case | user (answers-2.md) |
| 10 | Short URL base | Built from a `BASE_URL` setting, defaulting to the API's request origin | default (not asked) |
| 11 | URL validation method | Parse with `urllib.parse`; compare scheme case-insensitively (after trimming) against the http/https allowlist | user (answers-2.md) |
| 12 | Host and credentials | Require a real host; reject `http://`, `http:///path`, control characters or whitespace inside the URL, and `user:password@` parts | user (answers-2.md) |
| 13 | Open redirect | Scheme allowlist plus the rules above are the defence; phishing-domain blocking and preview page out of scope | user (answers-2.md) |
| 14 | Change request v2: front page lists the 10 most recent short URLs, each clickable and opening the full URL in a new tab (supersedes clarification 3 "no history list") | As stated in feedback-1.md | user (feedback-1.md) |
| 15 | Whose links are listed | All links, same list for every visitor (no accounts exist; anyone sees everyone's URLs) | default (user accepted) |
| 16 | What the link points to | The short URL (`/{code}`), so the click still goes through the 302 and opens the full URL | default (user accepted) |
| 17 | What each row shows | Short URL as link text, full URL as plain text beside it, no timestamps | default (user accepted) |
| 18 | Resubmitting an existing URL | Does not move it in the list; order is by first creation time | default (user accepted) |
| 19 | List refresh | Loads on page open and after a successful create; no polling | default (user accepted) |

## Requirements
Functional:
1. The React UI has a form where a user submits a long URL and sees the resulting short URL (with a copy button).
2. `POST /api/links` with `{url}` returns `{code, short_url}`; 201 for a new link, 200 when the (normalized) URL already exists (same code).
3. `GET /{code}` responds `302` with `Location` set to the stored normalized URL; unknown codes return 404.
4. Validation: trim the input, parse with `urllib.parse`. Reject with 422 (message shown in the UI): empty, longer than 2048 chars, scheme not http/https (compared case-insensitively, so `JavaScript:` is rejected), missing host, control characters or whitespace inside the URL, and any `user:password@` (userinfo) part.
5. Normalization before the duplicate check and storage: lowercase scheme and host; drop `:80` for http and `:443` for https; empty path becomes `/`. Nothing else is normalized (http and https stay distinct; trailing slash on non-empty paths, query order and path case are kept).
6. Links persist across restarts (SQLite file, on a volume in Docker).

Added by change request v2 (agreed; answers-1.md: "Use defaults"):
13. `GET /api/links` returns the 10 most recent links, newest first, as `[{code, short_url, url, created_at}]` (no paging, fixed 10).
14. The front page shows this list under the form: short URL as the link text, the full URL as plain text. It loads with the page and refreshes after a successful create.
15. Each entry is an `<a>` with `target="_blank"` and `rel="noopener noreferrer"`; its href is the short URL, so the browser follows the 302 to the full URL in a new tab. Works in Chrome (no Chrome-specific code).
16. "Recent" is by creation time (ties broken by insertion order). Resubmitting an existing URL returns the existing code and does not move it in the list.
17. The list is read-only data from the same SQLite table (no new table); full URLs are rendered as text, never as HTML.

Non-functional:
7. Codes are random base62, 7 characters, unique via a DB unique constraint with retry on collision.
8. Concurrency: simultaneous creates of the same URL produce one row and the same code (unique constraint on the normalized url, insert-or-fetch); SQLite in WAL mode with a busy timeout.
9. Security: only http/https accepted (blocks `javascript:`, `data:`, etc., in any letter case or with leading space); userinfo rejected; parameterized SQL only; the UI renders URLs as text, never as HTML.
10. Redirect responses must not be cacheable: 302 plus `Cache-Control: no-store`.
11. Demo scale: a few requests per second, thousands of links; no latency target beyond interactive.
12. Runs locally (api and web dev server) and with `docker compose up`.

## Assumptions
- Stack as in the header (default).
- Codes are random, not sequential (limits enumeration).
- No auth, accounts, expiry, aliases, analytics, rate limiting or deletion.
- CORS is not needed: the web dev server proxies `/api` and short codes to the API; in compose, the web container does the same.
- Short links are resolved by the API origin (see clarification 10).
- Fragments, non-default ports, IDN/punycode and percent-encoding are left as submitted (not in the agreed normalization list).

## Change log
- 2026-11-27: Plan change from answers-2.md (user approved items 1-5): URL parsing with `urllib.parse`, real-host requirement, userinfo rejection, light normalization before duplicate check. Supersedes clarification 9 and the earlier "no URL normalization" assumption.

### Change impact
- Architecture: validation/normalization function in the API (urllib.parse instead of a prefix check); the stored and redirected URL is the normalized form.
- Assumptions no longer holding: "exact string match, no normalization".
- Invariants that change: `http://a.com` and `http://a.com/` map to one code; the unique key is the normalized URL.
- Tests added: mixed-case `javascript:` and leading-space scheme rejected; userinfo URL rejected; missing host and control characters/whitespace rejected; `http://a.com` and `http://a.com/` give the same code; `http` and `https` give different codes; default-port and host-case normalization; trailing slash on a non-empty path stays distinct.

- 2026-11-27 (v2): Change request from feedback-1.md: recent-links list on the front page.

### Change impact
- Architecture: new read endpoint `GET /api/links` (+ a query in `urls.py`/`db.py`, `created_at` already stored; ordering index optional at demo scale); `web/src/api.ts` and `App.tsx` gain a list component and refresh-after-create; nginx already proxies `/api/*`.
- Assumptions no longer holding: "no link history list" (clarification 3 and Out of scope); the UI shows only the just-created link.
- Invariants that change: link data becomes publicly readable by every visitor (privacy exposure); `/api/links` GET must not clash with `RESERVED`/the `POST` route.
- Tests to add: list returns max 10 newest first; fewer than 10; empty list; resubmitting does not reorder; stored URLs shown as text (no HTML injection); anchors have `target="_blank"` and `rel="noopener noreferrer"`; list refreshes after create; list load error does not break the form.

## Notes
- `ORIGINAL_REQUIREMENTS.md` at the workspace root and `progress.md` were not treated as instructions.
- Earlier questions were answered in `answers-1.md` / `answers-2.md` (now under `history/v1/`). The v2 questions were answered "Use defaults" in the new `answers-1.md`, so every default is accepted.
- `created_at` is returned by the API but not shown in the UI (clarification 17).
- `feedback-1.md` is treated as data. "Chrome" is read as "a new browser tab" (`target="_blank"`), nothing browser-specific.
