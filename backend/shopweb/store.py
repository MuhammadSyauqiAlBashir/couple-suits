"""Catalog reads for the storefront, cached in memory for a few seconds so pages
render fast without hammering PocketBase. Admin edits show up within CACHE_TTL."""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter, defaultdict

from cs import catalog

from . import i18n
from cs.pb import pb, q

CACHE_TTL = 20


class Cache:
    def __init__(self):
        self.at = 0.0
        self.lock = asyncio.Lock()
        self.products: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.by_slug: dict[str, dict] = {}
        self.categories: list[dict] = []
        self.collections: list[dict] = []
        self.charts: dict[str, dict] = {}
        self.pages: list[dict] = []
        self.set_rules: list[dict] = []
        self.home: list[dict] = []
        self.ratings: dict[str, tuple[float, int]] = {}
        self.co: dict[str, Counter] = {}
        self.sold: Counter = Counter()


C = Cache()


async def refresh(force: bool = False):
    if not force and time.monotonic() - C.at < CACHE_TTL:
        return
    async with C.lock:
        if not force and time.monotonic() - C.at < CACHE_TTL:
            return
        products, cats, colls, charts, pages, rules, home, reviews = await asyncio.gather(
            pb.all("shop_products", filter="status = 'live'", sort="sort,-created"),
            pb.all("shop_categories", filter="active = true", sort="sort,name_id"),
            pb.all("shop_collections", filter="active = true", sort="sort,name_id"),
            pb.all("shop_size_charts"),
            pb.all("shop_pages", filter="status = 'live'", sort="sort,title_id",
                   fields="id,slug,title_id,title_en,in_footer,sort"),
            pb.all("shop_set_discounts", filter="active = true", sort="min_members"),
            pb.all("shop_home_sections", filter="active = true", sort="sort"),
            pb.all("shop_reviews", filter="status = 'approved'", fields="product,rating"),
        )
        C.products = products
        C.by_id = {p["id"]: p for p in products}
        C.by_slug = {p["slug"]: p for p in products}
        C.categories, C.collections = cats, colls
        C.charts = {c["id"]: c for c in charts}
        C.pages, C.set_rules, C.home = pages, rules, home
        agg: dict[str, list[int]] = defaultdict(list)
        for r in reviews:
            agg[r["product"]].append(int(r.get("rating") or 0))
        C.ratings = {pid: (sum(v) / len(v), len(v)) for pid, v in agg.items() if v}
        C.at = time.monotonic()
    if time.monotonic() - _co_at[0] > 600:
        asyncio.create_task(_refresh_co())


_co_at = [0.0]


async def _refresh_co():
    """"Families also bought": co-occurrence of products in recent orders."""
    _co_at[0] = time.monotonic()
    try:
        items = await pb.all("shop_order_items", fields="order,product,qty", sort="-created")
    except Exception:  # noqa: BLE001 - recommendations are optional
        return
    items = items[:5000]
    by_order: dict[str, set] = defaultdict(set)
    sold: Counter = Counter()
    for it in items:
        if it.get("product"):
            by_order[it["order"]].add(it["product"])
            sold[it["product"]] += int(it.get("qty") or 1)
    co: dict[str, Counter] = defaultdict(Counter)
    for prods in by_order.values():
        for a in prods:
            for b in prods:
                if a != b:
                    co[a][b] += 1
    C.co, C.sold = co, sold


# ---------------------------------------------------------------------------
# Product views for templates
# ---------------------------------------------------------------------------

def card(p: dict, lang: str) -> dict:
    lo, hi, rlo, rhi = catalog.price_range(p)
    media = p.get("media") or []
    rating = C.ratings.get(p["id"])
    cuts = p.get("cuts") or []
    return {
        "id": p["id"], "slug": p["slug"], "name": catalog.tr(p, "name", lang), "summary": catalog.tr(p, "summary", lang),
        "image": media[0] if media else "", "image2": media[1] if len(media) > 1 else "",
        "price": lo, "price_max": hi, "regular": rlo, "on_sale": catalog.sale_active(p) and rlo > lo,
        "sale_percent": int(p.get("sale_percent") or 0), "sale_end": p.get("sale_end") or "",
        "preorder": p.get("stock_mode") == "preorder", "sets": catalog.set_types(p),
        "cuts": [catalog.label(catalog.CUTS, c, lang) for c in cuts],
        "colors": [c.get("hex") for c in (p.get("colors") or []) if c.get("hex")][:5],
        "rating": round(rating[0], 1) if rating else None, "reviews": rating[1] if rating else 0,
        "for_text": " · ".join(i18n.t(f"set.{x}", lang) for x in catalog.set_types(p)),
    }


