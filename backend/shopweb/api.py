"""JSON endpoints used by the storefront scripts (header X-CS: 1 required for writes)."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from cs import pricing, util
from cs.pb import PBError, pb, q

from . import i18n, orders, stats, store
from .render import lang_of

router = APIRouter(prefix="/api")
order_limit = util.Window(8, 3600)
quote_limit = util.Window(120, 600)


class LineIn(BaseModel):
    product: str = Field(max_length=20)
    cut: str = Field(max_length=20)
    size: str = Field(max_length=20)
    color: str = Field(default="", max_length=40)
    qty: int = Field(default=1, ge=1, le=20)
    role: str = Field(default="", max_length=40)
    member: str = Field(default="", max_length=80)
    set_key: str = Field(default="", max_length=40)


class QuoteIn(BaseModel):
    lines: list[LineIn] = Field(max_length=pricing.MAX_LINES)
    voucher: str = Field(default="", max_length=40)
    phone: str = Field(default="", max_length=30)


def ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.post("/quote")
async def quote(body: QuoteIn, request: Request):
    quote_limit.check(ip(request))
    c = request.state.customer
    res = await pricing.quote([ln.model_dump() for ln in body.lines], lang=lang_of(request), voucher_code=body.voucher,
                              customer_id=c["id"] if c else "", phone=util.normalize_phone(body.phone))
    return res.as_dict()


class AddressIn(BaseModel):
    street: str = Field(min_length=5, max_length=500)
    city: str = Field(min_length=2, max_length=100)
    province: str = Field(default="", max_length=100)
    postal: str = Field(default="", max_length=10)


class OrderIn(BaseModel):
    lines: list[LineIn] = Field(min_length=1, max_length=pricing.MAX_LINES)
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=30)
    email: str = Field(default="", max_length=200)
    address: AddressIn
    note: str = Field(default="", max_length=2000)
    voucher: str = Field(default="", max_length=40)
    save: bool = False
    website: str = Field(default="", max_length=200)  # honeypot


@router.post("/orders")
async def place_order(body: OrderIn, request: Request):
    lang = lang_of(request)
    order_limit.check(ip(request), "Too many orders from this network.")
    if body.website:
        raise HTTPException(400, "Blocked.")
    phone = util.normalize_phone(body.phone)
    if not util.valid_phone(phone):
        raise HTTPException(400, i18n.t("co.bad_phone", lang))
    email = body.email.strip().lower()
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", email, re.I):
        raise HTTPException(400, "Email?")
    customer = request.state.customer
    order = await orders.place(
        lines=[ln.model_dump() for ln in body.lines],
        contact={"name": body.name.strip(), "phone": phone, "email": email or (customer or {}).get("email", "")},
        address={k: v.strip() for k, v in body.address.model_dump().items()}, note=body.note.strip(),
        voucher=body.voucher.strip(), lang=lang, customer=customer)
    if customer and body.save:
        patch = {}
        if not customer.get("phone"):
            patch["phone"] = phone
        if not customer.get("name"):
            patch["name"] = body.name.strip()
        if patch:
            try:
                await pb.update("shop_customers", customer["id"], patch)
            except PBError:
                pass
    return {"number": order["number"], "token": order["token"],
            "url": f"/order/{order['number']}?t={order['token']}&new=1"}


@router.get("/cards")
async def cards(request: Request, ids: str = ""):
    wanted = [i for i in ids.split(",") if util.PB_ID.match(i)][:48]
    return {"cards": store.cards(store.for_ids(wanted), lang_of(request))}


@router.get("/recs")
async def recs(request: Request, ids: str = ""):
    """Picks based on recently viewed products (sent by the browser)."""
    seen = [i for i in ids.split(",") if util.PB_ID.match(i)][:12]
    out: list[dict] = []
    for pid in seen:
        for p in store.recommendations(pid, 4):
            if p["id"] not in seen and p not in out:
                out.append(p)
    return {"cards": store.cards(out[:8], lang_of(request))}


# ---------------------------------------------------------------------------
# Wishlist (server copy for logged-in customers; guests keep it in the browser)
# ---------------------------------------------------------------------------

@router.get("/wishlist")
async def wishlist(request: Request):
    c = request.state.customer
    if not c:
        return {"ids": [], "customer": False}
    items = await pb.all("shop_wishlist", filter=f"customer = {q(c['id'])}", fields="product", sort="-created")
    return {"ids": [i["product"] for i in items], "customer": True}


class WishIn(BaseModel):
    product: str = Field(max_length=20)
    on: bool = True


class WishMerge(BaseModel):
    ids: list[str] = Field(max_length=200)


@router.post("/wishlist")
async def wish(body: WishIn, request: Request):
    c = request.state.customer
    if not c:
        return {"ok": True, "customer": False}
    pid = util.rid(body.product)
    existing = await pb.first("shop_wishlist", f"customer = {q(c['id'])} && product = {q(pid)}")
    if body.on and not existing and pid in store.C.by_id:
        await pb.create("shop_wishlist", {"customer": c["id"], "product": pid})
        stats.add("wishlist_adds", pid)
    elif not body.on and existing:
        await pb.delete("shop_wishlist", existing["id"])
    return {"ok": True, "customer": True}


@router.post("/wishlist/merge")
async def wish_merge(body: WishMerge, request: Request):
    c = request.state.customer
    if not c:
        return {"ids": body.ids}
    have = {i["product"] for i in await pb.all("shop_wishlist", filter=f"customer = {q(c['id'])}", fields="product")}
    for pid in body.ids:
        if util.PB_ID.match(pid) and pid not in have and pid in store.C.by_id:
            try:
                await pb.create("shop_wishlist", {"customer": c["id"], "product": pid})
                have.add(pid)
            except PBError:
                pass
    return {"ids": sorted(have)}


# ---------------------------------------------------------------------------
# Analytics events from the browser
# ---------------------------------------------------------------------------

EVENTS = {"add_to_cart", "checkout_view", "wa_click", "set_built", "install"}


class EventIn(BaseModel):
    e: str = Field(max_length=30)
    p: str = Field(default="", max_length=20)
    n: int = Field(default=1, ge=1, le=20)


ev_limit = util.Window(300, 600)


@router.post("/ev")
async def event(body: EventIn, request: Request):
    ok, _ = ev_limit.allow(ip(request))
    if ok and body.e in EVENTS:
        stats.add(body.e, body.p if util.PB_ID.match(body.p or "") else "", body.n)
    return {"ok": True}
