# Couple Suits — design

Online shop for **matching clothing for couples and whole families** (spouses, parents, kids, siblings), plus an
admin CMS with an **AI design studio** for the owner's wife. Decisions from the owner interview on 2026-09-27.
Repo `~/couple-suits` (working name); brand name and logo are entered later in the CMS.

## 1. Decisions

| Topic | Decision |
|---|---|
| Sites | **Storefront** `shop.bashir.my.id` (desktop + mobile web, installable PWA). **Admin CMS** `shop-admin.bashir.my.id` (installable PWA, push, Face ID lock). Move to a brand domain before launch. |
| Payments | **None.** Checkout creates an order; the owners contact the customer (manual WhatsApp chat via one-tap `wa.me` buttons in the CMS) to arrange payment and shipping. |
| Shop WhatsApp | **+62 851-2106-9097** (`6285121069097`) for `wa.me` chat buttons. |
| Order notifications | **Admin PWA push** (free) on new orders. No WhatsApp API: the official one costs per message; unofficial libraries (venom, Baileys) risk a ban and venom runs a full Chrome (too heavy). |
| Shipping | Customer gives the address; **shipping cost is confirmed by the admin** and added to the order in the CMS. |
| Sets | **Flexible "build your set"**: the customer adds any members with a role (spouse, dad, mom, son, daughter, sibling, baby, grandparent, custom) and a size each. A product declares which **cuts** exist (men, women, boys, girls, baby, unisex adult/kids) and which roles map to which cut. Single pieces are sold too. |
| Sizing | **Asian/Indonesian adult S–XXXL** + **kids by age** (1–2 y … 11–12 y, with height ranges); charts in cm (chest, length, waist, sleeve, etc.). |
| Stock | Per product: **Ready stock** (quantity per variant, auto sold-out) or **Pre-order** (production time, e.g. 14 days). |
| Accounts | **Optional** customer accounts (**email + password**, verification + reset emails). Guests can order. Customer accounts are a separate PocketBase auth collection, not the household `users`. |
| Personalization | **Family size profiles** (save each member: role, name, size, birthday), **"Complete the family set"** (one tap adds matching pieces for everyone saved), **wishlist**, **recently viewed**, **recommendations** ("families also bought", similar styles), **reviews with family photos**. |
| Promotions | **Voucher codes** (%/Rp, min. spend, limits, expiry), **family-set discount** (automatic by number of members), **flash sale / sale prices** with countdown, **special-day vouchers** (birthday/anniversary from family profiles). |
| Content (CMS) | **Homepage builder** (hero banners, featured collections, section order), **lookbook** (photo stories linked to products), **blog**, **pages** (FAQ, size guide, how to order, returns, **privacy policy** for UU PDP). Plus products, categories/collections, orders, customers, reviews moderation, promos, settings (brand name, logo, colors, WhatsApp number). |
| Look | **Minimal premium** (clean white/black, lots of space, editorial photography; Uniqlo/Zara-like), bilingual. |
| Language | **Bahasa Indonesia** default + **English** switch; product/content fields in both (AI can draft the translation). |
| Analytics | **Built-in, privacy-friendly** (no cookies/banner): visits, top products, cart → order conversion, sources. Google Analytics / Meta Pixel can be added when running paid ads. |
| Admins | Owner + wife, full access (their existing accounts, role admin); Face ID lock. |

## 2. AI design studio

**Input:** hand sketches and/or detail crops (collar, buttons, waist shape, fabric, any detail), grouped in a
design board with notes, for any set of roles (e.g. dad + mom + daughter).

**Flow**
1. Upload / photograph sketches, crop details (in-browser cropper), write notes.
2. **Analyse** (free Gemini, text + vision): the AI describes garment type, silhouette, details and asks for
   anything missing; produces a structured design brief.
3. **Generate options** (image engine, see below): 4 concepts per round from the brief + up to 4 reference images.
   Iterate ("rounder collar", "shorter sleeves"), keep favourites, compare.
4. **Choose** one → the studio produces:
   - **Flat sketches front + back** per cut (men/women/kids), generated as images from the chosen concept;
   - **Family mockup** (the set worn together);
   - **Detail sheet (tech pack)**: components, fabric suggestions + weight, colours (hex/Pantone-like names),
     trims (buttons, zips), stitching/construction notes, **points of measure**, per-cut notes;
   - **Size charts per cut** (Asian adult S–XXXL, kids by age) from standard grading tables, adjusted for the
     design's fit; **editable** — must be checked against a real sample;
   - **PDF export** (server-side, `fpdf2`) to hand to a tailor/convection;
   - **"Turn into product"**: creates a draft product with cuts, sizes, size chart and images.
5. Everything is saved per design with history.

**Image engines (switchable in settings)**

| Engine | Inputs | Cost | Use |
|---|---|---|---|
| Cloudflare Workers AI **FLUX.2 [klein] 4B** | prompt + up to 4 reference images (≤512 px each) | free ~75–80 images/day (10k neurons), then ~$0.0014/image | **Default** |
| Cloudflare FLUX.2 [klein] 9B | same | ~6/day free, then ~$0.017/image | "High quality" button |
| Gemini app (Nano Banana 2) | many images | free ~20/day, manual | CMS prepares the prompt; she uploads results back |
| Gemini API Nano Banana 2 (Lite) | many images | ~$0.034–0.067/image, needs billing | Optional later |

Text/vision work (analysis, tech pack, size charts, translations) uses the existing **free Gemini** key.

