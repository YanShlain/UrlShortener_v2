# AGENTS.md

## Job: url-shortener (v2)
A TinyURL-style shortener. The React UI posts a long URL, the FastAPI api returns a 7-char code, and `GET /{code}` redirects with a 302. v2: the front page lists the 10 most recent short URLs; each opens in a new tab.
Spec: `docs/url-shortener/design.md` (binding), `requirements.md`, `plan.md`. Solution: `solutions/url-shortener/` (`api/`, `web/`, `docker-compose.yml`).

### Stack
Python 3.12+ / FastAPI / pydantic / uv; React + TypeScript (Vite, Vitest + Testing Library); SQLite (WAL); Docker + docker-compose.

### Layout
Paths are relative to `solutions/url-shortener/`.
- `api/`: `app/` (`main.py` with `app`, `urls.py`, `db.py`), `tests/`, `pyproject.toml`, `Dockerfile`
- `web/`: Vite app (`src/App.tsx`, `src/RecentLinks.tsx`, `src/api.ts`, `src/styles.css`), tests next to code as `*.test.tsx`, `nginx.conf`, `Dockerfile`
- `docker-compose.yml`, `README.md` (run notes and the privacy notice; a test reads it)
- Docs: `docs/url-shortener/walkthrough.md` (design choices, scale limits, FM-1 to FM-23 coverage)
- Gate (v2, round 1): 144 pytest cases, ruff, `mypy --strict`, web typecheck/test/build all pass.

### Commands
api (in `solutions/url-shortener/api/`):
- run: `uv run uvicorn app.main:app --port 8000`
- test: `uv run pytest`
- lint: `uv run ruff check .`
- type-check: `uv run mypy app`

web (in `solutions/url-shortener/web/`):
- run: `npm run dev`
- test: `npm test` (Vitest, single run)
- type-check: `npm run typecheck`
- build: `npm run build`

all: `docker compose up --build` in `solutions/url-shortener/`, then open `http://localhost:8080`.

### Implementation notes
- Endpoints: `POST /api/links` (201 new, 200 existing, 422 invalid, 413 body over 8 KB, 500 generic), `GET /api/links` (v2: 10 newest, `[{code, short_url, url, created_at}]`, `no-store`, 500 generic), `GET /{code}` (302 or 404, both `no-store`), `GET /healthz` (200 or 503). Errors are `{"detail": string}`.
- List query: `ORDER BY created_at DESC, rowid DESC LIMIT 10`. The limit is a constant, never a request parameter. Resubmitting a URL must not change the order. The `short_url` base logic (`BASE_URL`, else request origin) lives in one helper shared by both endpoints.
- Env (api): `DB_PATH` (default `data/links.db`; `/data/links.db` in Docker on the `linkdata` volume), `BASE_URL` (optional).
- `api/app/db.py` opens one connection per call (`timeout=5`); WAL is set once in `init_db`. `RESERVED` holds route names a code must never equal. Add a new top-level route name there.
- `web/src/api.ts` holds the fetches (`createLink`, `listLinks`) and error mapping; `web/src/App.tsx` holds the form, status state and the "Recent links" list. The list loads on mount and after each successful create, ignores stale responses, and a list error never blocks the form. In Docker, nginx proxies `/api/*` and `^/[0-9A-Za-z]{7}$` to the api and forwards `Host`.
- List rows: `<a href={short_url} target="_blank" rel="noopener noreferrer">` plus the full URL as a text node. Never use the stored URL as an `href`.
- Privacy: the list is public to every visitor by design. Keep the notice in the UI and README.

### Rules
- Typed code: type hints in Python (mypy clean), strict TypeScript.
- Invariants live in the storage layer: UNIQUE on `url`, PRIMARY KEY on `code`, single-statement upsert, never check-then-act.
- Validate on the server. All URL rules go through the one `normalize_url` function. The UI checks are only a convenience.
- Parameterized SQL only. The UI renders URLs as text, never as HTML (no `dangerouslySetInnerHTML`).
- Redirects are 302 with `Cache-Control: no-store`.
- Tests are the acceptance criteria. Do not weaken, skip or delete them to get a pass. Fix the code.
- Follow karpathy-guidelines: state assumptions, simplest design that meets the requirements, nothing speculative, surgical changes, verifiable success criteria.
- Out of scope: auth, aliases, expiry, counters, history beyond the fixed top 10 (no paging, search, polling), rate limiting, deletion, extra normalization.
