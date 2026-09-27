"""Server-rendered pages."""

from __future__ import annotations

import hmac
import json
import math
import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

from cs import catalog, config, media, util
from cs.pb import pb, q

from . import i18n, stats, store
from .render import STATIC, VERSION, lang_of, render

router = APIRouter()
PER_PAGE = 24


def L(request: Request) -> str:
    return lang_of(request)


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

def default_sections() -> list[dict]:
    return [{"kind": k, "data": {}} for k in ("hero", "sets", "products", "usp", "categories", "reviews")] + \
        [{"kind": "products", "data": {"mode": "new"}}]


async def section_view(sec: dict, lang: str) -> dict | None:
    kind, data = sec["kind"], sec.get("data") or {}
    view = {"kind": kind, "data": data}
    if kind == "hero":
        image = data.get("image")
        if not image:
            feat = next((p for p in store.filter_products() if p.get("media")), None)
            image = feat["media"][0] if feat else ""
        view["image"] = image
    elif kind == "products":
        mode, ref, limit = data.get("mode") or "featured", data.get("ref") or "", int(data.get("limit") or 8)
        if mode == "new":
            items = store.filter_products(sort="new")
        elif mode == "sale":
            items = store.filter_products(sale=True)
        elif mode == "category":
            items = store.filter_products(category=ref)
        elif mode == "collection":
            items = store.filter_products(collection=ref)
        elif mode == "popular":
            items = store.filter_products(sort="popular")
        else:
            items = [p for p in store.filter_products() if p.get("featured")] or store.filter_products()
        if not items:
            return None
        view["mode"] = mode
        view["cards"] = store.cards(items[:limit], lang)
    elif kind == "collection":
        coll = next((c for c in store.C.collections if c["id"] == data.get("collection")), None)
        if not coll:
            return None
        view["collection"] = coll
        view["cards"] = store.cards(store.filter_products(collection=coll["id"])[:4], lang)
    elif kind == "lookbook":
        lb = await pb.first("shop_lookbooks", f"id = {q(data.get('lookbook') or '')} && status = 'live'") \
            if data.get("lookbook") else await pb.first("shop_lookbooks", "status = 'live'", sort="sort,-created")
        if not lb:
            return None
        view["lookbook"] = lb
    elif kind == "reviews":
        revs = (await pb.list("shop_reviews", filter="status = 'approved' && rating >= 4", sort="-created",
                              per_page=6)).get("items", [])
        if not revs:
            return None
        view["reviews"] = [{**r, "product_rec": store.C.by_id.get(r["product"])} for r in revs]
    elif kind == "categories":
        if not store.C.categories:
            return None
        view["tiles"] = [{"cat": c, "image": c.get("image") or next(
            (p["media"][0] for p in store.filter_products(category=c["id"]) if p.get("media")), "")}
            for c in store.C.categories]
    elif kind == "sets":
        tiles = []
        for key in ("couple", "family", "kids"):
            prods = [p for p in store.filter_products(set_type=key) if p.get("media")]
            if prods:
                used = {t["image"] for t in tiles}
                pick = next((p for p in prods if p["media"][0] not in used), prods[0])
                tiles.append({"key": key, "image": pick["media"][0], "count": len(prods)})
        if not tiles:
            return None
        view["tiles"] = tiles
    return view


@router.get("/")
async def home(request: Request):
    lang = L(request)
    raw = [{"kind": s["kind"], "data": s.get("data") or {}} for s in store.C.home] or default_sections()
    sections = [v for v in [await section_view(s, lang) for s in raw] if v]
    s = request.state.settings
    return render(request, "home.html", sections=sections,
                  title=f"{s['brand_name']} — {catalog.tr(s, 'tagline', lang)}",
                  description=catalog.tr(s, "tagline", lang))


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------

