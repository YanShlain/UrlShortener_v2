VERDICT: PASS

1. Contract: matches design.md. Status codes 201/200/422/413/404/500/503, the `{"detail": string}` error format, Location plus no-store on 302 and 404, and the 7-char route filter are all present. Proxy rules in nginx.conf and vite.config.ts match, and Host is forwarded.
2. Hot path: POST does one connection and one INSERT, plus a SELECT only on a duplicate and a commit only on a create. Redirect does one connection and one PK lookup. This matches the claims. The perf test took 11.8 s against a 15 s budget (the design says 2-4 s is typical). The cost is mostly connection-per-call plus TestClient overhead on Windows. It passes, but the margin is thin.
3. Invariants under concurrency: enforced by the DB. `url UNIQUE` plus `ON CONFLICT(url) DO NOTHING` in a single statement, code `PRIMARY KEY`, a `CHECK` on length, and retry on `IntegrityError` with a rollback. There is no check-then-act. WAL is set once in `init_db`, and `timeout=5` gives the 5 s busy timeout. SQLite is the specified storage, not a JSON file.
4. Trust boundaries: `normalize_url` is the only path to the INSERT. It checks type, trim, length, control chars and whitespace on the raw string, scheme allowlist plus `://`, host, userinfo and port. The UI renders the short URL as text, with no `dangerouslySetInnerHTML` and no href. The 8 KB body cap is applied. Queries are parameterized.
5. Protocol semantics: 302 with `no-store` on both redirect and 404. Unmatched paths such as `/..%2f` get a 404 JSON error with `no-store` through the exception handler. `/healthz` is registered before `/{code}`. `RESERVED` blocks `healthz` codes.
6. UI states: loading (button disabled, "Shortening..."), success, and error (role=alert) are all handled. Input is kept after an error. A stale short URL is cleared on a new submit. A missing or rejected clipboard shows a message.
7. No test gaming: none found. There are no hard-coded outputs and no test-only paths.
8. Failure modes: FM-1 through FM-17 are handled in code where the design says, and the gate reports 122 tests passing, including the `test_risk_*` ones. I only spot-checked the `test_risk_*` names against the FM list.
9. Simplicity: small and direct (3 api modules, a 2-file UI). No speculative options. Open redirect is documented in the README.
10. Readability: clear names, short comments at the invariants, no dead code.

## Nits
- `web/src/App.tsx:124-132` and `styles.css:6`: the Copy button is empty and takes its visible label from CSS `attr(data-label)`. That is a test-driven trick and surprising to read. A plain text label would be clearer, unless a test truly forbids it.
- `main.py:171`: `short_url` is built from the client-supplied `Host` header when `BASE_URL` is unset. This is as designed. It is only reflected to the same requester, but note it as a host-header caveat.
- `main.py:148`: without Content-Length (chunked), the whole body is read before the 8 KB check. This is harmless at demo scale, but a streamed cap would be stricter.
- `db.py:33-35`: busy_timeout is set via `timeout=5` and `synchronous` per connection. This is fine, but it differs from the literal PRAGMA list in design.md.
- A stray `solutions/url-shortener/.ruff_cache/` exists at the solution root, with no root .gitignore covering it.

## Critical logic to audit
1. api/app/db.py:67-86 - `create_link` does an insert-or-fetch with `ON CONFLICT(url) DO NOTHING`, retries a code PK collision, and exhausts after 5 attempts. The candidate should explain why `rowcount==0` means the URL exists. They should also explain why the fallback SELECT runs inside the same write transaction, and why the connection closing without a commit is a rollback. - looks right.
2. api/app/urls.py:197-228 - `normalize_url` validates in the design's order, with the raw whitespace check before `urlsplit`. The candidate should explain why `url[len(scheme):len(scheme)+3] == "://"` is needed (it rejects `javascript:` and `a.com`). They should also explain how the port is stripped from `netloc` by `rfind(":")` with the IPv6 `]` guard, and why `@` in `netloc` catches userinfo. - looks right. The IPv6 path is lightly exercised.
3. api/app/main.py:143-174 - the POST handler's body cap, content-type check, manual JSON parsing, and mapping of DB errors to a generic 500. The candidate should justify not using pydantic (it gives full control of the 422 format) and explain the 413 behaviour. - looks right. The only weakness is the chunked body read noted above.
4. api/app/main.py:177-184 and 121-125 - the redirect takes `Location` only from the DB, with `no-store` on both 302 and 404, and a 404 handler for unmatched routes. The candidate should check that `/healthz` is not shadowed and that no request data reaches headers. - looks right.
5. api/app/db.py:41-46 and 31-38 - schema and WAL are set up once at startup, and there is one connection per call with `timeout=5`. The candidate should explain why concurrent writers see no "database is locked" (busy timeout plus short transactions), and why the 5 s timeout bounds the FM-14 behaviour. - looks right. The perf margin is the only concern.
