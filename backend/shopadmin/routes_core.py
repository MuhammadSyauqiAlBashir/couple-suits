"""Admin API: dashboard, settings, admins, push notifications, passkeys (Face ID lock), AI copywriting."""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from webauthn import (generate_authentication_options, generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement, UserVerificationRequirement)

from cs import ai, catalog, config, media, util
from cs.pb import pb, q

from . import notify
from .security import User, _locks, admin, revoke, signed_in

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def dashboard(days: int = 30, user: User = Depends(admin)):
    days = max(7, min(365, days))
    today = util.now_local().date()
    start = (today - timedelta(days=days - 1)).isoformat()
    rows = await pb.all("shop_stats", filter=f"day >= {q(start)}", fields="day,metric,dim,count")
    series: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    dims: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        series[r["metric"]][r["day"]] += int(r["count"] or 0)
        if r.get("dim"):
            dims[r["metric"]][r["dim"]] += int(r["count"] or 0)
    day_list = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]

    def s(metric: str) -> list[int]:
        return [series[metric].get(d, 0) for d in day_list]

    products = {p["id"]: p for p in await pb.all("shop_products", fields="id,name_id,slug,media,status")}

    def top(metric: str, n: int = 8) -> list[dict]:
        return [{"id": pid, "name": products[pid]["name_id"], "image": (products[pid].get("media") or [""])[0], "count": c}
                for pid, c in dims[metric].most_common(n * 2) if pid in products][:n]

    open_orders = await pb.list("shop_orders", filter="status != 'completed' && status != 'cancelled'", per_page=1,
                                skip_total=False)
    new_orders = await pb.list("shop_orders", filter="status = 'new'", per_page=1, skip_total=False)
    pending_reviews = await pb.list("shop_reviews", filter="status = 'pending'", per_page=1, skip_total=False)
    low = await pb.all("shop_variants", filter="active = true && stock <= 2 && product.stock_mode = 'ready' && product.status = 'live'",
                       expand="product", fields="id,cut,size,color,stock,expand.product.name_id,expand.product.id")
    visitors, orders = sum(s("visitors")), sum(s("orders"))
    return {
        "days": day_list, "visitors": s("visitors"), "pageviews": s("pageviews"), "orders": s("orders"),
        "revenue": s("revenue"), "add_to_cart": s("add_to_cart"), "checkout_view": s("checkout_view"),
        "totals": {"visitors": visitors, "orders": orders, "revenue": sum(s("revenue")),
                   "add_to_cart": sum(s("add_to_cart")), "checkout_view": sum(s("checkout_view")),
                   "conversion": round(orders / visitors * 100, 2) if visitors else 0,
                   "wa_click": sum(s("wa_click")), "registrations": sum(s("registrations"))},
        "top_viewed": top("product_views"), "top_sold": top("sold"),
        "sources": dims["sources"].most_common(8), "devices": dims["devices"].most_common(3),
        "searches": dims["searches"].most_common(10), "pages": dims["pages"].most_common(10),
        "counts": {"open_orders": open_orders.get("totalItems", 0), "new_orders": new_orders.get("totalItems", 0),
                   "pending_reviews": pending_reviews.get("totalItems", 0), "low_stock": len(low)},
        "low_stock": [{"product": (v.get("expand") or {}).get("product", {}).get("name_id", ""),
                       "product_id": (v.get("expand") or {}).get("product", {}).get("id", ""),
                       "cut": v["cut"], "size": v["size"], "color": v.get("color", ""), "stock": v["stock"]}
                      for v in low[:30]],
    }


# ---------------------------------------------------------------------------
# Settings + admins
# ---------------------------------------------------------------------------

SETTING_KEYS = {k for k in util.DEFAULT_SETTINGS} | {"bank_info_id", "bank_info_en", "image_engine"}


@router.get("/settings")
async def get_settings(user: User = Depends(admin)):
    s = await util.settings(fresh=True)
    admins = await pb.all("shop_admins", fields="id,user,username")
    return {"settings": s, "admin_usernames": await pb.kv_get("admin_usernames", []) or [], "admins": admins,
            "flux": bool(config.CF_ACCOUNT_ID), "gemini": bool(config.GEMINI_API_KEY),
            "demo": bool(await pb.kv_get("demo_catalog", False))}


@router.put("/settings")
async def put_settings(body: dict, user: User = Depends(admin)):
    stored = await pb.kv_get("settings", {}) or {}
    for k, v in body.items():
        if k not in SETTING_KEYS:
            continue
        if k == "whatsapp":
            v = util.normalize_phone(str(v))
            if v and not util.valid_phone(v):
                raise HTTPException(400, "That WhatsApp number isn't valid.")
        if k == "accent" and v and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(v)):
            raise HTTPException(400, "Accent colour must look like #1c1b19.")
        if k in ("special_voucher_percent", "special_voucher_days"):
            v = max(0, min(90 if k.endswith("percent") else 90, int(v or 0)))
        if k == "wa_templates" and not isinstance(v, dict):
            continue
        if isinstance(v, str):
            v = v.strip()[:3000]
        stored[k] = v
    await pb.kv_set("settings", stored)
    util.forget_settings()
    return {"settings": await util.settings(fresh=True)}


class AdminIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)


@router.post("/admins")
async def add_admin(body: AdminIn, user: User = Depends(admin)):
    names = await pb.kv_get("admin_usernames", []) or []
    name = body.username.strip().lower()
    if name not in names:
        names.append(name)
    await pb.kv_set("admin_usernames", names)
    return {"admin_usernames": names}


@router.delete("/admins/{username}")
async def remove_admin(username: str, user: User = Depends(admin)):
    name = username.strip().lower()
    if name == user.username.lower():
        raise HTTPException(400, "You can't remove yourself.")
    names = [n for n in (await pb.kv_get("admin_usernames", []) or []) if n != name]
    await pb.kv_set("admin_usernames", names)
    for row in await pb.all("shop_admins", filter=f"username = {q(name)}"):
        await pb.delete("shop_admins", row["id"])
        revoke(row["user"])
    return {"admin_usernames": names}


# ---------------------------------------------------------------------------
# Push notifications
# ---------------------------------------------------------------------------

class SubIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=5, max_length=100)
    ua: str = Field(default="", max_length=300)


@router.get("/push/key")
async def push_key(user: User = Depends(admin)):
    return {"key": notify.public_key()}


@router.post("/push/subscribe")
async def push_subscribe(body: SubIn, user: User = Depends(admin)):
    if not body.endpoint.startswith("https://"):
        raise HTTPException(400, "Bad endpoint.")
    existing = await pb.first("shop_push_subs", f"endpoint = {q(body.endpoint)}")
    data = {**body.model_dump(), "user": user.id}
    if existing:
        await pb.update("shop_push_subs", existing["id"], data)
    else:
        await pb.create("shop_push_subs", data)
    return {"ok": True}


@router.post("/push/test")
async def push_test(user: User = Depends(admin)):
    n = await notify.send("Notifikasi aktif 🎉", "Kamu akan dapat kabar pesanan baru di sini.", "/", tag="test", users=[user.id])
    return {"sent": n}


# ---------------------------------------------------------------------------
# Passkeys (Face ID lock)
# ---------------------------------------------------------------------------

async def user_passkeys(user_id: str) -> list[dict]:
    return await pb.all("shop_passkeys", filter=f"user = {q(user_id)}")


@router.get("/passkeys")
async def list_passkeys(user: User = Depends(admin)):
    return {"passkeys": [{"id": p["id"], "name": p.get("name"), "created": p["created"]} for p in await user_passkeys(user.id)]}


@router.post("/passkey/register/options")
async def passkey_register_options(user: User = Depends(admin)):
    existing = await user_passkeys(user.id)
    opts = generate_registration_options(
        rp_id=config.RP_ID, rp_name="Shop Admin", user_name=user.username, user_id=user.id.encode(),
        user_display_name=user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.PREFERRED,
                                                               user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["cred_id"])) for p in existing])
    _locks[user.sid].challenge = opts.challenge
    return json.loads(options_to_json(opts))


class CredentialIn(BaseModel):
    credential: dict
    name: str = Field(default="", max_length=100)


@router.post("/passkey/register/verify")
async def passkey_register_verify(body: CredentialIn, user: User = Depends(admin)):
    st = _locks[user.sid]
    if not st.challenge:
        raise HTTPException(400, "Start again.")
    try:
        v = verify_registration_response(credential=body.credential, expected_challenge=st.challenge,
                                         expected_rp_id=config.RP_ID, expected_origin=config.ADMIN_URL,
                                         require_user_verification=True)
    except InvalidRegistrationResponse as e:
        raise HTTPException(400, f"Face ID setup failed: {e}")
    finally:
        st.challenge = b""
    await pb.create("shop_passkeys", {"user": user.id, "cred_id": bytes_to_base64url(v.credential_id),
                                      "public_key": bytes_to_base64url(v.credential_public_key),
                                      "sign_count": v.sign_count, "name": body.name or "iPhone"})
    st.unlocked, st.last_seen = True, time.monotonic()
    return {"ok": True}


@router.delete("/passkeys/{pid}")
async def delete_passkey(pid: str, user: User = Depends(admin)):
    rec = await pb.get("shop_passkeys", util.rid(pid))
    if rec["user"] != user.id:
        raise HTTPException(404, "Not found.")
    await pb.delete("shop_passkeys", pid)
    return {"ok": True}


