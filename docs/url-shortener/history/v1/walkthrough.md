## Solution: URL shortener (TinyURL-style)

**Approach:** A FastAPI service validates and normalizes the URL in one function (`api/app/urls.py:13`), then inserts it into SQLite with a single `INSERT ... ON CONFLICT(url) DO NOTHING` (`api/app/db.py:74`). A new row returns 201. A row that already exists returns its code with 200. Codes are random 7-char base62 values, and `GET /{code}` answers with a 302 and `Cache-Control: no-store`. A small React page posts the URL and shows the short link as text with a Copy button. The two services run locally or under `docker compose`, and the SQLite file sits on a named volume.

**Verification:** Round 2 gate PASS (`rounds/2/checks.md`): ruff, `mypy --strict`, 122 pytest cases passed, web typecheck, web test, web build and api smoke boot all passed. The 122 pytest cases cover the example, edge and risk tests, which include FM-1 to FM-17 and 2 perf tests. 51 Python tests were locked up front (`progress.md`). The slowest was `test_perf_10k_links` at 11.84 s against the 15 s budget. `test_perf_concurrent_creates_under_5s` took 0.32 s against 5 s. The per-endpoint p95 targets (100/30/20 ms) are not measured separately. Only the whole-test time is. That time includes seeding 10,000 rows, so I cannot derive per-request latency from it. Rounds: 2. Round 1 got CHANGES and round 2 got PASS (`rounds/2/review.md`). Package: not run.

## Design decisions

**1. Code generation: random 7-char base62** (`api/app/db.py:10,49-53`).
- Chosen: `secrets.choice` over `[0-9A-Za-z]`, 7 characters, with `healthz` excluded (`RESERVED`, `db.py:11`).
- Alternatives: a sequential counter encoded in base62, a hash of the URL, or a UUID.
- Trade-off: random codes are not guessable or enumerable, and need no coordination. The cost is a possible collision, which is handled by retry.
- Breaks when: the space is 62^7 = 3.52e12. At 10,000 links one insert collides with probability about 10,000 / 3.52e12 = 2.8e-9. Five collisions in a row (`MAX_ATTEMPTS = 5`, `db.py:12`) end in a 500. The odds only become real near millions of links. At 1e6 links the per-insert probability is about 2.8e-7. At 1e9 links it is about 2.8e-4, so retries become routine, but 5 straight failures are still about 1.7e-18.
- Reserved route names are one hard-coded entry. Adding a new top-level route means adding it to `RESERVED`.

**2. Storage: SQLite with a unique constraint, not a check-then-insert** (`api/app/db.py:14-20,74-85`).
- Chosen: `code` PRIMARY KEY, `url` UNIQUE, `CHECK(length(code)=7)`. The create is one statement. `rowcount == 1` means created. `rowcount == 0` means the URL already existed, so a SELECT fetches the code.
- Alternatives: SELECT first and then INSERT (racy), a Python lock (only works inside one process), or Postgres.
- Trade-off: the database enforces the invariant, so concurrent creates cannot produce two rows. The test shows N parallel posts give one 201 and N-1 200s. SQLite needs no extra container.
- Breaks when: you need more than one api host. SQLite on a shared volume does not support multiple writer hosts. Writes are serialized, and the design estimates hundreds of inserts per second in WAL mode against a load of about 5 requests per second.

**3. Connection and concurrency control** (`api/app/db.py:31-46`).
- Chosen: one short-lived connection per call, `timeout=5` (the busy timeout), `synchronous=NORMAL` per connection, WAL set once in `init_db`.
- Alternatives: one shared connection (not thread-safe), or a connection pool.
- Trade-off: it is simple and safe. Closing the connection without a commit rolls back. The cost is a connect on every request. The review points to this, plus TestClient overhead on Windows, as the likely reason the perf test took 11.84 s against a 15 s budget.
- Breaks when: a writer holds the lock longer than 5 s. Then `sqlite3.OperationalError` becomes a 500 ("Internal error") on POST, and `/healthz` returns 503 only if its own `SELECT 1` fails.
- Deviation: the design lists `PRAGMA busy_timeout=5000`. The code uses `timeout=5`, which is equivalent (review nit).

