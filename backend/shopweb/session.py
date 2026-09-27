"""Customer sessions. The `cs_session` cookie holds the customer's PocketBase
token (shop_customers auth collection); it's httpOnly and SameSite=Lax so links
from WhatsApp keep people logged in. Tokens are checked with auth-refresh and
cached for a minute."""

from __future__ import annotations

import time
from collections import OrderedDict

from fastapi import Request, Response

from cs import config
from cs.pb import pb

COOKIE = "cs_session"
MAX_AGE = 60 * 24 * 3600
TTL = 60

_cache: OrderedDict[str, tuple[float, dict, str]] = OrderedDict()


def set_session(response: Response, token: str):
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, secure=not config.DEV, samesite="lax", path="/")


def clear_session(response: Response, token: str = ""):
    _cache.pop(token, None)
    response.delete_cookie(COOKIE, path="/")


async def verify(token: str) -> tuple[dict, str] | None:
    hit = _cache.get(token)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1], hit[2]
    status, data = await pb.raw("POST", "/api/collections/shop_customers/auth-refresh", token)
    if status != 200 or "token" not in data:
        _cache.pop(token, None)
        return None
    rec, fresh = data["record"], data["token"]
    for t in (token, fresh):
        _cache[t] = (time.monotonic(), rec, fresh)
        _cache.move_to_end(t)
    while len(_cache) > 2000:
        _cache.popitem(last=False)
    return rec, fresh


def forget(token: str):
    _cache.pop(token, None)


async def load(request: Request) -> tuple[dict | None, str]:
    """(customer record or None, refreshed token to set or '')."""
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 2000:
        return None, ""
    res = await verify(token)
    if not res:
        return None, "clear"
    rec, fresh = res
    return rec, (fresh if fresh != token else "")


async def login(email: str, password: str) -> tuple[dict, str] | None:
    status, data = await pb.raw("POST", "/api/collections/shop_customers/auth-with-password",
                                json={"identity": email.strip().lower(), "password": password})
    if status != 200:
        return None
    return data["record"], data["token"]