@router.post("/passkey/auth/options")
async def passkey_auth_options(user: User = Depends(signed_in)):
    keys = await user_passkeys(user.id)
    if not keys:
        raise HTTPException(400, "No Face ID set up for this account.")
    opts = generate_authentication_options(
        rp_id=config.RP_ID, user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["cred_id"])) for p in keys])
    _locks[user.sid].challenge = opts.challenge
    return json.loads(options_to_json(opts))


@router.post("/passkey/auth/verify")
async def passkey_auth_verify(body: CredentialIn, user: User = Depends(signed_in)):
    st = _locks[user.sid]
    if not st.challenge:
        raise HTTPException(400, "Start again.")
    cred_id = str(body.credential.get("id", ""))
    rec = await pb.first("shop_passkeys", f"cred_id = {q(cred_id)} && user = {q(user.id)}")
    if not rec:
        st.challenge = b""
        raise HTTPException(400, "Unknown passkey.")
    try:
        v = verify_authentication_response(
            credential=body.credential, expected_challenge=st.challenge, expected_rp_id=config.RP_ID,
            expected_origin=config.ADMIN_URL, credential_public_key=base64url_to_bytes(rec["public_key"]),
            credential_current_sign_count=int(rec.get("sign_count") or 0), require_user_verification=True)
    except InvalidAuthenticationResponse as e:
        raise HTTPException(400, f"Face ID check failed: {e}")
    finally:
        st.challenge = b""
    await pb.update("shop_passkeys", rec["id"], {"sign_count": v.new_sign_count})
    st.unlocked, st.last_seen = True, time.monotonic()
    return {"ok": True}


@router.post("/lock")
async def lock_now(user: User = Depends(signed_in)):
    if await user_passkeys(user.id):
        _locks[user.sid].unlocked = False
    return {"ok": True}


# ---------------------------------------------------------------------------
# AI copywriting (free Gemini): product texts, translations
# ---------------------------------------------------------------------------

def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "propertyOrdering": list(props)}


S = {"type": "string"}
COPY_SCHEMA = _obj({
    "name_id": S, "name_en": S, "summary_id": S, "summary_en": S, "description_id": S, "description_en": S,
    "material_id": S, "material_en": S, "care_id": S, "care_en": S, "tags": {"type": "array", "items": S},
    "seo_title": S, "seo_description": S,
})

COPY_SYSTEM = """You write product copy for a minimal, premium Indonesian clothing shop that sells matching outfits
for couples and whole families (dad, mum, kids, babies, grandparents). Tone: warm, calm, elegant, never pushy,
no exclamation marks, no emoji. Write natural Bahasa Indonesia (not a literal translation) and natural English.
Descriptions: 1 short paragraph + 3–5 markdown bullet points (fit, fabric feel, occasions, which family roles it
comes in). Material: fabric and weight/feel. Care: short washing instructions. Tags: 3–6 lowercase single words.
SEO title ≤ 60 characters, SEO description ≤ 155 characters (Indonesian). Never invent certifications or claims
you weren't given."""


class CopyIn(BaseModel):
    notes: str = Field(default="", max_length=3000)
    name: str = Field(default="", max_length=200)
    cuts: list[str] = Field(default_factory=list, max_length=10)
    image: str = Field(default="", max_length=40)


@router.post("/ai/product-copy")
async def product_copy(body: CopyIn, user: User = Depends(admin)):
    cuts = ", ".join(catalog.CUTS[c]["en"] for c in body.cuts if c in catalog.CUTS)
    parts: list = [f"Product name idea: {body.name or '(suggest one)'}\nAvailable cuts: {cuts or 'unknown'}\n"
                   f"Notes from the owner:\n{body.notes or '(none)'}"]
    if body.image and body.image.isalnum():
        try:
            with open(media.path_for(body.image, 800), "rb") as f:
                parts.append(ai.image_part(f.read(), "image/webp"))
            parts.append("The photo shows the product; describe what you can actually see.")
        except OSError:
            pass
    try:
        return await ai.generate(parts, system=COPY_SYSTEM, schema=COPY_SCHEMA, smart=True)
    except ai.AIUnavailable as e:
        raise HTTPException(503, f"AI is busy right now, try again in a minute. ({str(e)[:120]})")


class TranslateIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    to: str = Field(pattern="^(id|en)$")


@router.post("/ai/translate")
async def translate(body: TranslateIn, user: User = Depends(admin)):
    lang = "natural Bahasa Indonesia" if body.to == "id" else "natural English"
    try:
        text = await ai.generate([f"Translate into {lang}. Keep markdown formatting, line breaks and tone. "
                                  f"Return only the translation.\n\n{body.text}"])
    except ai.AIUnavailable as e:
        raise HTTPException(503, f"AI is busy right now, try again in a minute. ({str(e)[:120]})")
    return {"text": text.strip()}


_ = (datetime,)
