## Solution: URL shortener (TinyURL-style) with recent-links list (v2)

**Approach:** A FastAPI service validates and normalizes the URL in one function (`solutions/url-shortener/api/app/urls.py:13`). It stores the URL in SQLite with one `INSERT ... ON CONFLICT(url) DO NOTHING` (`api/app/db.py:87`): a new row gives 201, an existing URL gives its code with 200. `GET /{code}` answers 302 with `Cache-Control: no-store`. v2 adds `GET /api/links` (`api/app/main.py:96`), one SELECT of the 10 newest rows, and a `RecentLinks` React component under the form (`web/src/RecentLinks.tsx`). Each row is an anchor to the server-built short URL with `target="_blank"`, so the click goes through the 302 and the full URL opens in a new tab. No schema change.

**Verification:** Round 1 of v2: gate PASS (`rounds/1/checks.md`), review PASS (`rounds/1/review.md`). The gate ran ruff, `mypy --strict`, 144 pytest cases (all passed), web typecheck, web test, web build and an api smoke boot. 73 Python tests were locked up front (`progress.md`); the 144 is the pytest case count with parametrization. Risk tests: FM-1 to FM-17 (v1, `test_api.py`) plus FM-18 to FM-23 (v2, `test_recent_links.py` and `RecentLinks.test.tsx`). Perf (whole-test time, from the gate): `test_perf_10k_links` 9.36 s vs 15 s budget; `test_perf_concurrent_creates_under_5s` 0.53 s vs 5 s; `test_perf_list_10k_rows` 1.90 s vs 15 s. The list test also asserts p95 < 50 ms over 200 sequential requests at 10,000 rows, and it passed. The actual p95 value is not printed, so I cannot quote it. The 1.90 s includes app startup and seeding, so 1.90 s / 200 = 9.5 ms is only an upper bound on the mean. Package: not run.

## Design decisions

**1. Code generation: random 7-char base62** (`api/app/db.py:10,49-53`)
- Chosen: `secrets.choice` over `[0-9A-Za-z]`, 7 characters, `healthz` excluded via `RESERVED` (`db.py:11`).
- Alternatives: a sequential counter in base62 (guessable, enumerable), a hash of the URL, a UUID (longer).
- Trade-off: no coordination and no enumeration; the cost is a possible collision, handled by retry.
- Breaks when: the space is 62^7 = 3.52e12. At 10,000 links one insert collides with probability about 10,000 / 3.52e12 = 2.8e-9. At 1e9 links it is about 2.8e-4 per insert, so retries become routine; five straight failures (`MAX_ATTEMPTS = 5`, `db.py:12`) are about (2.8e-4)^5 = 1.7e-18. A new top-level route name must be added to `RESERVED`.

**2. Storage and schema: SQLite, constraints do the work** (`db.py:14-20,80-99`)
- Chosen: `code` PRIMARY KEY with `CHECK(length(code)=7)`, `url` UNIQUE. Create is one statement; `rowcount == 1` means created, otherwise a SELECT fetches the existing code. No check-then-act.
- Alternatives: SELECT then INSERT (racy), a Python lock (one process only), Postgres.
- Trade-off: the database guarantees one row per URL even under parallel creates; no extra container.
- Breaks when: more than one api host is needed. SQLite on a shared volume does not support multiple writer hosts. Design estimate: hundreds of inserts per second in WAL mode against about 5 requests per second.

**3. The v2 list query: sort on `(created_at, rowid)`, no index** (`db.py:67-77`)
- Chosen: `SELECT code, url, created_at FROM links ORDER BY created_at DESC, rowid DESC LIMIT ?`. `RECENT_LIMIT = 10` is a constant (`db.py:67`); the route takes no parameters, so a client cannot ask for more.
- Why `rowid` is a valid tie-break: it grows with each insert and rows are never deleted, so it equals insertion order. `created_at` has one-second resolution, so same-second links need it.
- Why a resubmit does not reorder: the upsert writes nothing on conflict, and there is no `updated_at`.
- Alternatives: add the composite index now; an in-memory "last 10" list; order by `rowid` alone.
- Trade-off: no index means SQLite scans and sorts every row on each call. That is within the SLA at 10,000 rows (test asserts p95 < 50 ms, passed) and avoids an index that costs a write on every insert.
- Breaks when: the table grows far past the tested 10,000 rows. The cost grows with the row count, so 10x the rows is roughly 10x the sort. The design names the fix: `CREATE INDEX idx_links_created ON links(created_at, rowid)` (`design.md` Data Model). `order by rowid alone` would be wrong if clocks or imports ever put rows out of time order.

