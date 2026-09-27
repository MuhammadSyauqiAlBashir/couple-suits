"""Admin API: products, variants (stock), media uploads, demo catalog removal."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from cs import catalog, media, util
from cs.pb import PBError, pb, q

from .security import User, admin

router = APIRouter(prefix="/api")

PRODUCT_FIELDS = {
    "slug", "name_id", "name_en", "summary_id", "summary_en", "description_id", "description_en", "material_id",
    "material_en", "care_id", "care_en", "category", "collections", "tags", "status", "stock_mode", "preorder_days",
    "cuts", "cut_prices", "colors", "media", "size_charts", "sale_percent", "sale_start", "sale_end", "featured",
    "sort", "seo_title", "seo_description", "design_id",
}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def clean_product(data: dict) -> dict:
    out = {k: v for k, v in data.items() if k in PRODUCT_FIELDS}
    if "slug" in out:
        out["slug"] = util.slugify(str(out["slug"]), 120)
    if "cuts" in out:
        out["cuts"] = [c for c in out["cuts"] or [] if c in catalog.CUTS]
    if "cut_prices" in out:
        out["cut_prices"] = {c: max(0, int(p or 0)) for c, p in (out["cut_prices"] or {}).items() if c in catalog.CUTS}
    if "colors" in out:
        colors = []
        for c in out["colors"] or []:
            key = util.slugify(str(c.get("key") or c.get("name_id") or ""), 40)
            hex_ = str(c.get("hex") or "")
            colors.append({"key": key, "name_id": str(c.get("name_id") or "")[:60], "name_en": str(c.get("name_en") or "")[:60],
                           "hex": hex_ if HEX.match(hex_) else "#cccccc",
                           "media": [m for m in (c.get("media") or []) if str(m).isalnum()][:10]})
        out["colors"] = colors
    if "media" in out:
        out["media"] = [m for m in out["media"] or [] if str(m).isalnum()][:30]
    if "tags" in out:
        out["tags"] = [util.slugify(str(t), 30) for t in out["tags"] or [] if str(t).strip()][:20]
    for k in ("sale_start", "sale_end"):
        if k in out and out[k] and not re.match(r"^\d{4}-\d{2}-\d{2}", str(out[k])):
            out[k] = ""
    return out


@router.get("/products")
async def products(status: str = "", q_: str = "", user: User = Depends(admin)):
    filt = f"status = {q(status)}" if status in ("draft", "live", "archived") else ""
    items = await pb.all("shop_products", filter=filt, sort="sort,-created",
                         fields="id,slug,name_id,name_en,status,stock_mode,media,cuts,cut_prices,featured,sort,demo,"
                                "sale_percent,sale_end,category,updated,preorder_days")
    stock: dict[str, int] = {}
    for v in await pb.all("shop_variants", filter="active = true", fields="product,stock"):
        stock[v["product"]] = stock.get(v["product"], 0) + int(v.get("stock") or 0)
    for p in items:
        p["stock"] = stock.get(p["id"], 0)
        lo, hi, _, _ = catalog.price_range(p)
        p["price_min"], p["price_max"] = lo, hi
    return {"products": items}


@router.get("/products/{pid}")
async def product(pid: str, user: User = Depends(admin)):
    p = await pb.get("shop_products", util.rid(pid))
    variants = await pb.all("shop_variants", filter=f"product = {q(pid)}", sort="cut,size")
    return {"product": p, "variants": variants}


@router.post("/products")
async def create_product(body: dict, user: User = Depends(admin)):
    data = clean_product(body)
    data.setdefault("name_id", "Produk baru")
    data["slug"] = await free_slug(data.get("slug") or util.slugify(data["name_id"]))
    data.setdefault("status", "draft")
    data.setdefault("stock_mode", "ready")
    for k, v in (("cuts", []), ("cut_prices", {}), ("colors", []), ("media", []), ("size_charts", []), ("tags", [])):
        data.setdefault(k, v)
    rec = await pb.create("shop_products", data)
    return {"product": rec}


async def free_slug(slug: str, exclude: str = "") -> str:
    base, n = slug or util.new_key(6), 1
    while True:
        other = await pb.first("shop_products", f"slug = {q(slug)}")
        if not other or other["id"] == exclude:
            return slug
        n += 1
        slug = f"{base}-{n}"


@router.patch("/products/{pid}")
async def update_product(pid: str, body: dict, user: User = Depends(admin)):
    util.rid(pid)
    data = clean_product(body)
    if "slug" in data:
        data["slug"] = await free_slug(data["slug"], exclude=pid)
    if data.get("status") == "live":
        cur = {**await pb.get("shop_products", pid), **data}
        if not cur.get("cuts"):
            raise HTTPException(400, "Add at least one cut (men, women, kids…) before publishing.")
        if any(not int((cur.get("cut_prices") or {}).get(c) or 0) for c in cur["cuts"]):
            raise HTTPException(400, "Every cut needs a price before publishing.")
        if not await pb.first("shop_variants", f"product = {q(pid)} && active = true"):
            raise HTTPException(400, "Set up sizes (and stock) before publishing.")
    rec = await pb.update("shop_products", pid, data)
    return {"product": rec}


@router.post("/products/{pid}/duplicate")
async def duplicate(pid: str, user: User = Depends(admin)):
    p = await pb.get("shop_products", util.rid(pid))
    data = {k: v for k, v in p.items() if k in PRODUCT_FIELDS}
    data.update({"slug": await free_slug(p["slug"] + "-copy"), "name_id": p["name_id"] + " (salinan)",
                 "name_en": (p.get("name_en") or "") + " (copy)", "status": "draft", "demo": False})
    rec = await pb.create("shop_products", data)
    for v in await pb.all("shop_variants", filter=f"product = {q(pid)}"):
        await pb.create("shop_variants", {"product": rec["id"], "cut": v["cut"], "size": v["size"], "color": v.get("color", ""),
                                          "stock": 0, "sku": "", "active": v.get("active", True)})
    return {"product": rec}


@router.delete("/products/{pid}")
async def delete_product(pid: str, user: User = Depends(admin)):
    util.rid(pid)
    if await pb.first("shop_order_items", f"product = {q(pid)}"):
        await pb.update("shop_products", pid, {"status": "archived"})
        return {"archived": True}
    await pb.delete("shop_products", pid)
    return {"deleted": True}


class VariantIn(BaseModel):
    cut: str = Field(max_length=20)
    size: str = Field(max_length=20)
    color: str = Field(default="", max_length=40)
    stock: int = Field(default=0, ge=0, le=100000)
    sku: str = Field(default="", max_length=60)
    active: bool = True


class VariantsIn(BaseModel):
    variants: list[VariantIn] = Field(max_length=2000)


@router.put("/products/{pid}/variants")
async def put_variants(pid: str, body: VariantsIn, user: User = Depends(admin)):
    """Make the product's variants match the grid: create, update, and remove (deactivate if ordered)."""
    util.rid(pid)
    existing = {(v["cut"], v["size"], v.get("color") or ""): v for v in await pb.all("shop_variants", filter=f"product = {q(pid)}")}
    wanted = {}
    for v in body.variants:
        if v.cut not in catalog.CUTS or v.size not in catalog.sizes_for_cut(v.cut):
            continue
        wanted[(v.cut, v.size, util.slugify(v.color, 40) if v.color else "")] = v
    for key, v in wanted.items():
        cur = existing.get(key)
        data = {"stock": v.stock, "sku": v.sku, "active": v.active}
        if cur:
            if any(cur.get(k) != data[k] for k in data):
                await pb.update("shop_variants", cur["id"], data)
        else:
            await pb.create("shop_variants", {"product": pid, "cut": key[0], "size": key[1], "color": key[2], **data})
    for key, cur in existing.items():
        if key not in wanted:
            try:
                if await pb.first("shop_order_items", f"variant = {q(cur['id'])}"):
                    raise PBError(400, {})
                await pb.delete("shop_variants", cur["id"])
            except PBError:
                await pb.update("shop_variants", cur["id"], {"active": False})
    return {"variants": await pb.all("shop_variants", filter=f"product = {q(pid)}", sort="cut,size")}


