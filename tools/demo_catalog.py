"""Demo catalog for Couple Suits (flagged demo=true so it can be removed in one go).

  python tools/demo_catalog.py images   # generate product photos with FLUX.2 klein (free quota)
  python tools/demo_catalog.py seed     # create products, variants, collections, content in PocketBase

Needs the shop-admin environment (CS_PB_*, CF_*, CS_MEDIA_DIR). Images are cached in
DEMO_IMG_DIR so re-running doesn't spend quota twice. The photos are AI-generated
placeholders; replace them with real product photos before launch."""

from __future__ import annotations

import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from cs import catalog, flux, media  # noqa: E402
from cs.pb import pb, q  # noqa: E402

IMG_DIR = os.environ.get("DEMO_IMG_DIR", os.path.expanduser("~/work/cs-demo-img"))

STYLE = ("Editorial fashion catalogue photograph, minimal premium style, warm off-white seamless studio backdrop, "
         "soft natural window light, gentle shadows, sharp focus on the garments, true-to-life fabric texture, "
         "no text, no watermark, no logo.")

CATEGORIES = [
    ("batik", "Batik", "Batik", "Batik tulis & cap dengan motif klasik untuk seluruh keluarga.",
     "Hand-drawn and stamped batik in classic motifs for the whole family."),
    ("raya", "Busana Raya", "Festive wear", "Kurta, gamis, dan koko serasi untuk Lebaran dan acara keluarga.",
     "Matching kurta, gamis and koko for Eid and family celebrations."),
    ("casual", "Kasual", "Casual", "Linen, polo, dan kaos serasi untuk akhir pekan.",
     "Linen, polos and tees that match for the weekend."),
    ("sleepwear", "Piyama", "Sleepwear", "Piyama keluarga yang lembut dan nyaman.", "Soft family pyjamas."),
    ("formal", "Formal & Pesta", "Formal & occasion", "Kebaya, beskap, dan songket untuk hari istimewa.",
     "Kebaya, beskap and songket for special days."),
]

COLLECTIONS = [
    ("lebaran-2027", "Lebaran 2027", "Eid 2027", "Koleksi Raya serasi — pre-order dibuka.",
     "Matching festive collection — pre-orders open.", True),
    ("weekend-linen", "Weekend Linen", "Weekend Linen", "Linen ringan untuk hari santai bersama.",
     "Light linen for slow days together.", False),
]