**4. Validation: hand-written `normalize_url` and manual JSON parsing** (`api/app/urls.py:13-44`, `api/app/main.py:57-77`).
- Chosen: one function, the only path to the INSERT. It runs in this order: type, trim, length <= 2048, control-char/whitespace check on the raw string, `urlsplit`, scheme allowlist plus a literal `://`, host present, no `@` in netloc, port validation, rebuild.
- Alternatives: pydantic `HttpUrl`, or a regex.
- Trade-off: full control of the 422 messages and of the `{"detail": string}` format, which FastAPI's default list-shaped errors would break. It is more code than a pydantic model. The raw check has to come before `urlsplit` because `urlsplit` silently strips tab, CR and LF.
- Breaks when: more URL rules arrive (IDN, percent-encoding, fragments). The design deliberately leaves these as submitted, so two spellings of the same page get two codes. The review calls the IPv6 path only lightly exercised.

**5. Normalization scope** (`api/app/urls.py:38-44`).
- Chosen: lowercase scheme and host, drop `:80` for http and `:443` for https, empty path becomes `/`. Nothing else.
- Alternatives: aggressive canonicalization (trailing slash, query order, path case, http-to-https). These change meaning for some servers, so they were rejected.
- Trade-off: duplicate detection is safe but incomplete. `http://a.com/docs` and `http://a.com/docs/` get different codes by design.

**6. Status codes and caching** (`api/app/main.py:15-16,91-98`).
- Chosen: 302 (not 301) with `Cache-Control: no-store` on both 302 and 404, so every redirect hits the backend. 201 for create and 200 for an existing URL. 422 for invalid input, 413 for a body over 8 KB, and a generic 500.
- Alternatives: 301 with caching, which is faster but impossible to change or count later.
- Trade-off: every click costs one API call and one PK lookup. This was the product decision (clarification 5).
- Breaks when: redirect traffic grows well beyond demo load. See the scale section.

**7. Error handling and body cap** (`api/app/main.py:35-45,57-67`).
- Chosen: handlers return `{"detail": string}`. An unmatched path such as `/..%2f` gets a 404 with `no-store`. Unexpected exceptions log only the exception type and return "Internal error", so there is no stack trace or path in the body.
- Weak point: when there is no Content-Length (chunked upload) the whole body is read before the 8 KB check (`main.py:62-64`). That is harmless at demo scale. A streamed cap would be stricter.

**8. Short URL base** (`api/app/main.py:83-88`).
- Chosen: `BASE_URL` if set, else `scheme://Host` from the request. nginx forwards `Host $http_host` (`web/nginx.conf:12,18`).
- Trade-off: it works without configuration. The Host header is client-controlled, but it is only reflected to the same requester (review nit). Set `BASE_URL` in production.

**9. Frontend and proxy choices** (`web/src/App.tsx`, `web/src/api.ts`, `web/nginx.conf`).
- Chosen: plain React state with a status union, `fetch`, and same-origin through a proxy (nginx in Docker, Vite proxy in dev), so no CORS. Routing rule `^/[0-9A-Za-z]{7}$` goes to the api and everything else serves the SPA.
- Breaks when: a front-end route is ever exactly 7 alphanumeric characters. It would be sent to the api.

**10. Deployment** (`docker-compose.yml`).
- Chosen: `api` with the `linkdata` volume mounted at `/data`, and a healthcheck written in Python urllib (slim images have no curl). `web` publishes port 8080 and waits for `api` to be healthy.
- Breaks when: you scale `api` to more than one replica. They would all write one SQLite file.

## What fails first at scale

Agreed load is about 5 requests per second and up to 10,000 links (`requirements.md`, `design.md`). That load is far below every limit here. The order below is for growth beyond it.

1. **Redirect path: connection-per-request plus a DB read for every click.** Every redirect opens a SQLite connection and does a PK lookup (`db.py:61-64`). `no-store` on purpose prevents any HTTP caching. The only measurement is the 11.84 s perf test (1,401 requests plus seeding 10,000 rows, on Windows with TestClient), so I cannot give a requests-per-second ceiling. This is the first thing to take load as click traffic grows, because reads outnumber creates. Fix: an in-process LRU or Redis cache for code to URL. This is safe because links are immutable. Keep one connection per thread rather than per call.
2. **SQLite single-writer lock.** All creates serialize, with a 5 s busy timeout (`db.py:33`). The design estimates hundreds of inserts per second in WAL mode (this is an estimate, not measured here). The 20-thread create test took 0.32 s. Past that rate callers wait and some get a 500 after 5 s. Fix: batch or queue writes, or move to Postgres.
3. **Single api process and single SQLite file.** One uvicorn worker, and the file cannot be shared by several hosts. Adding replicas needs Postgres first. There is also no rate limit, so one client can fill the table, because abuse handling was agreed to be out of scope. Fix: Postgres, then replicas behind nginx, and rate limiting at the proxy.