def listing(request: Request, *, title: str, intro: str = "", banner: str = "", base_path: str, category: str = "",
            collection: str = "", sale: bool = False, extra_desc: str = ""):
    lang = L(request)
    qp = request.query_params
    set_type = qp.get("set", "") if qp.get("set") in ("couple", "family", "kids") else ""
    cut = qp.get("cut", "") if qp.get("cut") in catalog.CUTS else ""
    sort = qp.get("sort", "featured") if qp.get("sort") in store.SORTS else "featured"
    query = (qp.get("q") or "").strip()[:80]
    if not category and qp.get("category"):
        cat = next((c for c in store.C.categories if c["slug"] == qp.get("category")), None)
        category = cat["id"] if cat else ""
    items = store.filter_products(category=category, collection=collection, set_type=set_type, cut=cut, query=query,
                                  sale=sale or qp.get("sale") == "1", sort=sort)
    try:
        page = max(1, int(qp.get("page", "1")))
    except ValueError:
        page = 1
    pages_n = max(1, math.ceil(len(items) / PER_PAGE))
    page = min(page, pages_n)
    shown = store.cards(items[(page - 1) * PER_PAGE: page * PER_PAGE], lang)
    if query:
        stats.add("searches", query.lower()[:60])
        title = i18n.t("search.results", lang, q=query)

    def link(**changes) -> str:
        params = {k: v for k, v in qp.items() if k not in ("page", "lang")}
        params.update({k: v for k, v in changes.items()})
        params = {k: v for k, v in params.items() if v not in ("", None)}
        from urllib.parse import urlencode  # noqa: PLC0415
        return base_path + ("?" + urlencode(params) if params else "")

    return render(request, "listing.html", title=title, intro=intro, banner=banner, cards=shown, total=len(items),
                  page=page, pages_n=pages_n, set_type=set_type, cut=cut, sort=sort, query=query, link=link,
                  base_path=base_path, description=extra_desc or intro or title,
                  noindex=bool(query or set_type or cut or sort != "featured"))


@router.get("/shop")
async def shop(request: Request):
    return listing(request, title=i18n.t("shop.title", L(request)), base_path="/shop")


@router.get("/sale")
async def sale(request: Request):
    return listing(request, title=i18n.t("sale.title", L(request)), base_path="/sale", sale=True)


@router.get("/c/{slug}")
async def category(request: Request, slug: str):
    cat = next((c for c in store.C.categories if c["slug"] == slug), None)
    if not cat:
        raise HTTPException(404)
    lang = L(request)
    return listing(request, title=catalog.tr(cat, "name", lang), intro=catalog.tr(cat, "description", lang),
                   banner=cat.get("image") or "", base_path=f"/c/{slug}", category=cat["id"])


@router.get("/collections/{slug}")
async def collection(request: Request, slug: str):
    coll = next((c for c in store.C.collections if c["slug"] == slug), None)
    if not coll:
        raise HTTPException(404)
    lang = L(request)
    return listing(request, title=catalog.tr(coll, "name", lang), intro=catalog.tr(coll, "description", lang),
                   banner=coll.get("image") or "", base_path=f"/collections/{slug}", collection=coll["id"])


@router.get("/search")
async def search(request: Request):
    return RedirectResponse(f"/shop?q={request.query_params.get('q', '')}", status_code=302)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

def product_json(p: dict, variants: list[dict], lang: str, family: list[dict]) -> dict:
    colors = [{"key": c.get("key") or "", "name": c.get(f"name_{lang}") or c.get("name_id") or c.get("key") or "",
               "hex": c.get("hex") or "", "media": c.get("media") or []} for c in (p.get("colors") or [])]
    stock: dict[str, int] = {}
    for v in variants:
        stock[f"{v['cut']}|{v['size']}|{v.get('color') or ''}"] = int(v.get("stock") or 0)
    cuts = []
    for c in p.get("cuts") or []:
        if c not in catalog.CUTS:
            continue
        regular, price = catalog.cut_price(p, c)
        sizes = [s for s in catalog.sizes_for_cut(c) if any(k.startswith(f"{c}|{s}|") for k in stock)]
        cuts.append({"id": c, "label": catalog.label(catalog.CUTS, c, lang), "group": catalog.CUTS[c]["group"],
                     "price": price, "regular": regular,
                     "sizes": [{"id": s, "label": catalog.size_label(s, lang)} for s in sizes]})
    have = {c["id"] for c in cuts}
    roles = []
    for key, r in catalog.ROLES.items():
        options = [c for c in r["cuts"] if c in have]
        if options:
            roles.append({"id": key, "label": r[lang] if lang in r else r["id"], "cuts": options})
    presets = []
    role_ids = {r["id"] for r in roles}
    for key, pr in catalog.PRESETS.items():
        if all(r in role_ids for r in pr["roles"]):
            presets.append({"id": key, "label": pr[lang], "roles": pr["roles"]})
    return {
        "id": p["id"], "slug": p["slug"], "name": catalog.tr(p, "name", lang), "image": (p.get("media") or [""])[0],
        "preorder": p.get("stock_mode") == "preorder", "preorder_days": int(p.get("preorder_days") or 0),
        "cuts": cuts, "colors": colors, "stock": stock, "roles": roles, "presets": presets,
        "set_rules": [{"min": int(r["min_members"]), "percent": int(r["percent"])} for r in store.C.set_rules],
        "family": [{"name": m.get("name") or "", "role": m.get("role") or "", "cut": m.get("cut") or "",
                    "size": m.get("size") or ""} for m in family],
        "sale_end": p.get("sale_end") if catalog.sale_active(p) else "",
    }


