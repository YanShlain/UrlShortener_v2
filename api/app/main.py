import json
import logging
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .urls import InvalidUrl, normalize_url

MAX_BODY = 8 * 1024
NO_STORE = {"Cache-Control": "no-store"}
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.init_db()  # idempotent
    yield


app = FastAPI(
    lifespan=lifespan, redirect_slashes=False, docs_url=None, redoc_url=None, openapi_url=None
)


def error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404:  # unmatched paths like /..%2f
        return error(404, "Not found", NO_STORE)
    return error(exc.status_code, str(exc.detail))


@app.exception_handler(Exception)
async def unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error: %s", type(exc).__name__)  # no trace/paths to the client
    return error(500, "Internal error")


@app.get("/healthz")
def healthz() -> JSONResponse:
    try:
        db.ping()
    except sqlite3.Error:
        return error(503, "database unavailable")
    return JSONResponse({"status": "ok"})


@app.post("/api/links")
async def create_link(request: Request) -> JSONResponse:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY:
        return error(413, "Request body too large")
    body = await request.body()
    if len(body) > MAX_BODY:
        return error(413, "Request body too large")
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype != "application/json":
        return error(422, "Content-Type must be application/json")
    try:
        data = json.loads(body)
    except ValueError:
        return error(422, "Request body must be valid JSON")
    if not isinstance(data, dict) or "url" not in data:
        return error(422, 'Request body must be a JSON object with a "url" field')
    try:
        url = normalize_url(data["url"])
    except InvalidUrl as exc:
        return error(422, str(exc))
    try:
        code, created = db.create_link(url)
    except (sqlite3.Error, db.CodesExhausted) as exc:
        log.error("create failed: %s", type(exc).__name__)
        return error(500, "Internal error")
    base = os.environ.get("BASE_URL", "").rstrip("/")
    if not base:
        base = f"{request.url.scheme}://{request.headers.get('host', request.url.netloc)}"
    return JSONResponse(
        {"code": code, "short_url": f"{base}/{code}"}, status_code=201 if created else 200
    )


@app.get("/{code}")
def redirect(code: str) -> Response:
    if len(code) != 7 or not (code.isascii() and code.isalnum()):
        return error(404, "Not found", NO_STORE)
    url = db.get_url(code)
    if url is None:
        return error(404, "Not found", NO_STORE)
    return Response(status_code=302, headers={"Location": url, **NO_STORE})
