"""Admin sessions for the CMS, and the Face ID lock.

- People log in with their existing household account (shared PocketBase
  `users`, same as lyrsync/finance). Access: role `admin`, or a row in
  shop_admins, or a username the owner added in Settings (kv `admin_usernames`,
  turned into a shop_admins row on first login).
- `csa_session` cookie: the person's PocketBase token (httpOnly, SameSite=Strict, /api).
- `csa_sid`: server-side lock state. After LOCK_IDLE_SECONDS idle the API answers
  423 until a passkey (Face ID) check succeeds.
"""

from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request, Response

from cs import config
from cs.pb import pb, q

COOKIE = "csa_session"
SID_COOKIE = "csa_sid"
COOKIE_MAX_AGE = 30 * 24 * 3600
AUTH_TTL = 60


@dataclass
class User:
    id: str
    username: str
    role: str
    token: str
    sid: str = ""


@dataclass
class LockState:
    user_id: str
    last_seen: float = field(default_factory=time.monotonic)
    unlocked: bool = False
    challenge: bytes = b""


_auth_cache: OrderedDict[str, tuple[float, dict, str]] = OrderedDict()
_locks: dict[str, LockState] = {}
_admin_ok: dict[str, float] = {}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def set_cookie(response: Response, name: str, value: str, max_age: int = COOKIE_MAX_AGE):
    response.set_cookie(name, value, max_age=max_age, httponly=True, secure=not config.DEV, samesite="strict",
                        path="/api")


def clear_session(response: Response):
    response.delete_cookie(COOKIE, path="/api")
    response.delete_cookie(SID_COOKIE, path="/api")


def forget_token(token: str):
    _auth_cache.pop(token, None)


async def verify_token(token: str) -> tuple[dict, str] | None:
    hit = _auth_cache.get(token)
    if hit and time.monotonic() - hit[0] < AUTH_TTL:
        return hit[1], hit[2]
    status, data = await pb.raw("POST", "/api/collections/users/auth-refresh", token)
    if status != 200 or "token" not in data:
        _auth_cache.pop(token, None)
        return None
    user, new_token = data["record"], data["token"]
    for t in (token, new_token):
        _auth_cache[t] = (time.monotonic(), user, new_token)
        _auth_cache.move_to_end(t)
    while len(_auth_cache) > 200:
        _auth_cache.popitem(last=False)
    return user, new_token


async def is_shop_admin(user: dict) -> bool:
    """Owner (role admin) always; others if listed. Checked at most once a minute per person."""
    if (user.get("role") or "") not in ("", "admin"):  # machine logins never
        return False
    if time.monotonic() - _admin_ok.get(user["id"], 0) < 60:
        return True
    row = await pb.first("shop_admins", f"user = {q(user['id'])}")
    ok = bool(row)
    if not ok:
        allowed = [u.lower() for u in (await pb.kv_get("admin_usernames", []) or [])]
        if user.get("role") == "admin" or (user.get("username") or "").lower() in allowed:
            await pb.create("shop_admins", {"user": user["id"], "username": user.get("username", "")})
            ok = True
    if ok:
        _admin_ok[user["id"]] = time.monotonic()
    else:
        _admin_ok.pop(user["id"], None)
    return ok


def revoke(user_id: str):
    _admin_ok.pop(user_id, None)
    for sid, st in list(_locks.items()):
        if st.user_id == user_id:
            _locks.pop(sid, None)


def new_sid(user_id: str, unlocked: bool) -> str:
    sid = secrets.token_urlsafe(32)
    _locks[sid] = LockState(user_id=user_id, unlocked=unlocked)
    if len(_locks) > 500:
        for k, _ in sorted(_locks.items(), key=lambda kv: kv[1].last_seen)[:100]:
            _locks.pop(k, None)
    return sid


async def signed_in(request: Request, response: Response) -> User:
    """A logged-in shop admin (the Face ID lock is not checked here)."""
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Please log in.")
    verified = await verify_token(token)
    if not verified:
        clear_session(response)
        raise HTTPException(401, "Your session has ended. Please log in again.")
    rec, fresh = verified
    if fresh != token:
        set_cookie(response, COOKIE, fresh)
    if not await is_shop_admin(rec):
        raise HTTPException(403, "This account doesn't have access to the shop admin. Ask the owner to add you.")
    user = User(id=rec["id"], username=rec.get("username", ""), role=rec.get("role") or "user", token=fresh)
    sid = request.cookies.get(SID_COOKIE, "")
    st = _locks.get(sid) if sid else None
    if not st or st.user_id != user.id:
        has_passkey = bool(await pb.first("shop_passkeys", f"user = {q(user.id)}"))
        sid = new_sid(user.id, unlocked=not has_passkey)
        set_cookie(response, SID_COOKIE, sid)
    user.sid = sid
    return user


async def admin(user: User = Depends(signed_in)) -> User:
    """A shop admin whose session is unlocked."""
    st = _locks[user.sid]
    now = time.monotonic()
    if st.unlocked and now - st.last_seen > config.LOCK_IDLE_SECONDS:
        if await pb.first("shop_passkeys", f"user = {q(user.id)}"):
            st.unlocked = False
    if not st.unlocked:
        raise HTTPException(423, "Locked. Unlock with Face ID.")
    st.last_seen = now
    return user