@router.get("/p/{slug}")
async def product(request: Request, slug: str):
    p = store.C.by_slug.get(slug)
    if not p:
        raise HTTPException(404)
    lang = L(request)
    variants = await store.variants_for(p["id"])
    customer = request.state.customer
    family = await pb.all("shop_family_members", filter=f"customer = {q(customer['id'])}", sort="sort,created") \
        if customer else []
    reviews = (await pb.list("shop_reviews", filter=f"product = {q(p['id'])} && status = 'approved'", sort="-created",
                             per_page=30)).get("items", [])
    data = product_json(p, variants, lang, family)
    charts = store.chart_list(p)
    recs = store.cards(store.recommendations(p["id"], 4), lang)
    card = store.card(p, lang)
    cat = next((c for c in store.C.categories if c["id"] == p.get("category")), None)
    stats.add("product_views", p["id"])
    lo, hi, _, _ = catalog.price_range(p)
    any_stock = data["preorder"] or any(v > 0 for v in data["stock"].values())
    ld = {
        "@context": "https://schema.org", "@type": "Product", "name": card["name"],
        "description": util.plain(catalog.tr(p, "summary", lang) or catalog.tr(p, "description", lang), 300),
        "image": [config.SHOP_URL + catalog.media_url(k, 1200) for k in (p.get("media") or [])[:4]],
        "brand": {"@type": "Brand", "name": request.state.settings["brand_name"]},
        "offers": {"@type": "AggregateOffer", "priceCurrency": "IDR", "lowPrice": lo, "highPrice": hi,
                   "availability": "https://schema.org/" + ("PreOrder" if data["preorder"] else "InStock" if any_stock
                                                              else "OutOfStock")},
    }
    if card["reviews"]:
        ld["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": card["rating"], "reviewCount": card["reviews"]}
    wa_text = f"Halo, saya mau tanya ukuran untuk {card['name']} ({config.SHOP_URL}/p/{slug})" if lang == "id" else \
        f"Hi, I have a sizing question about {card['name']} ({config.SHOP_URL}/p/{slug})"
    return render(request, "product.html", p=p, card=card, data=data, charts=charts, reviews=reviews, recs=recs,
                  category=cat, ld=json.dumps(ld, ensure_ascii=False), any_stock=any_stock,
                  wa_ask=util.wa_link(request.state.settings["whatsapp"], wa_text),
                  title=p.get("seo_title") or f"{card['name']} — {request.state.settings['brand_name']}",
                  description=p.get("seo_description") or util.plain(catalog.tr(p, "summary", lang) or
                                                                     catalog.tr(p, "description", lang)),
                  og_image=config.SHOP_URL + catalog.media_url(card["image"], 1200) if card["image"] else "")


# ---------------------------------------------------------------------------
# Cart, checkout, order status
# ---------------------------------------------------------------------------

@router.get("/cart")
async def cart(request: Request):
    return render(request, "cart.html", title=i18n.t("cart.title", L(request)), noindex=True)


@router.get("/checkout")
async def checkout(request: Request):
    customer = request.state.customer
    last_address = {}
    if customer:
        last = await pb.first("shop_orders", f"customer = {q(customer['id'])}", sort="-created")
        last_address = (last or {}).get("address") or {}
    privacy = next((p for p in store.C.pages if p["slug"] in ("privacy", "kebijakan-privasi")), None)
    return render(request, "checkout.html", title=i18n.t("co.title", L(request)), noindex=True,
                  last_address=last_address, privacy=privacy)


async def order_for(number: str, token: str, customer: dict | None) -> dict:
    if not number.startswith("CS-") or len(number) > 30:
        raise HTTPException(404)
    order = await pb.first("shop_orders", f"number = {q(number)}")
    if not order:
        raise HTTPException(404)
    ok = (token and hmac.compare_digest(token, order["token"])) or (customer and order.get("customer") == customer["id"])
    if not ok:
        raise HTTPException(404)
    return order


