#!/usr/bin/env bash
# One-time (re-runnable) setup of Couple Suits secrets. Prints no secrets.
#  - creates the PocketBase machine logins svc_shopweb (role shop_web) and svc_shopadmin (role shop_admin)
#    with random 48-character passwords;
#  - writes /etc/couple-suits/web.env (root:shopweb 640) and admin.env (root:shopadm 640);
#  - moves the Cloudflare keys from /etc/couple-suits/env and copies the Gemini key from /etc/finance/env.
set -euo pipefail
PB="/opt/pocketbase/pocketbase"
PBARGS=(--dir /var/lib/pocketbase/pb_data --hooksDir /var/lib/pocketbase/pb_hooks --migrationsDir /var/lib/pocketbase/pb_migrations)

make_login() {  # $1 username, $2 role → prints password on stdout (captured, never shown)
  local pass cred
  pass="$(openssl rand -hex 24)"
  cred="$(sudo mktemp /tmp/cs-XXXXXX.cred)"
  printf '%s\n%s\n' "$1" "$pass" | sudo tee "$cred" >/dev/null
  sudo chown pocketbase "$cred"
  sudo -u pocketbase "$PB" shop-service "$cred" "$2" "${PBARGS[@]}" >&2
  sudo shred -u "$cred"
  printf '%s' "$pass"
}

get() { sudo grep -E "^$1=" "$2" 2>/dev/null | head -1 | cut -d= -f2- || true; }

WEB_PASS="$(make_login svc_shopweb shop_web)"
ADM_PASS="$(make_login svc_shopadmin shop_admin)"
CF_ACCOUNT_ID="$(get CF_ACCOUNT_ID /etc/couple-suits/env)"; CF_ACCOUNT_ID="${CF_ACCOUNT_ID:-$(get CF_ACCOUNT_ID /etc/couple-suits/admin.env)}"
CF_API_TOKEN="$(get CF_API_TOKEN /etc/couple-suits/env)"; CF_API_TOKEN="${CF_API_TOKEN:-$(get CF_API_TOKEN /etc/couple-suits/admin.env)}"
GEMINI="$(get GEMINI_API_KEY /etc/finance/env)"

sudo install -d -o root -g root -m 755 /etc/couple-suits
umask 077
printf 'CS_PB_USER=svc_shopweb\nCS_PB_PASSWORD=%s\n' "$WEB_PASS" | sudo tee /etc/couple-suits/web.env >/dev/null
printf 'CS_PB_USER=svc_shopadmin\nCS_PB_PASSWORD=%s\nCF_ACCOUNT_ID=%s\nCF_API_TOKEN=%s\nGEMINI_API_KEY=%s\n' \
  "$ADM_PASS" "$CF_ACCOUNT_ID" "$CF_API_TOKEN" "$GEMINI" | sudo tee /etc/couple-suits/admin.env >/dev/null
sudo chown root:shopweb /etc/couple-suits/web.env && sudo chmod 640 /etc/couple-suits/web.env
sudo chown root:shopadm /etc/couple-suits/admin.env && sudo chmod 640 /etc/couple-suits/admin.env
[ -f /etc/couple-suits/env ] && [ -n "$CF_API_TOKEN" ] && sudo shred -u /etc/couple-suits/env
echo "secrets ready: web.env, admin.env (CF: $([ -n "$CF_API_TOKEN" ] && echo yes || echo NO), Gemini: $([ -n "$GEMINI" ] && echo yes || echo NO))"
