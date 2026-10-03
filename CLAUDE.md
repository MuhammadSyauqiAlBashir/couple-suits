# Couple Suits (shop) — Claude context

Matching clothing for couples and whole families (spouses, parents, kids, siblings): storefront, admin CMS PWA and
an AI design studio for the wife's designs. Owner: Bashir (admin username `bashirsyauqi`); his wife `bells` is an
admin too. Storefront https://shop.bashir.my.id · Admin https://shop-admin.bashir.my.id.

Read `README.md` (layout, deploy, operations, AI limits) and `docs/DESIGN.md` (§0 as-built status, §1 decisions,
§2 AI studio, data model) before deeper work. Server-wide facts are in `~/.claude/CLAUDE.md`.

## Rules for working on this app

- Not open to real customers yet (demo catalog only). **Once real orders/customers exist, treat their data like
  the finance app: ask the owner before changing or deleting any `shop_*` records and explain the impact.**
  Customer data (names, phone numbers, addresses) must never be printed into chat or commits.
- Never print secrets (PocketBase service passwords, Cloudflare token, Gemini key).
- Owner prefers step-by-step, click-by-click guidance; budget-conscious; highest reasonable security.
- Git: work on `develop`; commit with `-c user.name="Bashir" -c user.email="bashirsyauqi@gmail.com"`. Push to
  `origin/develop` only when the owner asks (he asked on 2026-10-03). No PRs to `main` unless asked.
- After every deploy: `systemctl is-active pocketbase shop-web shop-admin`.
- Anything billable (paid AI models, email service plans) needs the owner's OK first.

## Server facts

| Item | Value |
|---|---|
| Storefront | `shop-web.service` (FastAPI + Jinja SSR), user `shopweb`, 127.0.0.1:8200 |
| Admin API | `shop-admin.service`, user `shopadm`, 127.0.0.1:8210; static PWA `/srv/couple-suits-admin`; StateDirectory `/var/lib/couple-suits-admin` (VAPID key + private studio files `studio/`) |
| Code | `/opt/couple-suits/{cs,shopweb,shopadmin,venv}`; both units sandboxed, `Restart=always`, `UMask=0002`, group `couplesuits`; only writable dir `/var/lib/couple-suits/media` (2775, WebP sizes; Caddy serves `/media`) |
| Secrets | `/etc/couple-suits/web.env` (`root:shopweb 640`: `CS_PB_USER`, `CS_PB_PASSWORD`); `/etc/couple-suits/admin.env` (`root:shopadm 640`: `CS_PB_USER`, `CS_PB_PASSWORD`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `GEMINI_API_KEY`). Created by `deploy/setup-secrets.sh` (prints no secrets) |
| Data | PocketBase (shared), `shop_*` collections; machine logins `svc_shopweb` (role `shop_web`), `svc_shopadmin` (role `shop_admin`) via the `shop-service` PB CLI command; `pb.bashir.my.id` 404s `/api/collections/shop_*` |
| Caddy | `deploy/Caddyfile.shop`: strict CSP (shop allows inline styles only); storefront camera/mic off; admin `camera=(self)` + passkeys. Backup before adding: `~/work/Caddyfile.bak-shop-2026-09-27` |
| Snapshot | PB before the shop migration: `~/work/pb-before-shop-2026-09-27.db` (root 600) |
| Deploy | `./deploy/deploy.sh` (`SKIP_PB_RESTART=1` to skip PocketBase restart) |
| Tests | `~/work/cs-venv/bin/python -m pytest tests` |
| Dev | scratch PB `~/work/pb/cs2` (:8094, owner/wife test logins), `~/work/cs-run.sh` / `cs-restart.sh web|admin` (:8201/:8211, `CS_DEV=1`), screenshots `~/work/cs_shots.py`, `csa_shots.py`, `cs_live.py`, studio test `~/work/studio_e2e.py` |

## Features (as built 2026-09-27)

- Storefront: family set builder (roles → cuts → sizes, presets, "use my family profile"); cart in localStorage +
  server re-pricing; guest checkout → order page with secret token + WhatsApp button (owner's WhatsApp
  6285121069097); optional accounts (email + password, family sizes, wishlist, vouchers); reviews with photos
  (moderated); vouchers; family-set discount (3+ people 5 %, 5+ people 10 %); sale with countdown; special-day
  vouchers (7 days before a birthday/anniversary for customers who allow offers); homepage builder; pages
  (privacy policy **draft to review**); journal; lookbook; bilingual ID/EN; cookie-free analytics (`shop_stats`,
  daily-rotating salted hash); SEO (sitemap, JSON-LD); installable PWA.
- Admin: owner (role admin) + admins by username (kv `admin_usernames`, `bells` pre-added); push on new orders
  (polls `notified=false` every 15 s); 08:00 special-day vouchers; 09:00 digest; WhatsApp message templates per
  order; customer password reset via admin (no email yet); Face ID lock.
- **AI studio** (tested end to end 2026-09-27, ~4 min): Gemini brief → FLUX.2 klein 4B options (sketch + detail
  refs) → flats front/back → other family roles from the flat + fabric crops only → Pillow family board → tech pack
  (Gemini) + size charts graded from the default Asian tables (not free-form AI numbers) → fpdf2 PDF → draft
  product. Inputs: unlimited uploads (≤25 MB each), but analyse uses the first 6; options = first sketch + first 3
  details; flats = chosen + first 2 details; family = front flat + first 3 details (earliest uploaded first).
- Demo catalog: 8 products with FLUX photos (`demo=true`), `tools/demo_catalog.py`; remove in Settings.
- Email (Brevo): **postponed by the owner** (SPF merge + DKIM needed later).

## AI limits (free) and sharing

- **Cloudflare Workers AI** (account shared with BashGames): 10,000 neurons/day, resets 07:00 WIB. FLUX.2 klein 4B
  ≈ 126 neurons/image → ~75–80 images/day; HQ (klein 9B) counts ≈ 12×. Usage counter kv `flux:<date>` ("Images
  today" in the studio). One full studio design ≈ 8–10 images. **BashGames uses the same account** as a backup
  photo judge, capped at 2,000 neurons/day (bg_kv `cf_neurons:<date>`), so ≥ ~63 images/day stay for the shop.
- **Gemini** (free, key copied from finance): per-model daily limits, reset 14:00 WIB (15:00 in winter); shared
  with finance and BashGames; `cs/ai.py` falls back across models.
- If Google/Cloudflare retire a model, update the names in `cs/ai.py` / `cs/flux.py`. The Cloudflare token and
  Gemini key have no expiry.

## History

- 2026-09-27 — All four phases built and deployed; studio verified; docs (AI limits, studio inputs, renewals).
- 2026-09-27 — Machine-login roles (`shop_web`, `shop_admin`) added; lyrsync/finance patched to reject them.

## Open owner tasks

- [ ] Install the admin app on both iPhones (Safari → shop-admin → log in → Share → Add to Home Screen), then
      Settings → "Turn on order notifications" + "Set up Face ID lock".
- [ ] Settings: brand name, logo, bank details (used in the WhatsApp confirmation), Instagram/TikTok.
- [ ] Review the privacy-policy draft (Content → Pages → Kebijakan privasi) and write "Tentang kami".
- [ ] Place a test order → push arrives → try the WhatsApp buttons → cancel it (stock returns).
- [ ] Real products + photos (or via the AI studio from the wife's sketches), then Settings → Remove demo catalog.
- [ ] Brevo email (postponed).
- [ ] **Before real customers:** automated encrypted backups (server-wide plan in `~/.claude/CLAUDE.md`).
