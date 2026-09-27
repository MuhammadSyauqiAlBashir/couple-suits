"""Background jobs in the admin service:
- every 15 s: push new orders to the admins (the storefront has no push keys; it
  marks orders `notified=false` and this loop picks them up);
- 08:00 WIB: special-day vouchers (birthdays/anniversaries in the next 7 days);
- 09:00 WIB: morning digest (open orders, pending reviews, low stock)."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import date, timedelta

from cs import catalog, util
from cs.pb import pb, q

from . import notify

log = logging.getLogger("shopadmin.scheduler")


async def push_new_orders():
    for o in await pb.all("shop_orders", filter="notified = false", sort="created"):
        items = await pb.all("shop_order_items", filter=f"order = {q(o['id'])}", fields="qty,preorder")
        n = sum(int(i.get("qty") or 1) for i in items)
        city = (o.get("address") or {}).get("city", "")
        await pb.update("shop_orders", o["id"], {"notified": True})
        await notify.send(f"🛍️ Pesanan baru {o['number']}",
                          f"{o['contact_name']} · {n} item · {catalog.rupiah(o['total'])}{' · ' + city if city else ''}"
                          f"{' · pre-order' if o.get('has_preorder') else ''}", f"/#order/{o['id']}", tag=f"order-{o['id']}")


def upcoming(mmdd_date: str, today: date, days: int = 7) -> date | None:
    """Next occurrence of a YYYY-MM-DD anniversary within `days` days."""
    try:
        m, d = int(mmdd_date[5:7]), int(mmdd_date[8:10])
    except (ValueError, IndexError):
        return None
    for year in (today.year, today.year + 1):
        try:
            when = date(year, m, d)
        except ValueError:  # 29 Feb
            when = date(year, 2, 28)
        if today <= when <= today + timedelta(days=days):
            return when
    return None


async def special_days():
    s = await util.settings(fresh=True)
    pct, valid = int(s.get("special_voucher_percent") or 0), int(s.get("special_voucher_days") or 14)
    if pct <= 0:
        return
    today = util.now_local().date()
    created = []
    for c in await pb.all("shop_customers", filter="marketing_ok = true && (birthday != '' || anniversary != '')",
                          fields="id,name,email,phone,birthday,anniversary"):
        for kind in ("birthday", "anniversary"):
            when = upcoming(c.get(kind) or "", today)
            if not when:
                continue
            key = f"special:{kind}:{c['id']}:{when.year}"
            if not await pb.event_once(key):
                continue
            code = ("ULTAH-" if kind == "birthday" else "ANNIV-") + secrets.token_hex(3).upper()
            ends = (when + timedelta(days=valid)).strftime("%Y-%m-%d 16:59:59.000Z")
            await pb.create("shop_vouchers", {
                "code": code, "kind": "percent", "value": pct, "active": True, "special": kind, "customer": c["id"],
                "usage_limit": 1, "per_customer_limit": 1, "min_spend": 0, "max_discount": 0, "starts": "", "ends": ends,
                "label_id": f"Hadiah {'ulang tahun' if kind == 'birthday' else 'anniversary'} {pct}%",
                "label_en": f"{'Birthday' if kind == 'birthday' else 'Anniversary'} gift {pct}% off"})
            created.append(f"{c.get('name') or c['email']} ({'ultah' if kind == 'birthday' else 'anniv'} {when:%d %b})")
    if created:
        await notify.send(f"🎁 {len(created)} voucher hari spesial dibuat",
                          "Kirim ucapan via WhatsApp: " + ", ".join(created)[:180], "/#customers", tag="special")


async def digest():
    open_new = (await pb.list("shop_orders", filter="status = 'new'", per_page=1, skip_total=False)).get("totalItems", 0)
    unpaid = (await pb.list("shop_orders", filter="status = 'awaiting_payment'", per_page=1, skip_total=False)).get("totalItems", 0)
    reviews = (await pb.list("shop_reviews", filter="status = 'pending'", per_page=1, skip_total=False)).get("totalItems", 0)
    low = await pb.all("shop_variants", filter="active = true && stock <= 2 && product.stock_mode = 'ready' && product.status = 'live'",
                       fields="id")
    parts = []
    if open_new:
        parts.append(f"{open_new} pesanan baru belum dikonfirmasi")
    if unpaid:
        parts.append(f"{unpaid} menunggu bayar")
    if reviews:
        parts.append(f"{reviews} ulasan menunggu")
    if low:
        parts.append(f"{len(low)} ukuran hampir habis")
    if parts:
        await notify.send("☀️ Ringkasan pagi", " · ".join(parts), "/", tag="digest", urgency="normal")


async def daily(job, hour: int, name: str):
    now = util.now_local()
    if now.hour >= hour and await pb.event_once(f"{name}:{now:%Y-%m-%d}"):
        try:
            await job()
        except Exception:  # noqa: BLE001
            log.exception("%s failed", name)


async def run():
    await asyncio.sleep(5)
    while True:
        try:
            await push_new_orders()
            await daily(special_days, 8, "special-days")
            await daily(digest, 9, "digest")
        except Exception as e:  # noqa: BLE001 - keep the loop alive (PocketBase restarts etc.)
            log.warning("scheduler: %s", e)
        await asyncio.sleep(15)