## Frontend review

- **Loading:** `loading` disables the button and changes its label to "Shortening..." (`web/src/App.tsx:17,61-63`). A second submit while loading is ignored (`App.tsx:21`).
- **Errors:** client-side check for empty or over-long input (`App.tsx:23-27`, `web/src/api.ts:9-14`). Server `detail` text is shown in a `role="alert"` paragraph (`App.tsx:65-69`, `api.ts:16-27`). Network failure and an unexpected response body each have their own message (`api.ts:37-39,50`). The input is kept after an error. The short URL from a previous success is cleared on a new submit, because `setStatus` replaces the whole union.
- **Feedback:** the short URL is rendered as text in a `<span>` (`App.tsx:72`) with no href and no `dangerouslySetInnerHTML`, which covers the XSS risk. Copy shows "Copied", and a missing or rejected clipboard shows a manual-copy message (`App.tsx:40-48,82-86`).
- **Overcomplicated or wrong:**
  - The Copy button is empty and its visible text comes from CSS `attr(data-label)` (`App.tsx:73-81`, `styles.css:6`). The comment says this is so the error text is the only text node matching "copy", which is a trick to satisfy the test queries. It confuses readers and screen readers get the `aria-label` only.
  - The client check duplicates the server's trim and length rules, which can drift. It saves one round trip and nothing else.
  - The Copy "Copied" state is never reset except on the next submit.
- **What I would simplify:** put a plain text label on the Copy button, which means adjusting the test query. Drop the client-side length check and show the server message. Make the short link a real `<a>` only if the product wants one-click opening. It is text today by design.

## Risks covered by tests

All `test_*` names are in `api/tests/test_api.py`. UI cases are in `web/src/App.test.tsx`.

| FM | Failure mode | Test name | How it is enforced in code |
|---|---|---|---|
| FM-1 | Concurrent creates of the same URL | `test_risk_fm1_concurrent_same_url` | `url UNIQUE` plus `ON CONFLICT(url) DO NOTHING` (`api/app/db.py:17,74-77`), WAL and `timeout=5` (`db.py:33,44`) |
| FM-2 | Code collision on insert | `test_risk_fm2_collision_retry_then_exhausted` | `except sqlite3.IntegrityError: rollback; continue`, 5 attempts, then `CodesExhausted` (`db.py:78-80,86`), mapped to 500 (`main.py:80-82`) |
| FM-3 | `javascript:`, `data:`, `file:`, `ftp:`, `//host` | `test_risk_fm3_dangerous_schemes` | lowercase scheme in allowlist plus literal `://` (`api/app/urls.py:26-28`) |
| FM-4 | Userinfo (`user:pw@host`) | `test_risk_fm4_userinfo` | `"@" in parts.netloc` (`urls.py:31-32`) |
| FM-5 | Missing host | `test_risk_fm5_missing_host` | `not parts.hostname` (`urls.py:29-30`) |
| FM-6 | Control chars and whitespace, including those `urlsplit` strips | `test_risk_fm6_control_chars` | raw-string check before parsing (`urls.py:21-23`) |
| FM-7 | Duplicates around normalization | `test_risk_fm7_normalization_duplicates` | rebuild with lowercase host, default port dropped, `/` path (`urls.py:38-44`), unique on the normalized URL |
| FM-8 | Unknown or malformed code | `test_risk_fm8_unknown_code` | length/alnum guard and a 404 with `no-store` (`main.py:93-97`), 404 handler (`main.py:35-38`) |
| FM-9 | 301 or cacheable redirect | `test_risk_fm9_redirect_is_302_not_301` | `Response(status_code=302, headers={Location, no-store})` (`main.py:98`) |
| FM-10 | Restart loses data or breaks startup | `test_risk_fm10_restart_idempotent` | `CREATE TABLE IF NOT EXISTS`, WAL persists in the file (`db.py:15,41-46`), lifespan init (`main.py:20-23`) |
| FM-11 | Malformed requests | `test_risk_fm11_malformed_requests` | 413 cap, content-type check, JSON parse, dict/`url` check (`main.py:59-73`) |
| FM-12 | Invalid port | `test_risk_fm12_invalid_port` | `parts.port` inside `try`, `ValueError` becomes `InvalidUrl` (`urls.py:33,36-37`) |
| FM-13 | `healthz` route shadowed | `test_risk_fm13_healthz_never_shadowed` | `RESERVED` check (`db.py:11,52`), `/healthz` registered before `/{code}` (`main.py:48,91`) |
| FM-14 | Database unavailable | `test_risk_fm14_database_unavailable` | `sqlite3.Error` gives 503 on healthz (`main.py:50-53`), 500 on create (`main.py:80-82`) |
| FM-15 | UI error paths | `test_risk_fm15_api_errors_are_displayable` plus UI tests for 500, network failure, clipboard missing and rejected, stale URL cleared | `{"detail": string}` format (`main.py:31-32`), UI error handling (`App.tsx:29-37,40-48`, `api.ts:16-40`) |
| FM-16 | Short URL base wrong behind a proxy | `test_risk_fm16_base_url_precedence`, `test_api_short_url_*` | `BASE_URL` first, else request `Host` (`main.py:83-85`), nginx `Host $http_host` (`web/nginx.conf:12`) |
| FM-17 | HTML in a URL rendered as markup | `test_risk_fm17_html_in_url_is_data_only` plus UI XSS tests | React text node, no href, no `dangerouslySetInnerHTML` (`App.tsx:72`); the API returns JSON only |

