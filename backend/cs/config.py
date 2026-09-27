"""Settings from the environment (systemd EnvironmentFile per service)."""

import os
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Jakarta")

PB_URL = os.environ.get("CS_PB_URL", "http://127.0.0.1:8090")
PB_USER = os.environ.get("CS_PB_USER", "")
PB_PASSWORD = os.environ.get("CS_PB_PASSWORD", "")

SHOP_URL = os.environ.get("CS_SHOP_URL", "https://shop.bashir.my.id")
ADMIN_URL = os.environ.get("CS_ADMIN_URL", "https://shop-admin.bashir.my.id")
RP_ID = os.environ.get("CS_RP_ID", "shop-admin.bashir.my.id")

MEDIA_DIR = os.environ.get("CS_MEDIA_DIR", "/var/lib/couple-suits/media")     # public images (Caddy serves /media)
STATE_DIR = os.environ.get("CS_STATE_DIR", "/var/lib/couple-suits-admin")     # private: VAPID key, studio files

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_FAST_MODEL = os.environ.get("CS_GEMINI_FAST_MODEL", "gemini-3.1-flash-lite")
GEMINI_SMART_MODEL = os.environ.get("CS_GEMINI_SMART_MODEL", "gemini-3.5-flash")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")

LOCK_IDLE_SECONDS = int(os.environ.get("CS_LOCK_IDLE_SECONDS", "600"))
DEV = os.environ.get("CS_DEV", "") == "1"