class StockIn(BaseModel):
    stock: int = Field(ge=0, le=100000)


@router.patch("/variants/{vid}")
async def set_stock(vid: str, body: StockIn, user: User = Depends(admin)):
    return await pb.update("shop_variants", util.rid(vid), {"stock": body.stock})


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------

@router.post("/media")
async def upload(file: UploadFile = File(...), kind: str = Form("product"), alt: str = Form(""),
                 user: User = Depends(admin)):
    if kind not in ("product", "content", "brand"):
        kind = "product"
    data = await file.read()
    try:
        info = media.ingest(data)
    except media.BadImage as e:
        raise HTTPException(400, str(e))
    rec = await pb.create("shop_media", {"key": info["key"], "kind": kind, "alt_id": alt[:300], "alt_en": "",
                                         "width": info["width"], "height": info["height"], "sizes": info["sizes"],
                                         "color": info["color"], "uploaded_by": user.username})
    return {"media": rec}


@router.get("/media")
async def list_media(kind: str = "", page: int = 1, user: User = Depends(admin)):
    filt = f"kind = {q(kind)}" if kind in ("product", "content", "review", "brand") else ""
    data = await pb.list("shop_media", filter=filt, sort="-created", page=max(1, page), per_page=60)
    return {"media": data.get("items", [])}


@router.delete("/media/{key}")
async def delete_media(key: str, user: User = Depends(admin)):
    if not key.isalnum():
        raise HTTPException(404, "Not found.")
    used = await pb.first("shop_products", f"media ~ {q(key)}")
    if used:
        raise HTTPException(409, f"Still used by “{used['name_id']}”. Remove it there first.")
    rec = await pb.first("shop_media", f"key = {q(key)}")
    if rec:
        await pb.delete("shop_media", rec["id"])
    media.remove(key)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Demo catalog
# ---------------------------------------------------------------------------

@router.delete("/demo")
async def remove_demo(user: User = Depends(admin)):
    """Delete the AI-generated demo products (and their photos, lookbook and journal post)."""
    removed, keys = 0, set()
    for p in await pb.all("shop_products", filter="demo = true"):
        keys.update(p.get("media") or [])
        if await pb.first("shop_order_items", f"product = {q(p['id'])}"):
            await pb.update("shop_products", p["id"], {"status": "archived"})
        else:
            await pb.delete("shop_products", p["id"])
        removed += 1
    for coll, slug in (("shop_lookbooks", "keluarga-di-rumah"), ("shop_posts", "tips-foto-keluarga-serasi")):
        rec = await pb.first(coll, f"slug = {q(slug)}")
        if rec:
            await pb.delete(coll, rec["id"])
    for coll in ("shop_collections", "shop_categories"):
        for c in await pb.all(coll):
            if c.get("image") in keys:
                await pb.update(coll, c["id"], {"image": ""})
    for sec in await pb.all("shop_home_sections"):
        data = sec.get("data") or {}
        if data.get("image") in keys:
            await pb.update("shop_home_sections", sec["id"], {"data": {**data, "image": ""}})
    for key in keys:
        rec = await pb.first("shop_media", f"key = {q(key)}")
        if rec:
            await pb.delete("shop_media", rec["id"])
        media.remove(key)
    await pb.kv_set("demo_catalog", False)
    return {"removed": removed}