STEPS = ["new", "confirmed", "awaiting_payment", "paid", "in_production", "shipped", "completed"]


@router.get("/order/{number}")
async def order_page(request: Request, number: str, t: str = ""):
    order = await order_for(number, t, request.state.customer)
    lang = L(request)
    items = await pb.all("shop_order_items", filter=f"order = {q(order['id'])}", sort="created")
    s = request.state.settings
    wa = util.wa_link(s["whatsapp"], i18n.t("o.wa_text", lang, brand=s["brand_name"], n=order["number"],
                                           name=order["contact_name"]))
    reviewed = set()
    can_review = order["status"] in ("shipped", "completed")
    if can_review:
        reviewed = {r["product"] for r in await pb.all("shop_reviews", filter=f"order = {q(order['id'])}", fields="product")}
    groups: dict[str, list] = {}
    for it in items:
        groups.setdefault(it.get("set_key") or f"single-{it['id']}", []).append(it)
    review_products = []
    seen = set()
    for it in items:
        if it.get("product") and it["product"] not in seen and it["product"] not in reviewed:
            seen.add(it["product"])
            review_products.append(it)
    step = STEPS.index(order["status"]) if order["status"] in STEPS else -1
    return render(request, "order.html", order=order, groups=list(groups.values()), wa_order=wa, token=t,
                  can_review=can_review, review_products=review_products, steps=STEPS, step=step, noindex=True,
                  title=i18n.t("o.title", lang, n=order["number"]), just_placed=request.query_params.get("new") == "1",
                  reviewed_now=request.query_params.get("reviewed") == "1")


review_limit = util.Window(10, 3600)


@router.post("/order/{number}/review")
async def order_review(request: Request, number: str, t: str = Form(""), product: str = Form(...),
                       rating: int = Form(...), text: str = Form(""), family: str = Form(""), name: str = Form(""),
                       consent: str = Form(""), photos: list[UploadFile] = File(default=[])):
    review_limit.check(request.client.host if request.client else "", "Too many reviews.")
    customer = request.state.customer
    order = await order_for(number, t, customer)
    if order["status"] not in ("shipped", "completed"):
        raise HTTPException(403, "You can review after your order has shipped.")
    util.rid(product)
    items = await pb.all("shop_order_items", filter=f"order = {q(order['id'])} && product = {q(product)}", fields="id")
    if not items:
        raise HTTPException(404)
    if await pb.first("shop_reviews", f"order = {q(order['id'])} && product = {q(product)}"):
        raise HTTPException(409, "Already reviewed.")
    keys = []
    files = [f for f in (photos or []) if f.filename][:4]
    if files and consent != "1":
        files = []
    for f in files:
        data = await f.read()
        try:
            info = media.ingest(data)
        except media.BadImage:
            continue
        await pb.create("shop_media", {"key": info["key"], "kind": "review", "width": info["width"],
                                       "height": info["height"], "sizes": info["sizes"], "color": info["color"],
                                       "uploaded_by": f"order:{order['number']}"})
        keys.append(info["key"])
    await pb.create("shop_reviews", {
        "product": product, "order": order["id"], "customer": order.get("customer") or "",
        "name": (name or order["contact_name"]).strip()[:80], "rating": max(1, min(5, rating)), "text": text.strip()[:3000],
        "photos": keys, "family": family.strip()[:120], "status": "pending", "reply": ""})
    stats.add("reviews")
    tq = f"t={t}&" if t else ""
    return RedirectResponse(f"/order/{number}?{tq}reviewed=1#reviews", status_code=303)


# ---------------------------------------------------------------------------
# Wishlist, recently viewed (rendered by the browser from local lists)
# ---------------------------------------------------------------------------

@router.get("/wishlist")
async def wishlist(request: Request):
    return render(request, "wishlist.html", title=i18n.t("wish.title", L(request)), noindex=True)


# ---------------------------------------------------------------------------
# Content: pages, journal, lookbook, size guide
# ---------------------------------------------------------------------------

@router.get("/page/{slug}")
async def page(request: Request, slug: str):
    rec = await pb.first("shop_pages", f"slug = {q(slug)} && status = 'live'")
    if not rec:
        raise HTTPException(404)
    lang = L(request)
    return render(request, "page.html", page=rec, title=catalog.tr(rec, "title", lang),
                  description=util.plain(catalog.tr(rec, "body", lang)))


