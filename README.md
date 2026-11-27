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
