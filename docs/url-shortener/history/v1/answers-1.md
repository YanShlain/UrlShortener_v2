* Scope: Create short link + redirect only (no custom aliases, expiry, click counters, or history list).
* Idempotency / Duplicates: Submitting an already-shortened long URL returns the existing short code.
* Redirect Semantics: HTTP `302` so every redirect hits the backend rather than getting cached by the browser.
* Scale & Storage: Demo scale backed by SQLite (persistent across restarts, safe against basic concurrent writes).
* Deployment: Runs locally out of the box, plus a `docker-compose.yml` setup.