# slug, category, collections, names (id, en), summary (id, en), cuts+prices, stock mode, preorder days,
# colours, tags, sale %, featured, prompts
PRODUCTS = [
    {
        "slug": "batik-parang-sogan-family", "category": "batik", "collections": [],
        "name": ("Set Keluarga Batik Parang Sogan", "Parang Sogan Batik Family Set"),
        "summary": ("Motif parang klasik warna sogan, katun primisima adem untuk ayah, ibu, dan anak.",
                    "Classic parang motif in sogan brown, cool primisima cotton for dad, mum and the kids."),
        "prices": {"men": 389000, "women": 429000, "boys": 229000, "girls": 249000, "baby": 179000},
        "mode": "ready", "colors": [("sogan", "Sogan", "Sogan brown", "#7a4b2a")], "tags": ["batik", "parang", "kondangan"],
        "featured": True,
        "prompts": [
            "An Indonesian family of four standing together: father in a long-sleeve batik shirt, mother in a batik "
            "wrap dress, a 7-year-old boy in a batik shirt and a 5-year-old girl in a batik dress, all in the same "
            "brown sogan parang batik pattern, full body, smiling naturally.",
            "Close-up flat lay of folded brown sogan parang batik fabric shirts in adult and child sizes stacked "
            "together, showing the diagonal parang motif and fine stitching.",
        ],
    },
    {
        "slug": "linen-sage-couple", "category": "casual", "collections": ["weekend-linen"],
        "name": ("Kemeja Linen Sage Pasangan", "Sage Linen Couple Shirts"),
        "summary": ("Linen ringan warna sage, potongan santai untuk pria dan wanita.",
                    "Light sage linen in relaxed cuts for him and her."),
        "prices": {"men": 329000, "women": 339000}, "mode": "ready",
        "colors": [("sage", "Sage", "Sage", "#9aa98c"), ("sand", "Pasir", "Sand", "#d8c7a8")],
        "tags": ["linen", "couple", "weekend"], "featured": True,
        "prompts": [
            "A young Indonesian couple wearing matching sage green linen shirts, the man in a relaxed camp-collar "
            "shirt with beige trousers, the woman in a sage linen shirt dress, full body, relaxed pose.",
            "Detail close-up of sage green linen fabric shirt collar and coconut buttons, soft natural light.",
        ],
    },
    {
        "slug": "kurta-gamis-ivory-raya", "category": "raya", "collections": ["lebaran-2027"],
        "name": ("Set Raya Kurta & Gamis Ivory", "Ivory Kurta & Gamis Eid Set"),
        "summary": ("Kurta pria, gamis wanita, dan versi anak dengan bordir emas lembut. Dibuat sesuai pesanan.",
                    "Men's kurta, women's gamis and kids' versions with soft gold embroidery. Made to order."),
        "prices": {"men": 459000, "women": 559000, "boys": 279000, "girls": 299000, "baby": 199000},
        "mode": "preorder", "preorder_days": 14, "colors": [("ivory", "Ivory", "Ivory", "#efe6d4")],
        "tags": ["lebaran", "raya", "gamis", "kurta"], "featured": True,
        "prompts": [
            "An Indonesian Muslim family of five for Eid: father in an ivory kurta, mother in an ivory gamis with "
            "hijab, a boy in an ivory kurta, a girl in an ivory gamis, and a baby in ivory, all with subtle gold "
            "embroidery at the neckline, full body, warm and joyful.",
            "Close-up of ivory cotton kurta neckline with delicate gold thread embroidery, premium detail shot.",
        ],
    },
    {
        "slug": "songket-anniversary-couple", "category": "formal", "collections": [],
        "name": ("Set Songket Anniversary", "Songket Anniversary Set"),
        "summary": ("Beskap dan kebaya dengan aksen songket emas untuk anniversary, lamaran, atau pesta.",
                    "Beskap and kebaya with gold songket accents for anniversaries, engagements or parties."),
        "prices": {"men": 899000, "women": 1099000}, "mode": "preorder", "preorder_days": 21,
        "colors": [("maroon", "Marun", "Maroon", "#6b1f2a")], "tags": ["songket", "kebaya", "anniversary"],
        "featured": False,
        "prompts": [
            "An elegant Indonesian couple in matching maroon outfits with gold songket accents: the man in a "
            "structured beskap jacket, the woman in a fitted modern kebaya with a songket skirt, full body, formal pose.",
            "Close-up of maroon songket fabric woven with gold thread, luxurious texture, soft light.",
        ],
    },
    {
        "slug": "family-pyjama-navy-stripe", "category": "sleepwear", "collections": [],
        "name": ("Piyama Keluarga Garis Navy", "Navy Stripe Family Pyjamas"),
        "summary": ("Katun rayon lembut bergaris navy, untuk dewasa, anak, dan bayi.",
                    "Soft cotton-rayon navy stripes for grown-ups, kids and babies."),
        "prices": {"men": 249000, "women": 249000, "unisex_kids": 179000, "baby": 149000}, "mode": "ready",
        "colors": [("navy", "Navy", "Navy", "#23324a")], "tags": ["pyjama", "gift"], "featured": False,
        "prompts": [
            "An Indonesian family of four in matching navy and white striped pyjamas with piped collars, sitting "
            "together on a white bed, cosy morning mood.",
            "Folded navy and white striped pyjama sets in adult, child and baby sizes, neat flat lay.",
        ],
    },
    {
        "slug": "weekend-polo-terracotta", "category": "casual", "collections": ["weekend-linen"],
        "name": ("Polo Weekend Terracotta", "Terracotta Weekend Polo"),
        "summary": ("Polo knit terracotta untuk ayah, ibu, dan anak — cocok untuk foto keluarga.",
                    "Terracotta knit polos for dad, mum and kids — great for family photos."),
        "prices": {"men": 219000, "women": 219000, "boys": 149000, "girls": 149000}, "mode": "ready",
        "colors": [("terracotta", "Terakota", "Terracotta", "#b85c3c")], "tags": ["polo", "weekend", "photo"],
        "featured": True, "sale": 20,
        "prompts": [
            "An Indonesian family (father, mother, son, daughter) wearing matching terracotta knit polo shirts "
            "with cream trousers and skirts, standing close together, full body, candid laugh.",
            "Detail of a terracotta knit polo collar and button placket, texture close-up.",
        ],
    },
    {
        "slug": "kebaya-beskap-modern", "category": "formal", "collections": [],
        "name": ("Kebaya & Beskap Modern Sage", "Modern Sage Kebaya & Beskap"),
        "summary": ("Kebaya brokat modern dan beskap senada untuk wisuda, lamaran, atau kondangan.",
                    "Modern lace kebaya and matching beskap for graduations, engagements or weddings."),
        "prices": {"men": 1250000, "women": 1450000}, "mode": "preorder", "preorder_days": 21,
        "colors": [("sage", "Sage", "Sage", "#a3b09a")], "tags": ["kebaya", "beskap", "kondangan"], "featured": False,
        "prompts": [
            "An Indonesian couple in coordinated sage green formal wear: the woman in a modern lace kebaya with a "
            "batik kain skirt, the man in a sage beskap with a matching batik kain, full body, graceful pose.",
            "Close-up of sage green lace kebaya fabric with delicate floral embroidery.",
        ],
    },
    {
        "slug": "tie-dye-family-tee", "category": "casual", "collections": [],
        "name": ("Kaos Tie-Dye Keluarga", "Family Tie-Dye Tee"),
        "summary": ("Kaos katun combed tie-dye biru laut, unisex untuk semua umur.",
                    "Ocean-blue tie-dye combed cotton tees, unisex for every age."),
        "prices": {"unisex_adult": 149000, "unisex_kids": 109000, "baby": 89000}, "mode": "ready",
        "colors": [("ocean", "Biru laut", "Ocean", "#4f7ea8")], "tags": ["tee", "holiday", "beach"], "featured": False,
        "prompts": [
            "An Indonesian family of four in matching ocean-blue tie-dye cotton t-shirts and white shorts, "
            "standing together barefoot, bright cheerful holiday mood, full body.",
            "Flat lay of ocean-blue tie-dye t-shirts in adult, kid and baby sizes on white.",
        ],
    },
]

