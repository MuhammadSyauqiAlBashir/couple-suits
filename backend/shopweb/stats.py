"""Built-in, cookie-free analytics. Counters live in memory and are flushed to
shop_stats (day, metric, dim, count) every minute. Unique visitors are counted
with a daily-rotating salted hash of IP + browser, never stored."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
from collections import Counter
from urllib.parse import urlparse

from cs import config, util
from cs.pb import PBError, pb, q

log = logging.getLogger("shopweb.stats")

BOT = re.compile(r"bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|curl|wget|python|headless|monitor",
                 re.I)

_counts: Counter = Counter()
_seen: set[str] = set()
_day = [""]
_salt = [secrets.token_bytes(16)]


def _roll():
    d = util.today()
    if d != _day[0]:
        _day[0] = d
        _seen.clear()
        _salt[0] = secrets.token_bytes(16)
    return d


def add(metric: str, dim: str = "", n: int = 1):
    _counts[(_roll(), metric, dim[:200])] += n


def page_view(path: str, ip: str, ua: str, referer: str, utm: str = ""):
    if not ua or BOT.search(ua):
        return
    day = _roll()
    add("pageviews")
    visitor = hashlib.sha256(_salt[0] + f"{ip}|{ua}".encode()).hexdigest()[:20]
    if visitor not in _seen:
        _seen.add(visitor)
        add("visitors")
        source = utm or ""
        if not source and referer:
            host = (urlparse(referer).hostname or "").lower().removeprefix("www.")
            own = (urlparse(config.SHOP_URL).hostname or "").lower()
            if host and host != own:
                source = host
        add("sources", source or "direct")
        device = "mobile" if re.search(r"Mobi|Android|iPhone", ua) else "desktop"
        add("devices", device)
    _ = day
    add("pages", path[:120])


async def flush():
    if not _counts:
        return
    items = list(_counts.items())
    _counts.clear()
    for (day, metric, dim), n in items:
        try:
            rec = await pb.first("shop_stats", f"day = {q(day)} && metric = {q(metric)} && dim = {q(dim)}")
            if rec:
                await pb.update("shop_stats", rec["id"], {"count+": n})
            else:
                await pb.create("shop_stats", {"day": day, "metric": metric, "dim": dim, "count": n})
        except PBError as e:
            log.warning("stats flush %s/%s: %s", metric, dim, e)
            _counts[(day, metric, dim)] += n  # try again next time


async def run():
    while True:
        await asyncio.sleep(60)
        try:
            await flush()
        except Exception as e:  # noqa: BLE001 - never let analytics crash the shop
            log.warning("stats flush failed: %s", e)