## How to present it

**Clarifying questions that mattered:**
- Scope: create and redirect only, with no aliases, expiry, counters or history.
- Same long URL twice: return the existing code. This pushed the design to a unique constraint.
- 301 or 302: 302, so every click hits the backend.
- Duplicate detection: light normalization only, agreed in `answers-2.md`.
- Validation: allowlist http/https, require a host, reject userinfo.
- Storage and load: SQLite, demo scale, runs locally and in docker-compose.

**Approach and key insight:** correctness lives in the database, not in application code. The unique constraint on the normalized URL plus a single upsert makes concurrent creates safe without locks or a read-before-write. Everything that reaches the INSERT passes through one `normalize_url`, and the redirect target comes only from the DB.

**Walk-through example:**
1. The user submits ` HTTP://Example.COM:80/Path `.
2. The UI trims it, and `POST /api/links` sends it.
3. `normalize_url` trims it, passes the whitespace check, finds scheme `http` followed by `://`, and sees a host and no `@`. It lowercases and drops `:80`, giving `http://example.com/Path`.
4. `create_link` makes code `aB3dE9x`. The INSERT affects one row, so the answer is 201 with `{code, short_url}`.
5. Posting `http://example.com:80/Path` again gives rowcount 0, the SELECT finds the code, and the answer is 200 with the same code.
6. `GET /aB3dE9x` gives 302, `Location: http://example.com/Path`, `Cache-Control: no-store`.

**Edge cases to call out:** `JavaScript:` and leading-space schemes, `good.com@evil.com`, tab/CR/LF that `urlsplit` would hide, `:99999`, exactly 2048 vs 2049 characters, `http://a.com` vs `http://a.com/`, trailing slash on a non-empty path (kept distinct), a code equal to `healthz`, `/..%2f`.

## Likely follow-up questions

1. **Why SQLite, and when would you leave it?**
   It is persistent, needs no extra process, and has unique constraints that make concurrent writes safe. It does not support several writer hosts, so I move to Postgres when I need more than one api replica or when the write lock starts to show.
2. **How do you handle two users creating the same URL at once?**
   The unique index on `url` and a single `ON CONFLICT DO NOTHING` insert. One request inserts, and the others see rowcount 0 and read the existing code. The test with parallel posts gives one 201, N-1 200s and one row.
3. **What if two random codes collide?**
   The PK raises `IntegrityError`, the code rolls back and tries a new code, up to 5 times, then returns a 500. At 10,000 links the per-insert odds are about 2.8e-9, so this is a safety net.
4. **How would you scale redirects?**
   Add a code-to-URL cache (an in-process LRU, then Redis), because links never change. Then add replicas behind the proxy with Postgres. The `no-store` header would stay for browsers, and the cache would sit behind the api.
5. **Is this an open redirect or a phishing risk?**
   It is open by design. Any valid http(s) URL can be shortened. The allowlist blocks `javascript:` and `data:`, and userinfo is rejected, so `good.com@evil.com` does not pass. Domain blocklists and a preview page are out of scope and would be the next step.
6. **Why 302 and not 301, and why `no-store`?**
   A 301 can be cached by browsers and so would skip the backend. The product wanted every redirect to hit the server. The cost is one lookup per click.
7. **Why not pydantic for validation?**
   The 422 body must be `{"detail": string}`. FastAPI's default is a list. A hand-written function also lets me check the raw string before `urlsplit` removes tabs and newlines.