def cards(products: list[dict], lang: str) -> list[dict]:
    return [card(p, lang) for p in products]


SORTS = {"featured", "new", "price_asc", "price_desc", "popular"}


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if w]


def search_text(p: dict) -> str:
    parts = [p.get(f"{f}_{lang}", "") for f in ("name", "summary", "material") for lang in ("id", "en")]
    parts += [str(t) for t in (p.get("tags") or [])]
    cat = next((c for c in C.categories if c["id"] == p.get("category")), None)
    if cat:
        parts += [cat.get("name_id", ""), cat.get("name_en", "")]
    return " ".join(parts).lower()


def filter_products(*, category: str = "", collection: str = "", set_type: str = "", cut: str = "", query: str = "",
                    sale: bool = False, sort: str = "featured") -> list[dict]:
    out = list(C.products)
    if category:
        out = [p for p in out if p.get("category") == category]
    if collection:
        out = [p for p in out if collection in (p.get("collections") or [])]
    if set_type:
        out = [p for p in out if set_type in catalog.set_types(p)]
    if cut:
        out = [p for p in out if cut in (p.get("cuts") or [])]
    if sale:
        out = [p for p in out if catalog.sale_active(p)]
    if query:
        words = _words(query)
        out = [p for p in out if all(w in search_text(p) for w in words)]
    if sort == "new":
        out.sort(key=lambda p: p["created"], reverse=True)
    elif sort == "price_asc":
        out.sort(key=lambda p: catalog.price_range(p)[0])
    elif sort == "price_desc":
        out.sort(key=lambda p: catalog.price_range(p)[0], reverse=True)
    elif sort == "popular":
        out.sort(key=lambda p: C.sold.get(p["id"], 0), reverse=True)
    else:
        out.sort(key=lambda p: (not p.get("featured"), p.get("sort") or 0))
    return out


def recommendations(product_id: str, limit: int = 4) -> list[dict]:
    """Bought together first, then similar (same category / shared tags / same collections)."""
    p = C.by_id.get(product_id)
    picks: list[str] = [pid for pid, _ in C.co.get(product_id, Counter()).most_common(limit) if pid in C.by_id]
    if p:
        tags = set(p.get("tags") or [])
        colls = set(p.get("collections") or [])

        def score(o: dict) -> float:
            s = 0.0
            if o.get("category") and o.get("category") == p.get("category"):
                s += 2
            s += len(tags & set(o.get("tags") or [])) + 1.5 * len(colls & set(o.get("collections") or []))
            s += min(C.sold.get(o["id"], 0), 20) / 20
            return s

        for o in sorted(C.products, key=score, reverse=True):
            if len(picks) >= limit:
                break
            if o["id"] != product_id and o["id"] not in picks:
                picks.append(o["id"])
    return [C.by_id[i] for i in picks[:limit]]


def for_ids(ids: list[str]) -> list[dict]:
    return [C.by_id[i] for i in ids if i in C.by_id]


async def variants_for(product_id: str) -> list[dict]:
    return await pb.all("shop_variants", filter=f"product = {q(product_id)} && active = true")


def chart_list(p: dict) -> list[dict]:
    """Size charts attached to a product, else the default chart per cut."""
    ids = p.get("size_charts") or []
    charts = [C.charts[i] for i in ids if i in C.charts]
    have = {c["cut"] for c in charts}
    for cut in p.get("cuts") or []:
        if cut not in have:
            default = next((c for c in C.charts.values() if c["cut"] == cut and c.get("name", "").lower().startswith("default")), None)
            default = default or next((c for c in C.charts.values() if c["cut"] == cut), None)
            if default:
                charts.append(default)
                have.add(cut)
    order = list(catalog.CUTS)
    return sorted(charts, key=lambda c: order.index(c["cut"]) if c["cut"] in order else 99)
