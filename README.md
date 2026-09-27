# couple-suits

Matching clothing for couples and whole families (spouses, parents, kids, siblings): a storefront, an admin CMS
PWA, and an AI design studio. Design and all decisions: [docs/DESIGN.md](docs/DESIGN.md).

| | URL | Service |
|---|---|---|
| Storefront | https://shop.bashir.my.id | `shop-web` (FastAPI + Jinja SSR) on 127.0.0.1:8200, user `shopweb` |
| Admin CMS (PWA) | https://shop-admin.bashir.my.id | `shop-admin` (FastAPI API) on 127.0.0.1:8210, user `shopadm`; static app in `/srv/couple-suits-admin` |
| Data | PocketBase (shared), collections `shop_*` | machine logins `svc_shopweb` (role `shop_web`) / `svc_shopadmin` (role `shop_admin`) |

## Layout

| Path | What |
|---|---|
| `backend/cs/` | Shared: config, PocketBase client, catalog vocabulary (cuts, sizes, roles, default Asian size charts), pricing (sale, family-set discount, vouchers), media pipeline (WebP sizes), Gemini + Cloudflare FLUX clients, fonts |
| `backend/shopweb/` | Storefront: pages, family set builder, cart/checkout API, customer accounts, reviews, analytics, templates + static (CSS/JS/fonts/icons) |
| `backend/shopadmin/` | Admin API: auth + Face ID lock, push, dashboard, products/stock/media, orders + WhatsApp templates, customers, reviews, content, scheduler, AI studio |
| `admin-ui/` | Admin PWA (plain ES modules) |
| `pb_migrations/`, `pb_hooks/` | `shop_*` schema and the `shop-service` CLI command |
| `deploy/` | `deploy.sh`, `setup-secrets.sh` (one-time), systemd units, Caddy site blocks |
| `tools/` | `demo_catalog.py` (AI demo products), `make_icons.py` |
| `tests/` | `python -m pytest tests` |

## Deploy

    ./deploy/deploy.sh            # SKIP_PB_RESTART=1 to skip the PocketBase restart
    systemctl is-active pocketbase shop-web shop-admin

First install only: `./deploy/setup-secrets.sh` (creates the service logins and `/etc/couple-suits/{web,admin}.env`;
prints no secrets), then `./deploy/deploy.sh` again. Caddy blocks: `deploy/Caddyfile.shop`.

## Local development

Scratch PocketBase + both services on other ports (see `~/work/cs-run.sh`, `~/work/cs-restart.sh`):
`CS_DEV=1` makes the apps serve `/static`, `/media` and the admin UI themselves and relaxes cookie `Secure`.

## Operations

- Admins: the owner (role `admin`) always; others are added by username in Settings (kv `admin_usernames`).
- New orders → push to admins within ~15 s (the admin service polls `notified=false`). 08:00 special-day vouchers,
  09:00 digest.
- Customer password reset (no email yet): Customers → Set a new password → send on WhatsApp.
- Demo catalog: `tools/demo_catalog.py images|seed`; remove in Settings → Remove demo catalog.
- Studio files are private in `/var/lib/couple-suits-admin/studio/`; public images in `/var/lib/couple-suits/media/`.
