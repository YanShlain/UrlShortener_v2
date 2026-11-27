# URL shortener

FastAPI + SQLite API (`api/`) and a React UI (`web/`).

## Run locally
- API: `cd api && uv sync && uv run uvicorn app.main:app --port 8000`
- Web: `cd web && npm install && npm run dev`
- API tests: `cd api && uv run pytest -q`

## Run with Docker
`docker compose up --build`, then open http://localhost:8080

## Environment variables (api)
- `DB_PATH`: SQLite file (default `data/links.db`; `/data/links.db` in Docker, on the `linkdata` volume).
- `BASE_URL`: prefix used to build the returned short URL.

## Known limitation
Open redirect is accepted by design: any valid http(s) URL can be shortened (out of scope).

## recent links (v2)
`GET /api/links` returns the 10 most recent links, newest first, and the page lists them under the form. Recent links are visible to everyone: any visitor sees every listed URL, including secrets in query strings. This is accepted by design (no auth, no filtering).