**4. Concurrency control: connection per call, WAL, busy timeout** (`db.py:31-46`)
- Chosen: a short-lived connection per call, `timeout=5`, `synchronous=NORMAL`, WAL set once in `init_db`. Handlers are sync `def`, so FastAPI runs them in its thread pool and no connection is shared across threads.
- Alternatives: one shared connection (not thread-safe), a connection pool.
- Trade-off: simple and safe; the cost is one connect per request. The list read is a pure SELECT, so in WAL mode it does not block writers.
- Breaks when: a writer holds the lock longer than 5 s. POST then returns 500 (`main.py:87-89`); `/healthz` returns 503 only if its own `SELECT 1` fails.

**5. Status codes and caching** (`main.py:15-16,90-93,107,117`)
- Chosen: 302 (not 301) with `no-store` on redirects and 404s; `no-store` also on the list so the refresh after a create is never served from a cache. A DB error gives a generic 500 `{"detail":"Internal error"}` with no stack trace (`main.py:100-102`).
- Alternatives: 301 (browsers cache it, so later requests skip the api), `max-age` on the list.
- Trade-off: every click hits the api and every list read hits SQLite; correctness over saving a few ms at demo scale.
- Breaks when: traffic grows far past the demo. `no-store` blocks browser and proxy caching, so the fix has to be an in-process or Redis cache on the server.

**6. Short URL base: one helper for both endpoints** (`main.py:35-39`)
- Chosen: `BASE_URL` if set, else `scheme://Host` from the request. POST and GET /api/links both call it, so list links never point at the internal host.
- Behind nginx this only works because `proxy_set_header Host $http_host` forwards the original host (`web/nginx.conf:12`).
- Alternatives: hard-coded base; trust `X-Forwarded-Host`.
- Breaks when: a proxy forgets to forward `Host`; then `short_url` becomes `http://api:8000/<code>` and does not open from a browser (FM-16).

**7. Validation: hand-written `normalize_url`, manual JSON parse** (`urls.py:13-44`, `main.py:66-84`)
- Chosen: one function is the only path to the INSERT. Order: type, trim, length <= 2048, control-char/whitespace check on the raw string, `urlsplit`, scheme allowlist plus literal `://`, host present, no `@`, port check, rebuild. The raw check must come before `urlsplit`, which silently strips tab, CR and LF (`urls.py:21-23`).
- Alternatives: pydantic `HttpUrl`, a regex. FastAPI's default 422 is a list; the spec needs `{"detail": string}`.
- Trade-off: full control of messages and error format, at the cost of more code.
- Breaks when: more URL rules arrive (IDN, percent-encoding, fragments). They are left as submitted, so two spellings of one page get two codes.

**8. Frontend: how the list is loaded and rendered** (`web/src/App.tsx:18-33`, `RecentLinks.tsx:8-30`, `api.ts:71-82`)
- Chosen: three-state list (`loading`/`ok`/`error`), loaded on mount and after every successful create. A `latest` ref counter (`App.tsx:19,22,25`) lets only the newest request set state. The `href` is the server's `short_url`; the full URL is a text node.
- Alternatives: polling (out of scope), optimistic insert, a data library such as React Query.
- Trade-off: one extra GET per page load and per create; no new dependency.
- Breaks when: you need live updates (a link made in another tab appears only after reload or the next create) or you want to show timestamps.

## What fails first at scale

Agreed load (requirements.md/design.md): about 5 requests per second, up to 10,000 links. At this load nothing is near saturation: the gate's 200-request list test and 20-thread create test pass with room. The order below is by how each part degrades as load or data grows.

