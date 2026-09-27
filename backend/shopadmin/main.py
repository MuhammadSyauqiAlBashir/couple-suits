"""Shop admin CMS backend (FastAPI on 127.0.0.1:8210, behind Caddy at shop-admin.*).
The static PWA is served by Caddy; this is /api only."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from cs import util
from cs.pb import PBError, pb

from . import bootstrap, routes_catalog, routes_content, routes_core, routes_orders, scheduler, studio
from .security import COOKIE, User, _locks, clear_session, client_ip, forget_token, set_cookie, signed_in

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("shopadmin")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async def start():
        for attempt in range(30):
            try:
                await bootstrap.run()
                return
            except Exception as e:  # noqa: BLE001 - PocketBase may still be starting
                log.warning("bootstrap waiting for PocketBase: %s", e)
                await asyncio.sleep(2)
    tasks = [asyncio.create_task(start()), asyncio.create_task(scheduler.run())]
    yield
    for t in tasks:
        t.cancel()
    await pb.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
for r in (routes_core.router, routes_catalog.router, routes_orders.router, routes_content.router, studio.router):
    app.include_router(r)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    body = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    headers = {"Retry-After": str(body["retry_after"])} if "retry_after" in body else None
    return JSONResponse(body, status_code=exc.status_code, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(x) for x in first.get("loc", ["", "input"])[1:]) or "input"
    return JSONResponse({"error": f"Invalid {field}: {first.get('msg', 'bad value')}."}, status_code=400)


@app.exception_handler(PBError)
async def pb_error(request: Request, exc: PBError):
    log.warning("pocketbase error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse({"error": exc.field_error()}, status_code=400 if exc.status < 500 else 502)


@app.middleware("http")
async def csrf_and_cache(request: Request, call_next):
    # Cookie-authenticated writes need a header that cross-site forms can't send.
    if request.method not in ("GET", "HEAD") and request.headers.get("x-csa") != "1":
        return JSONResponse({"error": "Missing request header."}, status_code=403)
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store")
    return response


login_limit = util.Window(10, 600)


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=72)


def public_user(u: User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role}


@app.post("/api/login")
async def login(body: Credentials, request: Request, response: Response):
    login_limit.check(client_ip(request), "Too many login attempts.")
    status, data = await pb.raw("POST", "/api/collections/users/auth-with-password", json={
        "identity": body.username.strip().lower(), "password": body.password})
    if status == 403:
        raise HTTPException(403, "Your account is waiting for approval.")
    if status != 200 or (data["record"].get("role") or "") not in ("", "admin"):
        raise HTTPException(401, "Wrong username or password.")
    set_cookie(response, COOKIE, data["token"])
    request.cookies[COOKIE] = data["token"]
    user = await signed_in(request, response)
    return {"user": public_user(user), "locked": not _locks[user.sid].unlocked}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    forget_token(request.cookies.get(COOKIE, ""))
    clear_session(response)
    return {"ok": True}


@app.get("/api/me")
async def me(user: User = Depends(signed_in)):
    s = await util.settings()
    return {"user": public_user(user), "locked": not _locks[user.sid].unlocked, "brand": s["brand_name"]}


@app.get("/api/health")
async def health():
    return {"ok": True}
