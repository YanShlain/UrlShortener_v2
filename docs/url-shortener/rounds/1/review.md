VERDICT: CHANGES

1. Contract: PARTIAL. API routes, status codes and `{"detail": str}` errors match design.md. `README.md` (listed as a deliverable in the Contract section: run instructions plus the documented open-redirect note) is missing from `solutions/url-shortener/`. Add it.
2. Hot path: OK. POST = 1 connection, 3 PRAGMAs, 1 INSERT (+1 SELECT on duplicate), 1 commit. GET = 1 connection, 1 PK lookup. Healthz = SELECT 1. The 10k perf test takes 12.3 s of its 15 s budget, which is little headroom (see Nits).
3. Invariants under concurrency: OK. `ON CONFLICT(url) DO NOTHING` in a single statement, PK on code, `IntegrityError` leads to rollback and retry (5 attempts), busy_timeout 5 s, WAL, one connection per call. No JSON file. No check-then-act.
4. Trust boundaries: OK. `normalize_url` validates on the raw trimmed string before `urlsplit`, in the design order. SQL is parameterized. The body is capped at 8 KB. The UI renders text only.
5. Protocol semantics: OK. 302 with `no-store`, 404 with `no-store` (including unmatched paths via the handler), `/healthz` registered before `/{code}`, generic 500 with no trace.
6. UI states: OK. Loading (button disabled, "Shortening..."), success, error (`role=alert`) and clipboard error are all present. Input is kept on error. The old short URL is cleared when a new submit starts (the status is replaced).
7. No test gaming: OK. No hard-coded outputs or test-only paths. `RESERVED` is a real rule.
8. Failure modes covered: OK. FM-1 to FM-17 each have a `test_risk_*` (FM-15 and FM-17 are also covered in the web tests). Handling is in `urls.py`, `db.py` and `main.py` as designed.
9. Simplicity: OK, with a small amount of redundancy (see Nits). No speculative options or dependencies.
10. Readability: OK. The code is short, with comments at the invariants. No dead code.

## Required change
- Add `solutions/url-shortener/README.md`. It needs local run steps (api with uv, web with npm), the Docker run (`docker compose up`, open http://localhost:8080), the env vars `DB_PATH` and `BASE_URL`, and a line that open redirect is accepted by design (out of scope).

## Nits
- `connect()` runs `PRAGMA journal_mode=WAL` on every request. WAL persists in the file, so it only needs to run in `init_db`. That would cut per-request cost and the 12 s perf-test time.
- `sqlite3.connect(timeout=5)` and `PRAGMA busy_timeout=5000` both set the same thing. One is enough.
- `create_link` reads the full body before the size check when `Content-Length` is absent (chunked). The risk is minor at 8 KB.
- `main.py` http_error: non-404 HTTP errors (405) return no `no-store`. That is fine, since the design only requires it for redirect and 404.

## Critical logic to audit
1. api/app/db.py:67 - `create_link`: single-statement insert-or-fetch with retry on PK `IntegrityError` - Be ready to explain why a url conflict does not raise (DO NOTHING) while a code conflict does, why `rollback()` precedes the retry, and why rowcount 0 leads to a SELECT with no race (rows are immutable) - looks right.
2. api/app/urls.py:19 - `normalize_url` validation order: the raw-string control/whitespace check runs before `urlsplit` - Explain why (urlsplit strips tab/CR/LF), and that the `://` check at line 27 blocks `javascript:` and `a.com` - looks right. One thing to know: `host = parts.netloc.lower()` with the `rfind(":")` strip also handles IPv6 brackets, and userinfo is already rejected earlier.
3. api/app/main.py:60 - `create_link` handler: manual body parsing (8 KB cap, content-type, JSON shape) replaces FastAPI validation so every error uses the `{detail: str}` format - Check that all malformed inputs give 422/413 and never 500 - looks right. A `Content-Length` header that is not numeric falls through to the real body length check.
4. api/app/main.py:100 - `redirect`: code shape check, DB lookup, `Location` taken only from the DB, `no-store` on both 302 and 404 - Explain why no request data reaches the header - looks right.
5. api/app/db.py:25-33 - connection handling: per-call connection, WAL, busy_timeout - Explain why a shared connection is avoided and what "database is locked" would look like under contention (it surfaces as a 500) - works, but see the PRAGMA nit.