SIZE_STOCK = {"S": 6, "M": 10, "L": 10, "XL": 8, "XXL": 4, "XXXL": 2}


def img_path(slug: str, i: int) -> str:
    return os.path.join(IMG_DIR, f"{slug}-{i + 1}.jpg")


async def make_images():
    os.makedirs(IMG_DIR, exist_ok=True)
    for p in PRODUCTS:
        for i, prompt in enumerate(p["prompts"]):
            out = img_path(p["slug"], i)
            if os.path.exists(out):
                continue
            print("generating", os.path.basename(out), flush=True)
            data = await flux.generate(f"{prompt} {STYLE}", width=768, height=1024, seed=random.randint(1, 10**6))
            with open(out, "wb") as f:
                f.write(data)


async def upsert(coll: str, key: str, value: str, data: dict) -> dict:
    rec = await pb.first(coll, f"{key} = {q(value)}")
    return await pb.update(coll, rec["id"], data) if rec else await pb.create(coll, data)


async def add_media(path: str, alt_id: str, alt_en: str) -> str:
    with open(path, "rb") as f:
        info = media.ingest(f.read())
    await pb.create("shop_media", {"key": info["key"], "kind": "product", "alt_id": alt_id, "alt_en": alt_en,
                                   "width": info["width"], "height": info["height"], "sizes": info["sizes"],
                                   "color": info["color"], "uploaded_by": "demo"})
    return info["key"]


