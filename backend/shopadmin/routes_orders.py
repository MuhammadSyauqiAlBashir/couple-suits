"""Admin API: orders (status, shipping cost, WhatsApp messages), customers, reviews."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from cs import catalog, config, util
from cs.pb import pb, q

from .security import User, admin

router = APIRouter(prefix="/api")

STATUSES = ["new", "confirmed", "awaiting_payment", "paid", "in_production", "shipped", "completed", "cancelled"]
STATUS_LABEL = {"new": "New", "confirmed": "Confirmed", "awaiting_payment": "Awaiting payment", "paid": "Paid",
                "in_production": "In production", "shipped": "Shipped", "completed": "Completed", "cancelled": "Cancelled"}

# WhatsApp message templates. {placeholders} are filled from the order. Editable in Settings.
WA_TEMPLATES = {
    "confirm": {
        "label": "Confirm + shipping cost",
        "id": "Halo {name}, terima kasih sudah memesan di {brand} 🙏\n\nPesanan *{number}*:\n{items}\n\nSubtotal: {total}\n"
              "Ongkir ke {city}: {shipping}\n*Total bayar: {grand}*\n\n{bank}\n\nMohon kirim bukti transfer di chat ini ya. "
              "Status pesanan: {link}",
        "en": "Hi {name}, thank you for ordering from {brand} 🙏\n\nOrder *{number}*:\n{items}\n\nSubtotal: {total}\n"
              "Shipping to {city}: {shipping}\n*Total to pay: {grand}*\n\n{bank}\n\nPlease send the transfer receipt in this "
              "chat. Order status: {link}",
    },
    "reminder": {
        "label": "Payment reminder",
        "id": "Halo {name}, mengingatkan pesanan *{number}* sebesar *{grand}* belum kami terima pembayarannya. "
              "Kalau sudah transfer, kirim buktinya di sini ya. Terima kasih!",
        "en": "Hi {name}, a gentle reminder that we haven't received payment for order *{number}* (*{grand}*) yet. "
              "If you've paid, please send the receipt here. Thank you!",
    },
    "paid": {
        "label": "Payment received",
        "id": "Halo {name}, pembayaran untuk pesanan *{number}* sudah kami terima. {production}Kami kabari lagi saat dikirim. "
              "Status: {link}",
        "en": "Hi {name}, we've received payment for order *{number}*. {production}We'll let you know when it ships. "
              "Status: {link}",
    },
    "shipped": {
        "label": "Shipped + tracking",
        "id": "Halo {name}, pesanan *{number}* sudah dikirim via {courier}. No. resi: *{tracking}*. Semoga suka! "
              "Setelah sampai, boleh minta ulasan dan foto keluarga di sini: {link}",
        "en": "Hi {name}, order *{number}* is on its way with {courier}. Tracking number: *{tracking}*. We hope you love it! "
              "Once it arrives, we'd love a review and a family photo here: {link}",
    },
    "thanks": {
        "label": "Thank you + review",
        "id": "Halo {name}, terima kasih sudah berbelanja di {brand}. Kalau berkenan, bagikan ulasan dan foto keluarga "
              "di sini ya: {link} 💛",
        "en": "Hi {name}, thank you for shopping with {brand}. If you have a moment, we'd love a review and a family "
              "photo here: {link} 💛",
    },
}


def order_link(order: dict) -> str:
    return f"{config.SHOP_URL}/order/{order['number']}?t={order['token']}"


async def wa_messages(order: dict, items: list[dict]) -> list[dict]:
    s = await util.settings()
    lang = order.get("lang") if order.get("lang") in ("id", "en") else "id"
    custom = s.get("wa_templates") or {}
    lines = []
    for it in items:
        who = it.get("role") or ""
        if it.get("member_name"):
            who += f" ({it['member_name']})"
        lines.append(f"• {it['product_name']} — {who + ' · ' if who else ''}{catalog.label(catalog.CUTS, it['cut'], lang)} "
                     f"{catalog.size_label(it['size'], lang)}{' ×' + str(it['qty']) if it['qty'] > 1 else ''}: "
                     f"{catalog.rupiah(it['line_total'])}")
    shipping = catalog.rupiah(order["shipping_cost"]) if order.get("shipping_set") else ("(dikonfirmasi)" if lang == "id" else "(to confirm)")
    production = ""
    if order.get("has_preorder"):
        days = max([int(i.get("preorder_days") or 0) for i in items] or [14])
        production = (f"Pesanan pre-order mulai diproduksi, estimasi {days} hari. " if lang == "id"
                      else f"Your pre-order goes into production now, about {days} days. ")
    values = {
        "name": order["contact_name"].split(" ")[0], "brand": s["brand_name"], "number": order["number"],
        "items": "\n".join(lines), "total": catalog.rupiah(order["total"]), "shipping": shipping,
        "grand": catalog.rupiah(order["total"] + (order["shipping_cost"] if order.get("shipping_set") else 0)),
        "city": (order.get("address") or {}).get("city", ""), "link": order_link(order),
        "bank": s.get(f"bank_info_{lang}") or s.get("bank_info_id") or "", "courier": order.get("shipping_courier") or "kurir",
        "tracking": order.get("tracking_number") or "-", "production": production,
    }
    out = []
    for key, tpl in WA_TEMPLATES.items():
        text = (custom.get(key) or {}).get(lang) or tpl[lang]
        try:
            msg = text.format(**values)
        except (KeyError, IndexError, ValueError):
            msg = tpl[lang].format(**values)
        out.append({"key": key, "label": tpl["label"], "text": msg, "url": util.wa_link(order["phone"], msg)})
    return out


@router.get("/orders")
async def orders(status: str = "", search: str = "", page: int = 1, user: User = Depends(admin)):
    parts = []
    if status == "open":
        parts.append("status != 'completed' && status != 'cancelled'")
    elif status in STATUSES:
        parts.append(f"status = {q(status)}")
    if search.strip():
        s = search.strip()[:60]
        parts.append(f"(number ~ {q(s)} || contact_name ~ {q(s)} || phone ~ {q(util.normalize_phone(s) or s)} || email ~ {q(s)})")
    data = await pb.list("shop_orders", filter=" && ".join(parts), sort="-created", page=max(1, page), per_page=50,
                         skip_total=False, fields="id,number,status,contact_name,phone,total,shipping_cost,shipping_set,"
                                                  "created,has_preorder,address,customer_note")
    return {"orders": data.get("items", []), "total": data.get("totalItems", 0), "page": data.get("page", 1),
            "pages": data.get("totalPages", 1)}


@router.get("/orders/{oid}")
async def order(oid: str, user: User = Depends(admin)):
    o = await pb.get("shop_orders", util.rid(oid))
    items = await pb.all("shop_order_items", filter=f"order = {q(oid)}", sort="created")
    customer = await pb.get("shop_customers", o["customer"]) if o.get("customer") else None
    history = []
    if o.get("phone"):
        history = (await pb.list("shop_orders", filter=f"phone = {q(o['phone'])} && id != {q(oid)}", sort="-created",
                                 per_page=10, fields="id,number,status,total,created")).get("items", [])
    return {"order": o, "items": items, "customer": customer, "history": history, "link": order_link(o),
            "wa": await wa_messages(o, items), "statuses": [{"id": s, "label": STATUS_LABEL[s]} for s in STATUSES]}


class OrderPatch(BaseModel):
    status: str | None = Field(default=None, max_length=30)
    shipping_cost: int | None = Field(default=None, ge=0, le=100_000_000)
    admin_note: str | None = Field(default=None, max_length=5000)
    shipping_courier: str | None = Field(default=None, max_length=60)
    tracking_number: str | None = Field(default=None, max_length=80)


async def restore_stock(order: dict):
    for it in await pb.all("shop_order_items", filter=f"order = {q(order['id'])} && preorder = false"):
        if it.get("variant"):
            try:
                await pb.update("shop_variants", it["variant"], {"stock+": int(it["qty"])})
            except Exception:  # noqa: BLE001 - variant may be gone
                pass


@router.patch("/orders/{oid}")
async def update_order(oid: str, body: OrderPatch, user: User = Depends(admin)):
    o = await pb.get("shop_orders", util.rid(oid))
    patch: dict = {}
    timeline = list(o.get("timeline") or [])
    now = util.pb_now()
    if body.status and body.status != o["status"]:
        if body.status not in STATUSES:
            raise HTTPException(400, "Unknown status.")
        if o["status"] == "cancelled":
            raise HTTPException(400, "This order was cancelled. Ask the customer to order again.")
        patch["status"] = body.status
        timeline.append({"at": now, "status": body.status, "by": user.username})
        if body.status == "cancelled":
            await restore_stock(o)
            timeline.append({"at": now, "note": "stock returned", "by": "system"})
    if body.shipping_cost is not None:
        patch["shipping_cost"], patch["shipping_set"] = body.shipping_cost, True
        timeline.append({"at": now, "note": f"shipping {catalog.rupiah(body.shipping_cost)}", "by": user.username})
    for k in ("admin_note", "shipping_courier", "tracking_number"):
        v = getattr(body, k)
        if v is not None:
            patch[k] = v.strip()
    if patch:
        patch["timeline"] = timeline[-200:]
        await pb.update("shop_orders", oid, patch)
    return await order(oid, user)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@router.get("/customers")
async def customers(search: str = "", page: int = 1, user: User = Depends(admin)):
    filt = ""
    if search.strip():
        s = search.strip()[:60]
        filt = f"(email ~ {q(s)} || name ~ {q(s)} || phone ~ {q(s)})"
    data = await pb.list("shop_customers", filter=filt, sort="-created", page=max(1, page), per_page=50, skip_total=False,
                         fields="id,email,name,phone,created,marketing_ok,birthday,anniversary,lang")
    return {"customers": data.get("items", []), "total": data.get("totalItems", 0), "pages": data.get("totalPages", 1)}


@router.get("/customers/{cid}")
async def customer(cid: str, user: User = Depends(admin)):
    c = await pb.get("shop_customers", util.rid(cid))
    family = await pb.all("shop_family_members", filter=f"customer = {q(cid)}", sort="sort")
    orders_ = (await pb.list("shop_orders", filter=f"customer = {q(cid)}", sort="-created", per_page=50,
                             fields="id,number,status,total,created")).get("items", [])
    vouchers = await pb.all("shop_vouchers", filter=f"customer = {q(cid)}", sort="-created")
    wish = await pb.all("shop_wishlist", filter=f"customer = {q(cid)}", expand="product",
                        fields="id,expand.product.name_id,expand.product.id")
    return {"customer": c, "family": family, "orders": orders_, "vouchers": vouchers,
            "wishlist": [(w.get("expand") or {}).get("product") for w in wish if w.get("expand")],
            "wa": util.wa_link(c["phone"]) if c.get("phone") else ""}


@router.post("/customers/{cid}/password")
async def reset_password(cid: str, user: User = Depends(admin)):
    """Set a new temporary password (no reset emails yet). Shown once; send it on WhatsApp."""
    temp = "-".join(secrets.token_hex(2) for _ in range(3))
    await pb.update("shop_customers", util.rid(cid), {"password": temp, "passwordConfirm": temp})
    return {"password": temp}


@router.delete("/customers/{cid}")
async def delete_customer(cid: str, user: User = Depends(admin)):
    """Data-deletion request (UU PDP): removes the account, family profiles and wishlist.
    Orders are kept for bookkeeping but unlinked from the account."""
    util.rid(cid)
    for o in await pb.all("shop_orders", filter=f"customer = {q(cid)}", fields="id"):
        await pb.update("shop_orders", o["id"], {"customer": ""})
    for r in await pb.all("shop_reviews", filter=f"customer = {q(cid)}", fields="id"):
        await pb.update("shop_reviews", r["id"], {"customer": ""})
    await pb.delete("shop_customers", cid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Reviews moderation
# ---------------------------------------------------------------------------

@router.get("/reviews")
async def reviews(status: str = "pending", user: User = Depends(admin)):
    filt = f"status = {q(status)}" if status in ("pending", "approved", "hidden") else ""
    items = (await pb.list("shop_reviews", filter=filt, sort="-created", per_page=100, expand="product",
                           fields="*,expand.product.name_id,expand.product.slug")).get("items", [])
    return {"reviews": items}


class ReviewPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|approved|hidden)$")
    reply: str | None = Field(default=None, max_length=2000)


@router.patch("/reviews/{rid_}")
async def moderate(rid_: str, body: ReviewPatch, user: User = Depends(admin)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return await pb.update("shop_reviews", util.rid(rid_), data)


@router.delete("/reviews/{rid_}")
async def delete_review(rid_: str, user: User = Depends(admin)):
    await pb.delete("shop_reviews", util.rid(rid_))
    return {"ok": True}