1. **The list query (`db.py:74`).** It scans and sorts all rows for each `GET /api/links`, and every page load and every create triggers one. The cost grows linearly with table size, so it is the first read to slow down. The tested point is 10,000 rows, p95 < 50 ms. Fix: the index on `(created_at, rowid)` so SQLite reads 10 index entries; then a 1-2 s in-process cache invalidated on create; then Redis.
2. **SQLite write serialization plus connect-per-call (`db.py:33`).** One writer at a time; the design estimates hundreds of inserts per second, and the 20-thread test finished in 0.53 s. Every request also opens a connection, and sync handlers share the thread pool of one uvicorn worker. Past a few hundred writes per second POSTs queue on the 5 s busy timeout and start returning 500. Fix: batch or async writes, a pooled connection, then Postgres.
3. **Single api host and single SQLite file.** You cannot add replicas behind a load balancer, because SQLite on a shared volume does not support multiple writer hosts. There is also no rate limiting, so one client can use all capacity (the list is public and parameter-free, so it is cheap to scrape). Fix: Postgres with several api replicas, rate limiting at nginx, a read cache for code-to-URL (safe, because links are immutable).

## Frontend review

- **Loading, errors, feedback.** The form shows "Shortening..." and disables the button (`App.tsx:80-82`), and the server's `detail` message in a `role="alert"` paragraph (`App.tsx:84-88`). The list has its own loading, empty ("No links yet.") and error ("Could not load recent links.") text (`RecentLinks.tsx:13-15`). A list failure never touches the form status (`App.tsx:26-28`). A privacy line sits above the list (`RecentLinks.tsx:12`). Reloads keep the old list on screen (no flip back to "Loading...") because `loadList` does not reset state.
- **Over-complicated or wrong.**
  - The Copy button label comes from a CSS `data-label` (`App.tsx:92-100`, `styles.css:6`) so the error text is the only node matching "copy" in tests. This is a test-driven hack, and the visible label is not in the DOM.
  - A failed refresh replaces a good list with the error text (`App.tsx:27`). The reviewer called this acceptable under FM-19, but a user loses 10 links because of one blip.
  - `validateUrl` in `api.ts:9-14` duplicates the server's trim and length rules; the server stays the authority.
  - The 2048-char layout case (Trap 38) is tested only as "text stays in the DOM" (jsdom has no layout), so I cannot confirm from the tests that CSS wraps it.
- **What I would simplify.** Use a real text label on the Copy button and fix the test query instead. On refresh failure, keep the previous items and show a small error beside them.

## Risks covered by tests

| FM | Failure mode | Test name | Enforced in code |
|---|---|---|---|
| FM-1 | Concurrent creates of one URL | `test_risk_fm1_concurrent_same_url` | `db.py:87-90` (UNIQUE + DO NOTHING) |
| FM-2 | Code collision, retries exhausted | `test_risk_fm2_collision_retry_then_exhausted` | `db.py:83-93,99`; `main.py:87-89` |
| FM-3 | `javascript:`/`data:`/`file:`/`ftp:`/`//host` | `test_risk_fm3_dangerous_schemes` | `urls.py:26-28` |
| FM-4 | Userinfo `user:pw@host` | `test_risk_fm4_userinfo` | `urls.py:31-32` |
| FM-5 | Missing host | `test_risk_fm5_missing_host` | `urls.py:29-30` |
| FM-6 | Control chars/whitespace | `test_risk_fm6_control_chars` | `urls.py:22-23` |
| FM-7 | Normalization and duplicates | `test_risk_fm7_normalization_duplicates` | `urls.py:38-44` |
| FM-8 | Unknown or malformed code | `test_risk_fm8_unknown_code` | `main.py:44-46,111-116` |
| FM-9 | 302 not 301, `no-store` | `test_risk_fm9_redirect_is_302_not_301` | `main.py:117` |
| FM-10 | Restart on the same DB file | `test_risk_fm10_restart_idempotent` | `db.py:41-46` (`IF NOT EXISTS`) |
| FM-11 | Malformed requests, 413 | `test_risk_fm11_malformed_requests` | `main.py:66-80` |
| FM-12 | Invalid port | `test_risk_fm12_invalid_port` | `urls.py:33,36-37` |
| FM-13 | Route shadowing (`healthz`, `/api/links`) | `test_risk_fm13_healthz_never_shadowed`; `test_edge_35_route_not_shadowed_and_methods` | `db.py:11,52`; `main.py:55,96,110` |
| FM-14 | Database unavailable | `test_risk_fm14_database_unavailable` | `main.py:57-60,87-89,100-102` |
| FM-15 | UI error paths | `test_risk_fm15_api_errors_are_displayable`; `App.test.tsx` | `main.py:42-52`; `App.tsx:51-56,64-66` |
| FM-16 | Short URL base behind proxy | `test_risk_fm16_base_url_precedence`; `test_edge_short_url_uses_forwarded_host` | `main.py:35-39`; `nginx.conf:12` |
| FM-17 | HTML in a URL stays data | `test_risk_fm17_html_in_url_is_data_only`; UI "renders hostile URLs as inert text..." | `RecentLinks.tsx:23`; `App.tsx:91` |
| FM-18 | List order, tie-breaks, resubmit | `test_risk_fm18_ordering_and_tiebreaks` | `db.py:74`; `db.py:87-88` |
| FM-19 | List load failure isolated | `test_risk_fm19_list_failure_is_isolated`; UI "shows an inline list error on 500..." | `main.py:100-102`; `App.tsx:26-28` |
| FM-20 | Stale list after create, races | `test_risk_fm20_fresh_after_create_no_store`; UI "ignores a stale list response..." | `main.py:107`; `App.tsx:19-25,50` |
| FM-21 | New tab, no `window.opener` | UI "every anchor has target=_blank and rel=noopener noreferrer" | `RecentLinks.tsx:20` |
| FM-22 | Privacy exposure documented | `test_risk_fm22_privacy_notice_in_readme`; UI "shows the privacy notice near the list" | `RecentLinks.tsx:12`; `solutions/url-shortener/README.md:21` |
| FM-23 | Hostile stored data in the list | `test_risk_fm23_hostile_stored_data_is_inert_json`; UI hostile and 2048-char tests | `main.py:104-106`; `RecentLinks.tsx:20-23` |