@router.get("/size-guide")
async def size_guide(request: Request):
    charts = {}
    for c in store.C.charts.values():
        if c["cut"] not in charts or c.get("name", "").lower().startswith("default"):
            charts[c["cut"]] = c
    order = list(catalog.CUTS)
    return render(request, "size_guide.html", charts=sorted(charts.values(), key=lambda c: order.index(c["cut"])),
                  title=i18n.t("nav.size_guide", L(request)))


@router.get("/journal")
async def journal(request: Request):
    posts = (await pb.list("shop_posts", filter="status = 'live'", sort="-published_at,-created", per_page=60)).get("items", [])
    return render(request, "journal.html", posts=posts, title=i18n.t("blog.title", L(request)))


@router.get("/journal/{slug}")
async def post(request: Request, slug: str):
    rec = await pb.first("shop_posts", f"slug = {q(slug)} && status = 'live'")
    if not rec:
        raise HTTPException(404)
    lang = L(request)
    related = store.cards([p for p in store.filter_products() if set(p.get("tags") or []) & set(rec.get("tags") or [])][:4],
                          lang)
    return render(request, "post.html", post=rec, related=related, title=catalog.tr(rec, "title", lang),
                  description=catalog.tr(rec, "excerpt", lang) or util.plain(catalog.tr(rec, "body", lang)),
                  og_image=config.SHOP_URL + catalog.media_url(rec["cover"], 1200) if rec.get("cover") else "")


@router.get("/lookbook")
async def lookbooks(request: Request):
    items = await pb.all("shop_lookbooks", filter="status = 'live'", sort="sort,-created")
    return render(request, "lookbooks.html", lookbooks=items, title=i18n.t("lookbook.title", L(request)))


@router.get("/lookbook/{slug}")
async def lookbook(request: Request, slug: str):
    rec = await pb.first("shop_lookbooks", f"slug = {q(slug)} && status = 'live'")
    if not rec:
        raise HTTPException(404)
    lang = L(request)
    blocks = []
    for b in rec.get("blocks") or []:
        prods = store.cards(store.for_ids(b.get("products") or []), lang)
        blocks.append({**b, "cards": prods})
    return render(request, "lookbook.html", lb=rec, blocks=blocks, title=catalog.tr(rec, "title", lang),
                  description=catalog.tr(rec, "intro", lang),
                  og_image=config.SHOP_URL + catalog.media_url(rec["cover"], 1200) if rec.get("cover") else "")


# ---------------------------------------------------------------------------
# SEO + PWA
# ---------------------------------------------------------------------------

@router.get("/robots.txt")
async def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /cart\nDisallow: /checkout\nDisallow: /order/\n"
                             "Disallow: /account\nDisallow: /api/\n"
                             f"Sitemap: {config.SHOP_URL}/sitemap.xml\n")


@router.get("/sitemap.xml")
async def sitemap():
    urls = ["/", "/shop", "/sale", "/size-guide", "/journal", "/lookbook"]
    urls += [f"/p/{p['slug']}" for p in store.C.products]
    urls += [f"/c/{c['slug']}" for c in store.C.categories] + [f"/collections/{c['slug']}" for c in store.C.collections]
    urls += [f"/page/{p['slug']}" for p in store.C.pages]
    for coll, prefix in (("shop_posts", "/journal/"), ("shop_lookbooks", "/lookbook/")):
        urls += [prefix + r["slug"] for r in await pb.all(coll, filter="status = 'live'", fields="slug")]
    body = "".join(f"<url><loc>{config.SHOP_URL}{u}</loc></url>" for u in urls)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    f"{body}</urlset>", media_type="application/xml")


@router.get("/manifest.webmanifest")
async def manifest(request: Request):
    s = request.state.settings
    lang = L(request)
    data = {
        "name": s["brand_name"], "short_name": s["brand_name"][:12], "description": catalog.tr(s, "tagline", lang),
        "start_url": "/?utm_source=app", "scope": "/", "display": "standalone", "background_color": "#fbfaf8",
        "theme_color": "#fbfaf8", "lang": lang,
        "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    }
    return Response(json.dumps(data), media_type="application/manifest+json")


@router.get("/sw.js")
async def service_worker():
    with open(static_path("js/sw.js")) as f:
        body = f.read().replace("__VERSION__", VERSION)
    return Response(body, media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/offline")
async def offline(request: Request):
    return render(request, "error.html", 200, code="offline")


def static_path(rel: str) -> str:
    return os.path.join(STATIC, rel)