**Verified 2026-09-27** (public-domain Connolly dress sketch + Peter Pan collar drawing + ticking-stripe fabric photo;
test files in `~/work/sketches/`, not for commercial use):
- Gemini (free) turned the three images into an accurate brief (1960s sheath dress, Peter Pan collar, cream ticking
  stripe, cream dome buttons) and a coherent family set (mom dress, dad club-collar shirt, daughter A-line dress).
- FLUX.2 [klein] 4B, 3 reference images, 4 seeds: all 4 options followed the sketch silhouette/pose, the collar, the
  fabric and the buttons. ~7–9 s per image.
- **Front/back technical flat** from the chosen option: excellent (collar, placket, waist band, pleats, back zip,
  dashed stitching).
- **Pitfall:** a reference image that contains a *person* makes the model copy that person (the "dad" became a woman).
  **Rule:** for other family members, pass only garment references (the flat sketch + fabric/detail crops) and
  describe the wearer in the prompt. With that, dad and a 6-year-old girl came out correct and matching on both 4B and
  9B (9B ~2.5 s but ~12× the neurons; 4B quality was as good or better here).
- Pipeline: brief (Gemini) → primary options from sketch + details → choose → flat front/back → each other role from
  flat + fabric → mockup board (composed from the role images) → tech pack + size charts (Gemini) → PDF.
Limits: AI output is a concept + draft spec. Sewing patterns still come from a pattern maker/tailor.
To verify first: FLUX.2 [klein] quality on real sketches (test before building the studio).

## 3. Architecture

```
Browser (shop) ──▶ Caddy ── shop.bashir.my.id ──▶ shop-web  (FastAPI + Jinja SSR, 127.0.0.1:8200, user shopweb)
                        │                          └─ /media/* static WebP images (Caddy, long cache)
Browser (CMS PWA) ─────▶ shop-admin.bashir.my.id ─▶ shop-admin (FastAPI API + static SPA, 127.0.0.1:8210, user shopadm)
                                                       ├─ Cloudflare Workers AI (FLUX.2) · Gemini (free)
                                                       └─ Web Push to admins
both ──▶ PocketBase (shared, collections `shop_*`, service-role rules)
```

- **Two services** so the public storefront can't write catalog/settings: `shop-web` (public pages, cart,
  checkout, customer accounts, reviews) and `shop-admin` (everything else + AI). Each ~80–100 MB.
- **Storefront is server-rendered** (fast first paint, SEO, works without JS) with small vanilla JS for the family
  builder, cart and wishlist; service worker for installability. Structured data (Product/Offer), sitemap, OG tags.
- **Images:** uploads are converted once into WebP sizes (e.g. 320/640/1080/1600) by `shop-admin` (Pillow) into
  `/var/lib/shop/media`, served by Caddy directly.
- **Email** (customer verification/reset, order confirmation): a free SMTP provider (e.g. Brevo 300/day). Requires
  DNS changes: SPF include + DKIM for the provider (today SPF is `-all`).
- **Security:** same pattern as the other apps (sandboxed units, strict CSP, httpOnly cookies, CSRF header,
  rate limits). Customer data minimal; privacy policy; admin separate subdomain + passkey lock.
- **Backups become mandatory** before launch (customer + order data): automated encrypted daily backups.

## 4. Data model (PocketBase, prefix `shop_`)

`shop_settings` (brand, logo, colours, WhatsApp number, texts) · `shop_categories` · `shop_collections` ·
`shop_products` (bilingual name/description, status draft/live, stock mode ready/preorder + lead days, base price,
sale price + window, cuts, tags, SEO) · `shop_variants` (product, cut, size, colour, stock, price override) ·
`shop_media` · `shop_size_charts` (cut → sizes × measurements) · `shop_customers` (auth) · `shop_family_members`
(customer, name, role, cut, size, birthday) · `shop_carts` · `shop_orders` (number, status new/confirmed/paid/
shipped/done/cancelled, customer or guest contact, address, items, discounts, shipping cost, notes, timeline) ·
`shop_order_items` (variant, role label, member name) · `shop_wishlist` · `shop_views` (recently viewed) ·
`shop_reviews` (+ photos, moderation) · `shop_vouchers` · `shop_set_discounts` · `shop_pages` · `shop_posts` ·
`shop_lookbooks` · `shop_home_sections` · `shop_stats_daily` · `shop_designs` (+ `shop_design_inputs`,
`shop_design_rounds`, `shop_design_outputs`) · `shop_push_subs` · `shop_admin_passkeys`.

## 5. Build phases

1. **Catalog + orders:** schema, media pipeline, CMS products/categories/stock/size charts, storefront browse +
   product page with family builder, cart, guest checkout → order, admin push, order management + `wa.me` buttons.
2. **Customers + growth:** accounts + email, family profiles, complete-the-set, wishlist, recently viewed,
   recommendations, reviews, promos (vouchers, set discount, flash sale, special-day), content (homepage builder,
   lookbook, blog, pages), bilingual, built-in analytics.
3. **AI design studio** (after testing FLUX.2 [klein] on real sketches).
4. **Launch polish:** SEO, performance, optional Cloudflare CDN, backups, brand domain.

## 6. Needed from the owner (when we get there)

- ~~Free Cloudflare account + Workers AI API token~~ **done 2026-09-27** (`/etc/couple-suits/env`: CF_ACCOUNT_ID, CF_API_TOKEN).
- Free **Brevo** account for customer emails; DNS changes for SPF/DKIM — **postponed by the owner** (phase 2).
- ~~Shop WhatsApp number~~ done (6285121069097). Brand name/logo later, in the CMS.
- ~~Test sketches~~ tested with public-domain sketches instead (see §2). Real sketches from his wife welcome later.
- Product photos for real listings.
