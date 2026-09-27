"""Placing orders. Everything is re-priced on the server; stock for ready-stock
items is reserved (decremented) when the order is placed. One process serves the
shop, so an asyncio lock makes check-then-reserve safe."""

from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import HTTPException

from cs import pricing, util
from cs.pb import PBError, pb, q

from . import stats

log = logging.getLogger("shopweb.orders")

_lock = asyncio.Lock()


async def next_number() -> str:
    prefix = "CS-" + util.now_local().strftime("%y%m%d") + "-"
    last = await pb.first("shop_orders", f"number ~ {q(prefix + '%')}", sort="-number")
    seq = int(last["number"].rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:03d}"


async def place(*, lines: list[dict], contact: dict, address: dict, note: str, voucher: str, lang: str,
                customer: dict | None) -> dict:
    async with _lock:
        quote = await pricing.quote(lines, lang=lang, voucher_code=voucher,
                                    customer_id=customer["id"] if customer else "", phone=contact["phone"])
        if quote.errors or not quote.lines:
            raise HTTPException(409, {"error": quote.errors[0] if quote.errors else "Empty order.",
                                      "errors": quote.errors, "quote": quote.as_dict()})
        if voucher and quote.voucher_error:
            raise HTTPException(409, {"error": quote.voucher_error, "errors": [quote.voucher_error],
                                      "quote": quote.as_dict()})
        token = secrets.token_urlsafe(24)
        order = None
        for _ in range(5):
            number = await next_number()
            try:
                order = await pb.create("shop_orders", {
                    "number": number, "token": token, "customer": customer["id"] if customer else "",
                    "contact_name": contact["name"], "phone": contact["phone"], "email": contact.get("email", ""),
                    "address": address, "lang": lang, "status": "new", "items_total": quote.items_total,
                    "discount_total": quote.discount_total, "shipping_cost": 0, "shipping_set": False,
                    "total": quote.total, "voucher_code": quote.voucher["code"] if quote.voucher else "",
                    "discounts": quote.discounts, "customer_note": note, "admin_note": "",
                    "timeline": [{"at": util.pb_now(), "status": "new", "by": "customer"}],
                    "notified": False, "has_preorder": quote.has_preorder,
                })
                break
            except PBError as e:
                if "number" not in str(e.data):
                    raise
        if not order:
            raise HTTPException(503, "Please try again.")
        try:
            for ln in quote.lines:
                await pb.create("shop_order_items", {
                    "order": order["id"], "product": ln["product"], "variant": ln["variant"],
                    "product_name": ln["name"], "product_slug": ln["slug"], "cut": ln["cut"], "size": ln["size"],
                    "color": ln["color_label"], "role": ln["role_label"] or ln["role"], "member_name": ln["member"],
                    "set_key": ln["set_key"], "unit_price": ln["regular"], "price": ln["price"], "qty": ln["qty"],
                    "line_total": ln["line_total"], "image": ln["image"], "preorder": ln["preorder"],
                    "preorder_days": ln["preorder_days"],
                })
                if not ln["preorder"]:
                    await pb.update("shop_variants", ln["variant"], {"stock-": ln["qty"]})
            if quote.voucher:
                await pb.create("shop_voucher_uses", {"voucher": quote.voucher["id"], "order": order["id"],
                                                      "customer": customer["id"] if customer else "",
                                                      "phone": contact["phone"]})
        except Exception:
            log.exception("order %s: items failed; cancelling", order["number"])
            await pb.update("shop_orders", order["id"], {"status": "cancelled", "admin_note": "Automatic: saving items failed."})
            raise
    stats.add("orders")
    stats.add("revenue", "", quote.total)
    for ln in quote.lines:
        stats.add("sold", ln["product"], ln["qty"])
    log.info("order %s placed: %d lines, total %d", order["number"], len(quote.lines), quote.total)
    return order
