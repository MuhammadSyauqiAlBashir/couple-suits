"""Cart pricing. The server always re-prices from the database; client prices are
never trusted. Used by the storefront (quote + order) and the CMS (order view)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import catalog
from .pb import pb, q

MAX_LINES = 60
MAX_QTY = 20


@dataclass
class Line:
    product: str
    cut: str
    size: str
    color: str = ""
    qty: int = 1
    role: str = ""
    member: str = ""
    set_key: str = ""
    idx: int = 0


@dataclass
class Quote:
    lines: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    bad: list[int] = field(default_factory=list)
    items_total: int = 0
    set_discount: int = 0
    voucher_discount: int = 0
    voucher: dict | None = None
    voucher_error: str = ""
    discounts: list[dict] = field(default_factory=list)
    has_preorder: bool = False

    @property
    def discount_total(self) -> int:
        return self.set_discount + self.voucher_discount

    @property
    def total(self) -> int:
        return max(0, self.items_total - self.discount_total)

    def as_dict(self) -> dict:
        return {"lines": self.lines, "errors": self.errors, "bad": self.bad, "items_total": self.items_total,
                "set_discount": self.set_discount, "voucher_discount": self.voucher_discount,
                "discount_total": self.discount_total, "total": self.total, "discounts": self.discounts,
                "voucher": ({"code": self.voucher["code"], "kind": self.voucher["kind"], "value": self.voucher["value"]}
                            if self.voucher else None),
                "voucher_error": self.voucher_error, "has_preorder": self.has_preorder}


MSG = {
    "id": {
        "unavailable": "{name} sudah tidak tersedia.", "cut": "{name}: potongan {cut} tidak tersedia.",
        "size": "{name}: ukuran {size} tidak tersedia.", "stock": "{name} ({cut} {size}): stok tersisa {n}.",
        "v_unknown": "Kode voucher tidak dikenal.", "v_expired": "Voucher sudah tidak berlaku.",
        "v_min": "Voucher berlaku untuk belanja minimal {min}.", "v_used": "Voucher sudah habis dipakai.",
        "v_mine": "Voucher ini khusus untuk akun lain.", "v_once": "Kamu sudah memakai voucher ini.",
        "set": "Diskon set keluarga ({n} orang)",
    },
    "en": {
        "unavailable": "{name} is no longer available.", "cut": "{name}: the {cut} cut isn't available.",
        "size": "{name}: size {size} isn't available.", "stock": "{name} ({cut} {size}): only {n} left.",
        "v_unknown": "Unknown voucher code.", "v_expired": "This voucher isn't valid right now.",
        "v_min": "This voucher needs a minimum purchase of {min}.", "v_used": "This voucher has been fully used.",
        "v_mine": "This voucher belongs to another account.", "v_once": "You've already used this voucher.",
        "set": "Family set discount ({n} people)",
    },
}


def m(lang: str, key: str, **kw) -> str:
    return MSG.get(lang, MSG["id"])[key].format(**kw)


async def load_products(ids: set[str]) -> dict[str, dict]:
    if not ids:
        return {}
    items = await pb.all("shop_products", filter=" || ".join(f"id = {q(i)}" for i in ids))
    return {p["id"]: p for p in items}


async def load_variants(product_ids: set[str]) -> dict[tuple, dict]:
    if not product_ids:
        return {}
    items = await pb.all("shop_variants", filter=" || ".join(f"product = {q(i)}" for i in product_ids))
    return {(v["product"], v["cut"], v["size"], v.get("color") or ""): v for v in items}


async def voucher_check(code: str, subtotal: int, customer_id: str, phone: str, lang: str) -> tuple[dict | None, str]:
    code = (code or "").strip().upper()
    if not code:
        return None, ""
    v = await pb.first("shop_vouchers", f"code = {q(code)}")
    if not v or not v.get("active"):
        return None, m(lang, "v_unknown")
    now = catalog.now_utc()
    starts, ends = catalog.parse_pb_date(v.get("starts")), catalog.parse_pb_date(v.get("ends"))
    if (starts and now < starts) or (ends and now > ends):
        return None, m(lang, "v_expired")
    if v.get("customer") and v["customer"] != customer_id:
        return None, m(lang, "v_mine")
    if int(v.get("min_spend") or 0) > subtotal:
        return None, m(lang, "v_min", min=catalog.rupiah(v["min_spend"]))
    uses = await pb.all("shop_voucher_uses", filter=f"voucher = {q(v['id'])}", fields="id,customer,phone")
    if v.get("usage_limit") and len(uses) >= int(v["usage_limit"]):
        return None, m(lang, "v_used")
    per = int(v.get("per_customer_limit") or 0)
    if per:
        mine = [u for u in uses if (customer_id and u.get("customer") == customer_id) or (phone and u.get("phone") == phone)]
        if len(mine) >= per:
            return None, m(lang, "v_once")
    return v, ""


async def quote(raw_lines: list[dict], *, lang: str = "id", voucher_code: str = "", customer_id: str = "",
                phone: str = "") -> Quote:
    out = Quote()
    lines = []
    for i, r in enumerate(raw_lines[:MAX_LINES]):
        try:
            lines.append(Line(idx=i, product=str(r["product"])[:20], cut=str(r["cut"]), size=str(r["size"])[:20],
                              color=str(r.get("color") or "")[:40], qty=max(1, min(MAX_QTY, int(r.get("qty") or 1))),
                              role=str(r.get("role") or "")[:40], member=str(r.get("member") or "")[:80],
                              set_key=str(r.get("set_key") or "")[:40]))
        except (KeyError, TypeError, ValueError):
            continue
    products = await load_products({ln.product for ln in lines})
    variants = await load_variants(set(products))
    stock_used: dict[str, int] = defaultdict(int)

    for ln in lines:
        p = products.get(ln.product)
        name = catalog.tr(p, "name", lang) if p else "?"
        if not p or p.get("status") != "live":
            out.errors.append(m(lang, "unavailable", name=name))
            out.bad.append(ln.idx)
            continue
        cut_name = catalog.label(catalog.CUTS, ln.cut, lang)
        if ln.cut not in (p.get("cuts") or []):
            out.errors.append(m(lang, "cut", name=name, cut=cut_name))
            out.bad.append(ln.idx)
            continue
        v = variants.get((p["id"], ln.cut, ln.size, ln.color)) or variants.get((p["id"], ln.cut, ln.size, ""))
        if not v or not v.get("active"):
            out.errors.append(m(lang, "size", name=name, size=catalog.size_label(ln.size, lang)))
            out.bad.append(ln.idx)
            continue
        preorder = p.get("stock_mode") == "preorder"
        if not preorder:
            stock_used[v["id"]] += ln.qty
            if stock_used[v["id"]] > int(v.get("stock") or 0):
                out.errors.append(m(lang, "stock", name=name, cut=cut_name, size=catalog.size_label(ln.size, lang),
                                    n=max(0, int(v.get("stock") or 0))))
                out.bad.append(ln.idx)
                continue
        regular, price = catalog.cut_price(p, ln.cut)
        media = p.get("media") or []
        color = next((c for c in (p.get("colors") or []) if c.get("key") == ln.color), None)
        color_label = (color.get(f"name_{lang}") or color.get("name_id") or ln.color) if color else ln.color
        if color and color.get("media"):
            media = color["media"] + media
        out.lines.append({
            "idx": ln.idx, "product": p["id"], "slug": p["slug"], "name": name, "variant": v["id"], "cut": ln.cut, "cut_label": cut_name,
            "size": ln.size, "size_label": catalog.size_label(ln.size, lang), "color": ln.color,
            "color_label": color_label, "qty": ln.qty,
            "role": ln.role, "role_label": catalog.label(catalog.ROLES, ln.role, lang) if ln.role in catalog.ROLES else ln.role,
            "member": ln.member, "set_key": ln.set_key, "regular": regular, "price": price, "line_total": price * ln.qty,
            "image": media[0] if media else "", "preorder": preorder, "preorder_days": int(p.get("preorder_days") or 0),
        })
        out.has_preorder = out.has_preorder or preorder
    out.items_total = sum(ln["line_total"] for ln in out.lines)

    # Family-set discount: per set (one "build your set" add), by number of people.
    rules = sorted((r for r in await pb.all("shop_set_discounts", filter="active = true")),
                   key=lambda r: -int(r["min_members"]))
    sets: dict[str, list[dict]] = defaultdict(list)
    for ln in out.lines:
        if ln["set_key"]:
            sets[ln["set_key"]].append(ln)
    for key, members in sets.items():
        count = sum(ln["qty"] for ln in members)
        rule = next((r for r in rules if count >= int(r["min_members"])), None)
        if rule:
            amount = catalog.round_price(sum(ln["line_total"] for ln in members) * int(rule["percent"]) / 100)
            if amount:
                out.set_discount += amount
                out.discounts.append({"kind": "set", "set_key": key, "percent": int(rule["percent"]), "amount": amount,
                                      "label": catalog.tr(rule, "label", lang) or m(lang, "set", n=count)})

    # Voucher on what's left.
    subtotal = out.items_total - out.set_discount
    if voucher_code:
        v, err = await voucher_check(voucher_code, subtotal, customer_id, phone, lang)
        out.voucher_error = err
        if v:
            if v["kind"] == "percent":
                amount = catalog.round_price(subtotal * int(v["value"]) / 100)
                if int(v.get("max_discount") or 0):
                    amount = min(amount, int(v["max_discount"]))
            else:
                amount = int(v["value"])
            amount = max(0, min(amount, subtotal))
            out.voucher, out.voucher_discount = v, amount
            out.discounts.append({"kind": "voucher", "code": v["code"], "amount": amount,
                                  "label": catalog.tr(v, "label", lang) or v["code"]})
    return out
