# AGENTS.md

## Job: url-shortener
A TinyURL-style shortener. The React UI posts a long URL, the FastAPI api returns a 7-char code, and `GET /{code}` redirects with a 302.
Spec: `docs/url-shortener/design.md` (binding), `requirements.md`, `plan.md`. Solution: workspace root (`api/`, `web/`, `docker-compose.yml`).

### Stack
Python 3.12+ / FastAPI / pydantic / uv; React + TypeScript (Vite, Vitest + Testing Library); SQLite (WAL); Docker + docker-compose.

### Layout
- `api/`: `app/` (`main.py` with `app`, `urls.py`, `db.py`), `tests/`, `pyproject.toml`, `Dockerfile`
- `web/`: Vite app, tests next to code as `*.test.tsx`, `nginx.conf`, `Dockerfile`
- `docker-compose.yml`

### Commands
api (in `api/`):
- run: `uv run uvicorn app.main:app --port 8000`
- test: `uv run pytest`
- lint: `uv run ruff check .`
- type-check: `uv run mypy app`

web (in `web/`):
- run: `npm run dev`
- test: `npm test` (Vitest, single run)
- type-check: `npm run typecheck`
- build: `npm run build`

all: `docker compose up --build` at the workspace root, then open `http://localhost:8080`.

### Implementation notes
- Endpoints: `POST /api/links` (201 new, 200 existing, 422 invalid, 413 body over 8 KB, 500 generic), `GET /{code}` (302 or 404, both `no-store`), `GET /healthz` (200 or 503). Errors are `{"detail": string}`.
- Env (api): `DB_PATH` (default `data/links.db`; `/data/links.db` in Docker on the `linkdata` volume), `BASE_URL` (optional).
- `api/app/db.py` opens one connection per call (`timeout=5`); WAL is set once in `init_db`. `RESERVED` holds route names a code must never equal. Add a new top-level route name there.
- `web/src/api.ts` holds the fetch and error mapping; `web/src/App.tsx` holds the form and status state. In Docker, nginx proxies `/api/*` and `^/[0-9A-Za-z]{7}$` to the api and forwards `Host`.
- Docs: `docs/url-shortener/walkthrough.md` explains the design choices, scale limits and test coverage per failure mode (FM-1 to FM-17).
- Gate (round 2): 122 pytest cases, ruff, `mypy --strict`, web typecheck/test/build all pass.
- Known nits: the Copy button label comes from CSS `data-label` (`App.tsx`).

### Rules
- Typed code: type hints in Python (mypy clean), strict TypeScript.
- Invariants live in the storage layer: UNIQUE on `url`, PRIMARY KEY on `code`, single-statement upsert, never check-then-act.
- Validate on the server. All URL rules go through the one `normalize_url` function. The UI checks are only a convenience.
- Parameterized SQL only. The UI renders URLs as text, never as HTML.
- Redirects are 302 with `Cache-Control: no-store`.
- Tests are the acceptance criteria. Do not weaken, skip or delete them to get a pass. Fix the code.
- Follow karpathy-guidelines: state assumptions, simplest design that meets the requirements, nothing speculative, surgical changes, verifiable success criteria.
- Out of scope: auth, aliases, expiry, counters, history, rate limiting, deletion, extra normalization.
