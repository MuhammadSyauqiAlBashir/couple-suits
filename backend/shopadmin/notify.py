"""Web Push to the admins' phones (new orders, low stock, special days).
Same approach as the finance app: VAPID key in the private state dir, Urgency
high so iOS delivers right away, and every push logged."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from cs import config
from cs.pb import PBError, pb, q

log = logging.getLogger("shopadmin.notify")
SUBJECT = os.environ.get("CS_VAPID_SUBJECT", "mailto:admin@bashir.my.id")
_vapid: Vapid | None = None


def vapid() -> Vapid:
    global _vapid
    if _vapid is None:
        path = os.path.join(config.STATE_DIR, "vapid_private.pem")
        if os.path.exists(path):
            _vapid = Vapid.from_file(path)
        else:
            v = Vapid()
            v.generate_keys()
            os.makedirs(config.STATE_DIR, exist_ok=True)
            v.save_key(path)
            os.chmod(path, 0o600)
            _vapid = v
    return _vapid


def public_key() -> str:
    raw = vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _send_one(sub: dict, payload: str, urgency: str) -> int:
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload, vapid_private_key=vapid(), vapid_claims={"sub": SUBJECT}, ttl=24 * 3600, timeout=15,
                headers={"Urgency": urgency})
        return 201
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0
    except Exception as e:  # noqa: BLE001 - never break the caller
        log.warning("push failed: %s", e)
        return 0


async def send(title: str, body: str, url: str = "/", tag: str = "", users: list[str] | None = None,
               urgency: str = "high") -> int:
    filt = " || ".join(f"user = {q(u)}" for u in users) if users else ""
    try:
        subs = await pb.all("shop_push_subs", filter=filt)
    except PBError as e:
        log.warning("push subs unavailable: %s", e)
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or url})
    sent = 0
    for sub in subs:
        status = await asyncio.to_thread(_send_one, sub, payload, urgency)
        log.info("push %r -> %s…: %s", title[:40], sub["endpoint"][8:30], status)
        if status in (404, 410):
            await pb.delete("shop_push_subs", sub["id"])
        elif status in (200, 201):
            sent += 1
    return sent
