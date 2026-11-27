# Interview solutions

A workspace of small, tested solutions to interview-style problems. Each job has its code under `solutions/<job>/` and its design, test plan and walkthrough under `docs/<job>/`.

## url-shortener

**What it does.** A TinyURL-style shortener. You paste a long URL into a web page and get a 7-character short link. Opening the short link redirects (HTTP 302) to the long URL. The page also lists the 10 most recent short links; each opens in a new tab. The list is public: every visitor sees every listed URL.

**Run locally** (from `solutions/url-shortener/`)
- API: `cd api && uv sync && uv run uvicorn app.main:app --port 8000`
- Web: `cd web && npm install && npm run dev`, then open http://localhost:5173 (Vite proxies `/api` and short codes to the API on port 8000).

**Run with Docker** (from `solutions/url-shortener/`)
- `docker compose up --build`, then open http://localhost:8080. The SQLite file lives on the named volume `linkdata`.
- No Kubernetes manifests (deploy target is Docker).

**How to use it**
- UI: enter `https://example.com/docs`, press Shorten, copy the short link. It appears at the top of "Recent links".
- API:
  - `curl -X POST localhost:8000/api/links -H "Content-Type: application/json" -d '{"url":"https://example.com/docs"}'` returns `{"code":"...","short_url":"..."}` (201 new, 200 existing).
  - `curl -i localhost:8000/<code>` returns 302 with `Location`.
  - `curl localhost:8000/api/links` returns the 10 newest links.

**Tests**
- API: `cd solutions/url-shortener/api && uv run pytest` (also `uv run ruff check .`, `uv run mypy app`).
- Web: `cd solutions/url-shortener/web && npm test` (also `npm run typecheck`, `npm run build`).
- Last gate (v2, round 1): 144 pytest cases, ruff, `mypy --strict`, and web typecheck, test and build all passed.

**Architecture.** React single page (Vite) and a FastAPI service with one SQLite file. In Docker, nginx serves the page and proxies `/api/*` and 7-character codes to the api, forwarding the `Host` header so short URLs point at the public address. URLs are validated and normalized in one function. The database enforces uniqueness (UNIQUE on `url`, PRIMARY KEY on `code`, one-statement upsert), so concurrent creates of one URL give one row. The recent list is one `SELECT ... ORDER BY created_at DESC, rowid DESC LIMIT 10`.

**Docs.** [`docs/url-shortener/`](docs/url-shortener/): [design](docs/url-shortener/design.md), [walkthrough](docs/url-shortener/walkthrough.md), [progress](docs/url-shortener/progress.md). Solution-level notes are in [`solutions/url-shortener/README.md`](solutions/url-shortener/README.md).

## Requirements
- Python 3.12 or newer and [uv](https://docs.astral.sh/uv/)
- Node.js 22 (the web Docker image builds with `node:22`) and npm
- Docker with Compose (only for the Docker run)
