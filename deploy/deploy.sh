#!/usr/bin/env bash
# Deploy Couple Suits from this repo. Safe to re-run.
#   backend   -> /opt/couple-suits (root-owned; runs as shopweb / shopadm)
#   admin app -> /srv/couple-suits-admin (static, served by Caddy)
#   media     -> /var/lib/couple-suits/media (group couplesuits, served by Caddy at /media)
#   pb files  -> /var/lib/pocketbase/{pb_migrations,pb_hooks} (applied on PocketBase restart)
# First time: run deploy/setup-secrets.sh after this (creates the env files and service logins).
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo dev)-$(date +%Y%m%d%H%M%S)"
echo "==> couple-suits $VERSION"

getent group couplesuits >/dev/null || sudo groupadd --system couplesuits
for u in shopweb shopadm; do
  id "$u" >/dev/null 2>&1 || sudo useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin "$u"
  sudo usermod -aG couplesuits "$u"
done

echo "==> backend"
sudo install -d -o root -g root -m 755 /opt/couple-suits
[ -x /opt/couple-suits/venv/bin/python ] || sudo python3 -m venv /opt/couple-suits/venv
sudo /opt/couple-suits/venv/bin/pip install --quiet --disable-pip-version-check -r backend/requirements.txt
for pkg in cs shopweb shopadmin; do
  sudo rsync -a --delete --chown=root:root --chmod=D755,F644 --exclude __pycache__ "backend/$pkg/" "/opt/couple-suits/$pkg/"
done
sudo install -o root -g root -m 644 deploy/shop-web.service /etc/systemd/system/shop-web.service
sudo install -o root -g root -m 644 deploy/shop-admin.service /etc/systemd/system/shop-admin.service

echo "==> folders"
sudo install -d -o root -g root -m 755 /var/lib/couple-suits
sudo install -d -o shopadm -g couplesuits -m 2775 /var/lib/couple-suits/media
sudo install -d -o root -g root -m 755 /etc/couple-suits
[ -f /etc/couple-suits/web.env ] && sudo chown root:shopweb /etc/couple-suits/web.env && sudo chmod 640 /etc/couple-suits/web.env
[ -f /etc/couple-suits/admin.env ] && sudo chown root:shopadm /etc/couple-suits/admin.env && sudo chmod 640 /etc/couple-suits/admin.env

echo "==> admin app"
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT
cp -r admin-ui/. "$STAGE/"
{ grep -rl __VERSION__ "$STAGE" || true; } | xargs -r sed -i "s/__VERSION__/$VERSION/g"
sudo install -d -o root -g root -m 755 /srv/couple-suits-admin
sudo rsync -a --delete --chown=root:root --chmod=D755,F644 "$STAGE/" /srv/couple-suits-admin/

echo "==> pocketbase migrations + hooks"
sudo install -C -o pocketbase -g pocketbase -m 640 pb_migrations/*.js /var/lib/pocketbase/pb_migrations/
sudo install -C -o pocketbase -g pocketbase -m 640 pb_hooks/*.js /var/lib/pocketbase/pb_hooks/

echo "==> restart"
sudo systemctl daemon-reload
if [ "${SKIP_PB_RESTART:-0}" != 1 ]; then sudo systemctl restart pocketbase; sleep 2; fi
if [ -f /etc/couple-suits/web.env ] && [ -f /etc/couple-suits/admin.env ]; then
  sudo systemctl enable --quiet shop-web shop-admin
  sudo systemctl restart shop-admin shop-web
  for i in $(seq 30); do curl -fsS http://127.0.0.1:8210/api/health >/dev/null 2>&1 && curl -fsS -o /dev/null http://127.0.0.1:8200/healthz 2>/dev/null && break; sleep 1; done
  curl -fsS http://127.0.0.1:8210/api/health && echo " admin ok"
  curl -fsS http://127.0.0.1:8200/healthz && echo " web ok"
else
  echo "!! env files missing: run deploy/setup-secrets.sh"
fi
systemctl is-active pocketbase
echo "==> done: $VERSION"