async def seed():
    cats = {}
    for i, (slug, nid, nen, did, den) in enumerate(CATEGORIES):
        cats[slug] = await upsert("shop_categories", "slug", slug, {"slug": slug, "name_id": nid, "name_en": nen,
                                                                     "description_id": did, "description_en": den,
                                                                     "sort": i, "active": True})
    colls = {}
    for i, (slug, nid, nen, did, den, feat) in enumerate(COLLECTIONS):
        colls[slug] = await upsert("shop_collections", "slug", slug, {"slug": slug, "name_id": nid, "name_en": nen,
                                                                       "description_id": did, "description_en": den,
                                                                       "sort": i, "active": True, "featured": feat})
    first_image: dict[str, str] = {}
    for n, p in enumerate(PRODUCTS):
        existing = await pb.first("shop_products", f"slug = {q(p['slug'])}")
        if existing:
            print("exists", p["slug"])
            first_image[p["slug"]] = (existing.get("media") or [""])[0]
            continue
        keys = []
        for i in range(len(p["prompts"])):
            path = img_path(p["slug"], i)
            if os.path.exists(path):
                keys.append(await add_media(path, p["name"][0], p["name"][1]))
        first_image[p["slug"]] = keys[0] if keys else ""
        sale = p.get("sale", 0)
        rec = await pb.create("shop_products", {
            "slug": p["slug"], "name_id": p["name"][0], "name_en": p["name"][1],
            "summary_id": p["summary"][0], "summary_en": p["summary"][1],
            "description_id": f"{p['summary'][0]}\n\n- Jahitan rapi, finishing premium\n- Tersedia untuk seluruh anggota keluarga\n"
                              "- Cek tabel ukuran atau tanya kami via WhatsApp",
            "description_en": f"{p['summary'][1]}\n\n- Neat stitching, premium finish\n- Available for the whole family\n"
                              "- Check the size chart or ask us on WhatsApp",
            "material_id": "Katun premium, adem dan menyerap keringat.", "material_en": "Premium cotton, breathable.",
            "care_id": "Cuci tangan air dingin, jangan diperas, setrika suhu sedang.",
            "care_en": "Hand wash cold, don't wring, iron on medium.",
            "category": cats[p["category"]]["id"], "collections": [colls[c]["id"] for c in p["collections"]],
            "tags": p["tags"], "status": "live", "stock_mode": p["mode"], "preorder_days": p.get("preorder_days", 0),
            "cuts": list(p["prices"]), "cut_prices": p["prices"],
            "colors": [{"key": k, "name_id": a, "name_en": b, "hex": h} for k, a, b, h in p["colors"]],
            "media": keys, "size_charts": [], "sale_percent": sale,
            "sale_start": "", "sale_end": "", "featured": p.get("featured", False), "sort": n, "demo": True,
        })
        if sale:
            from datetime import datetime, timedelta, timezone  # noqa: PLC0415
            end = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S.000Z")
            await pb.update("shop_products", rec["id"], {"sale_end": end})
        for cut in p["prices"]:
            for size in catalog.sizes_for_cut(cut):
                for color in [c[0] for c in p["colors"]]:
                    stock = SIZE_STOCK.get(size, random.choice([3, 5, 8])) if p["mode"] == "ready" else 0
                    if p["mode"] == "ready" and random.random() < 0.08:
                        stock = 0
                    await pb.create("shop_variants", {"product": rec["id"], "cut": cut, "size": size, "color": color,
                                                      "stock": stock, "sku": "", "active": True})
        print("created", p["slug"], len(keys), "images")

    # Collection + category images from their products; home sections; a lookbook and a journal post.
    for slug, coll in colls.items():
        prod = next((p for p in PRODUCTS if slug in p["collections"]), None)
        if prod and first_image.get(prod["slug"]):
            await pb.update("shop_collections", coll["id"], {"image": first_image[prod["slug"]]})
    if not await pb.first("shop_lookbooks", "slug = 'keluarga-di-rumah'"):
        blocks = []
        for p in PRODUCTS[:4]:
            key = first_image.get(p["slug"])
            prod = await pb.first("shop_products", f"slug = {q(p['slug'])}")
            if key and prod:
                blocks.append({"image": key, "caption_id": p["summary"][0], "caption_en": p["summary"][1],
                               "products": [prod["id"]]})
        await pb.create("shop_lookbooks", {"slug": "keluarga-di-rumah", "title_id": "Serasi di Rumah",
                                           "title_en": "Matching at Home", "intro_id": "Cerita kecil tentang keluarga yang tampil serasi — dari pagi santai sampai hari raya.",
                                           "intro_en": "Small stories of families dressed alike — from slow mornings to festive days.",
                                           "cover": first_image.get("kurta-gamis-ivory-raya", ""), "blocks": blocks,
                                           "status": "live", "sort": 0})
    if not await pb.first("shop_posts", "slug = 'tips-foto-keluarga-serasi'"):
        await pb.create("shop_posts", {
            "slug": "tips-foto-keluarga-serasi", "title_id": "5 Tips Foto Keluarga dengan Baju Serasi",
            "title_en": "5 Tips for Family Photos in Matching Outfits",
            "excerpt_id": "Warna, motif, dan pose supaya foto keluarga terlihat rapi dan hangat.",
            "excerpt_en": "Colours, patterns and poses for tidy, warm family photos.",
            "body_id": "## 1. Pilih satu warna utama\nSatu warna dasar membuat semua orang terlihat satu tim.\n\n"
                       "## 2. Motif di satu bagian saja\nKalau ayah memakai batik penuh, anak bisa memakai aksen.\n\n"
                       "## 3. Ukuran yang pas\nCek tabel ukuran untuk setiap anggota — terutama anak yang cepat tumbuh.\n\n"
                       "## 4. Cahaya pagi atau sore\nCahaya lembut membuat warna kain terlihat asli.\n\n"
                       "## 5. Biarkan anak bergerak\nFoto terbaik sering muncul saat semua tertawa.",
            "body_en": "## 1. Pick one main colour\nOne base colour makes everyone look like a team.\n\n"
                       "## 2. Pattern in one place\nIf dad wears full batik, the kids can wear an accent.\n\n"
                       "## 3. Get the sizes right\nCheck the size chart for everyone — especially fast-growing kids.\n\n"
                       "## 4. Morning or late-afternoon light\nSoft light keeps fabric colours true.\n\n"
                       "## 5. Let the kids move\nThe best photos often happen when everyone laughs.",
            "cover": first_image.get("weekend-polo-terracotta", ""), "status": "live",
            "published_at": "2026-09-27 03:00:00.000Z", "tags": ["photo", "weekend"]})
    if not await pb.all("shop_home_sections", fields="id"):
        hero_img = first_image.get("batik-parang-sogan-family", "")
        sections = [
            ("hero", {"image": hero_img, "eyebrow_id": "Koleksi baru", "eyebrow_en": "New collection",
                      "title_id": "Serasi untuk semua yang kamu sayang", "title_en": "Matching for everyone you love",
                      "text_id": "Busana keluarga dan pasangan — dari batik hingga busana Raya, untuk setiap peran dan ukuran.",
                      "text_en": "Family and couple outfits — from batik to festive wear, for every role and size.",
                      "cta_id": "Belanja sekarang", "cta_en": "Shop now", "link": "/shop"}),
            ("sets", {}),
            ("products", {"mode": "featured"}),
            ("collection", {"collection": colls["lebaran-2027"]["id"]}),
            ("usp", {}),
            ("story", {"image": first_image.get("linen-sage-couple", ""), "title_id": "Dibuat untuk momen bersama",
                       "title_en": "Made for moments together",
                       "text_id": "Setiap potong dirancang dalam versi pria, wanita, dan anak — warna dan motif yang sama, "
                                  "potongan yang pas untuk masing-masing.",
                       "text_en": "Every piece is designed in men's, women's and kids' versions — the same colour and "
                                  "pattern, a cut that fits each person.",
                       "link": "/lookbook", "cta_id": "Lihat lookbook", "cta_en": "See the lookbook", "align": "left"}),
            ("products", {"mode": "new"}),
            ("categories", {}),
            ("lookbook", {}),
            ("reviews", {}),
        ]
        for i, (kind, data) in enumerate(sections):
            await pb.create("shop_home_sections", {"kind": kind, "data": data, "sort": i, "active": True})
    await pb.kv_set("demo_catalog", True)
    print("seed done")


async def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "images":
        await make_images()
    elif cmd == "seed":
        await seed()
    else:
        print(__doc__)
    await pb.close()


if __name__ == "__main__":
    asyncio.run(main())
