"""Small helpers shared by both shop services."""

from __future__ import annotations

import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime
from urllib.parse import quote as urlquote

from fastapi import HTTPException
from markdown_it import MarkdownIt

from . import config

PB_ID = re.compile(r"^[a-z0-9]{15}$")


def rid(value: str) -> str:
    """A PocketBase record id from a URL, or 404."""
    if not PB_ID.match(value or ""):
        raise HTTPException(404, "Not found.")
    return value


def slugify(text: str, max_len: int = 80) -> str:
    s = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].strip("-") or secrets.token_hex(3)


def new_key(n: int = 10) -> str:
    """Random id for media folders and tokens (lowercase letters + digits)."""
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def now_local() -> datetime:
    return datetime.now(config.TZ)


def today() -> str:
    return now_local().strftime("%Y-%m-%d")


def pb_now() -> str:
    """UTC timestamp in PocketBase's format."""
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000Z")


# ---------------------------------------------------------------------------
# Phone numbers and WhatsApp links
# ---------------------------------------------------------------------------

def normalize_phone(raw: str) -> str:
    """Indonesian numbers to international digits: 0812… / +62 812… / 812… → 62812…"""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    return digits


def valid_phone(digits: str) -> bool:
    return 9 <= len(digits) <= 15


def wa_link(phone: str, text: str = "") -> str:
    url = f"https://wa.me/{normalize_phone(phone)}"
    return f"{url}?text={urlquote(text)}" if text else url


# ---------------------------------------------------------------------------
# Markdown for pages, posts and product descriptions (no raw HTML allowed)
# ---------------------------------------------------------------------------

_md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": True}).enable("table")


def markdown(text: str) -> str:
    return _md.render(text or "")


def plain(text: str, limit: int = 160) -> str:
    """Markdown → short plain text (meta descriptions, previews)."""
    s = re.sub(r"[#*_>`\[\]()|-]+", " ", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 1].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# Rate limiting (in memory, per process)
# ---------------------------------------------------------------------------

class Window:
    def __init__(self, limit: int, seconds: float):
        self.limit, self.seconds = limit, seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.seconds:
            q.popleft()
        if len(q) >= self.limit:
            return False, int(self.seconds - (now - q[0])) + 1
        q.append(now)
        if len(self.hits) > 20000:
            for k in list(self.hits)[:5000]:
                self.hits.pop(k, None)
        return True, 0

    def check(self, key: str, message: str = "Too many requests."):
        ok, wait = self.allow(key)
        if not ok:
            raise HTTPException(429, {"error": f"{message} ({wait}s)", "retry_after": wait})


# ---------------------------------------------------------------------------
# Shop settings (kv "settings"), cached briefly
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "brand_name": "Couple Suits",
    "tagline_id": "Busana serasi untuk pasangan & keluarga",
    "tagline_en": "Matching outfits for couples & families",
    "logo": "",
    "accent": "#1c1b19",
    "whatsapp": "6285121069097",
    "instagram": "",
    "tiktok": "",
    "email": "",
    "city": "",
    "announcement_id": "Gratis konsultasi ukuran via WhatsApp",
    "announcement_en": "Free size advice on WhatsApp",
    "payment_info_id": "Kami akan menghubungi kamu via WhatsApp untuk konfirmasi ongkir dan pembayaran.",
    "payment_info_en": "We'll contact you on WhatsApp to confirm shipping and payment.",
    "shipping_note_id": "Ongkos kirim dikonfirmasi admin setelah pesanan dibuat.",
    "shipping_note_en": "Shipping cost is confirmed by us after you order.",
    "special_voucher_percent": 10,
    "special_voucher_days": 14,
    "wa_templates": {},
}

_settings_cache: tuple[float, dict] = (0.0, {})


async def settings(fresh: bool = False) -> dict:
    global _settings_cache
    from .pb import pb  # noqa: PLC0415
    if not fresh and time.monotonic() - _settings_cache[0] < 30:
        return _settings_cache[1]
    stored = await pb.kv_get("settings", {}) or {}
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in stored.items() if v is not None}}
    _settings_cache = (time.monotonic(), merged)
    return merged


def forget_settings():
    global _settings_cache
    _settings_cache = (0.0, {})