## How to present it

- **Questions that mattered.** Who sees the list (everyone, no accounts)? What does the link point at (the short URL, so it still goes through the 302)? Does a resubmit move a link in the list (no)? Does the list poll (no, only on load and after create)? "Chrome" means a new tab. All were defaults the PM accepted ("Use defaults", `answers-1.md`).
- **Approach and key insight.** Constraints in the database, not in application code: UNIQUE on `url` and a one-statement upsert give duplicate safety under concurrency. Likewise the order of the list comes from immutable `created_at` and `rowid`, so a resubmit, which writes nothing, cannot reorder it. The list `href` is always the server's `short_url`, so stored data never reaches an `href`.
- **Walk-through.** Open the page: `GET /api/links` returns `[]` and the UI shows "No links yet." Submit `HTTP://Example.COM:80/Docs`: it is normalized to `http://example.com/Docs`, stored with code `aB3dE9x`, and 201 is returned. The UI shows the short URL and reloads the list, so the row appears on top. Click it: a new tab opens `/aB3dE9x`, nginx proxies it to the api, which answers 302 to `http://example.com/Docs`. Submit the same URL again: 200, same code, list unchanged.
- **Edge cases to call out.** Same-second creates (rowid tie-break); more than 10 links; `javascript:` in any case; `user@host` credentials; list failure while the form still works; 2048-char URL; `<script>` in a URL; the privacy exposure (secrets in query strings are visible to every visitor).

## Likely follow-up questions

1. **Why no index on `created_at`?** At 10,000 rows the full sort is within the 50 ms budget (the test passed), and an index adds a write cost for each insert. It becomes the first fix when the table grows: `(created_at, rowid)` makes the query read 10 entries.
2. **Why `rowid DESC` as the tie-break, and does it hold?** `created_at` has 1-second resolution. `rowid` increases with each insert and rows are never deleted, so it is insertion order. If deletion were added, a reused `rowid` could break it, and an AUTOINCREMENT column would be needed.
3. **Could the list link be an XSS or phishing vector?** The `href` is the server-built `<base>/<code>`, never the stored URL. The full URL is a React text node. Only http/https URLs are stored, so the 302 lands on one of those. Open redirect to a bad site is accepted and out of scope. Anchors carry `rel="noopener noreferrer"` against tabnabbing.
4. **Why `no-store` on the list, and what does it cost?** Without it the refresh after a create could be served from a cache and miss the new link. The cost is that every load hits SQLite. A server-side cache (1-2 s, invalidated on create) is the fix at larger scale.
5. **What happens when two list loads overlap?** The `latest` ref counter (`App.tsx:19-25`) drops any response that is not from the newest request, so a slow mount response cannot overwrite the post-create list.
6. **Everyone sees everyone's URLs. Is that acceptable?** It was a conscious default, accepted by the PM. URLs with tokens in query strings are exposed. It is documented in the README and in the UI (`RecentLinks.tsx:12`). A real product needs per-user lists (auth) or stripping query strings.
