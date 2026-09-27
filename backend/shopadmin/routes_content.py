"""Admin API: simple collections edited as whole records — categories, collections,
size charts, vouchers, set discounts, pages, journal posts, lookbooks, homepage sections."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from cs import catalog, util
from cs.pb import PBError, pb, q

from .security import User, admin

router = APIRouter(prefix="/api/c")

# name → (collection, editable fields, sort)
REGISTRY: dict[str, tuple[str, set[str], str]] = {
    "categories": ("shop_categories", {"slug", "name_id", "name_en", "description_id", "description_en", "image", "sort",
                                       "active"}, "sort,name_id"),
    "collections": ("shop_collections", {"slug", "name_id", "name_en", "description_id", "description_en", "image",
                                         "sort", "active", "featured"}, "sort,name_id"),
    "charts": ("shop_size_charts", {"name", "cut", "columns", "rows", "notes_id", "notes_en"}, "cut,name"),
    "vouchers": ("shop_vouchers", {"code", "label_id", "label_en", "kind", "value", "min_spend", "max_discount", "starts",
                                   "ends", "usage_limit", "per_customer_limit", "active", "special", "customer"}, "-created"),
    "set_discounts": ("shop_set_discounts", {"min_members", "percent", "label_id", "label_en", "active"}, "min_members"),
    "pages": ("shop_pages", {"slug", "title_id", "title_en", "body_id", "body_en", "status", "in_footer", "sort"},
              "sort,title_id"),
    "posts": ("shop_posts", {"slug", "title_id", "title_en", "excerpt_id", "excerpt_en", "body_id", "body_en", "cover",
                             "status", "published_at", "tags"}, "-published_at,-created"),
    "lookbooks": ("shop_lookbooks", {"slug", "title_id", "title_en", "intro_id", "intro_en", "cover", "blocks", "status",
                                     "sort"}, "sort,-created"),
    "home": ("shop_home_sections", {"kind", "data", "sort", "active"}, "sort"),
}


def entry(name: str) -> tuple[str, set[str], str]:
    if name not in REGISTRY:
        raise HTTPException(404, "Not found.")
    return REGISTRY[name]


def clean(name: str, body: dict) -> dict:
    _, fields, _ = entry(name)
    data = {k: v for k, v in body.items() if k in fields}
    if "slug" in data:
        data["slug"] = util.slugify(str(data["slug"] or data.get("title_id") or data.get("name_id") or ""), 120)
    if "code" in data:
        data["code"] = "".join(ch for ch in str(data["code"]).upper() if ch.isalnum() or ch in "-_")[:40]
    if name == "charts" and "cut" in data and data["cut"] not in catalog.CUTS:
        raise HTTPException(400, "Unknown cut.")
    for k in ("image", "cover"):
        if k in data and data[k] and not str(data[k]).isalnum():
            data[k] = ""
    return data


@router.get("/{name}")
async def list_(name: str, user: User = Depends(admin)):
    coll, _, sort = entry(name)
    return {"items": await pb.all(coll, sort=sort)}


@router.post("/{name}")
async def create(name: str, body: dict, user: User = Depends(admin)):
    coll, _, _ = entry(name)
    data = clean(name, body)
    try:
        return await pb.create(coll, data)
    except PBError as e:
        if "slug" in str(e.data) or "code" in str(e.data):
            raise HTTPException(409, "That link name / code is already used. Choose another.")
        raise


@router.patch("/{name}/{rid_}")
async def update(name: str, rid_: str, body: dict, user: User = Depends(admin)):
    coll, _, _ = entry(name)
    try:
        return await pb.update(coll, util.rid(rid_), clean(name, body))
    except PBError as e:
        if "slug" in str(e.data) or "code" in str(e.data):
            raise HTTPException(409, "That link name / code is already used. Choose another.")
        raise


@router.delete("/{name}/{rid_}")
async def delete(name: str, rid_: str, user: User = Depends(admin)):
    coll, _, _ = entry(name)
    util.rid(rid_)
    if name == "categories" and await pb.first("shop_products", f"category = {q(rid_)}"):
        raise HTTPException(409, "Products still use this category. Move them first.")
    await pb.delete(coll, rid_)
    return {"ok": True}


@router.post("/home/order")
async def reorder_home(body: dict, user: User = Depends(admin)):
    for i, sid in enumerate(body.get("ids") or []):
        await pb.update("shop_home_sections", util.rid(str(sid)), {"sort": i})
    return {"ok": True}
