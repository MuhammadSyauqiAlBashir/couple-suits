"""Storefront (FastAPI + Jinja SSR on 127.0.0.1:8200, behind Caddy).

Caddy serves /static and /media itself; this app renders pages and a small
JSON API for the cart, checkout and wishlist."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from cs import config, util
from cs.pb import PBError, pb

from . import account, api, i18n, pages, session, stats, store
from .render import STATIC, render

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("shopweb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(stats.run())
    yield
    task.cancel()
    await stats.flush()
    await pb.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(api.router)
app.include_router(account.router)
app.include_router(pages.router)

if config.DEV:  # in production Caddy serves these
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    os.makedirs(config.MEDIA_DIR, exist_ok=True)
    app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if wants_json(request) or not hasattr(request.state, "settings"):
        body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        return JSONResponse(body, status_code=exc.status_code)
    if exc.status_code == 404:
        return render(request, "error.html", 404, code=404)
    if exc.status_code in (401, 403, 409, 413, 429):
        msg = exc.detail.get("error") if isinstance(exc.detail, dict) else str(exc.detail)
        return render(request, "error.html", exc.status_code, code=exc.status_code, message=msg)
    return render(request, "error.html", exc.status_code, code=500)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = str(first.get("loc", ["", "input"])[-1])
    return JSONResponse({"error": f"Invalid {field}: {first.get('msg', 'bad value')}."}, status_code=400)


@app.exception_handler(PBError)
async def pb_error(request: Request, exc: PBError):
    log.warning("pocketbase error on %s %s: %s", request.method, request.url.path, exc)
    if wants_json(request):
        return JSONResponse({"error": exc.field_error()}, status_code=400 if exc.status < 500 else 502)
    return render(request, "error.html", 500, code=500) if hasattr(request.state, "settings") else \
        JSONResponse({"error": "Server error."}, status_code=500)


# ---------------------------------------------------------------------------
# Every request: language, CSRF, settings/catalog cache, customer, analytics
# ---------------------------------------------------------------------------

SHOP_HOST = urlparse(config.SHOP_URL).netloc


def same_origin(request: Request) -> bool:
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    host = urlparse(origin).netloc
    if not host:
        return False
    if config.DEV and host.startswith(("127.0.0.1", "localhost")):
        return True
    return host == SHOP_HOST


@app.middleware("http")
async def every_request(request: Request, call_next):
    path = request.url.path
    if path.startswith(("/static/", "/media/")):
        return await call_next(request)

    # Cookie-authenticated writes must come from our own pages.
    if request.method not in ("GET", "HEAD"):
        if not same_origin(request) or (path.startswith("/api/") and request.headers.get("x-cs") != "1"):
            return JSONResponse({"error": "Request blocked."}, status_code=403)

    q_lang = request.query_params.get("lang")
    lang = q_lang if q_lang in i18n.LANGS else request.cookies.get("lang")
    request.state.lang = lang if lang in i18n.LANGS else "id"
    try:
        request.state.settings = await util.settings()
        await store.refresh()
        customer, token = await session.load(request)
    except Exception as e:  # noqa: BLE001 - PocketBase down: show a friendly error, not a stack trace
        log.error("startup data unavailable: %s", e)
        return JSONResponse({"error": "The shop is temporarily unavailable."}, status_code=503)
    request.state.customer = customer

    response = await call_next(request)

    if token == "clear":
        session.clear_session(response)
    elif token:
        session.set_session(response, token)
    if q_lang in i18n.LANGS and request.cookies.get("lang") != q_lang:
        response.set_cookie("lang", q_lang, max_age=365 * 24 * 3600, secure=not config.DEV, samesite="lax", path="/")
    ctype = response.headers.get("content-type", "")
    if request.method == "GET" and response.status_code == 200 and ctype.startswith("text/html"):
        response.headers.setdefault("Cache-Control", "private, no-cache")
        stats.page_view(path, request.client.host if request.client else "", request.headers.get("user-agent", ""),
                        request.headers.get("referer", ""), request.query_params.get("utm_source", "")[:60])
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/healthz")
async def health():
    return {"ok": True}


_ = HTTPException
