"""Shop vocabulary: garment cuts, sizes, family roles, and product helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from . import config

# A cut is the garment pattern a product is made in. Products list the cuts they offer.
CUTS: dict[str, dict] = {
    "men": {"id": "Pria", "en": "Men", "group": "adult"},
    "women": {"id": "Wanita", "en": "Women", "group": "adult"},
    "unisex_adult": {"id": "Dewasa (unisex)", "en": "Adult (unisex)", "group": "adult"},
    "boys": {"id": "Anak laki-laki", "en": "Boys", "group": "kids"},
    "girls": {"id": "Anak perempuan", "en": "Girls", "group": "kids"},
    "unisex_kids": {"id": "Anak (unisex)", "en": "Kids (unisex)", "group": "kids"},
    "baby": {"id": "Bayi", "en": "Baby", "group": "baby"},
}

# Asian/Indonesian sizing: adults S–XXXL, kids by age, babies by months.
SIZES: dict[str, list[str]] = {
    "adult": ["S", "M", "L", "XL", "XXL", "XXXL"],
    "kids": ["1-2Y", "3-4Y", "5-6Y", "7-8Y", "9-10Y", "11-12Y"],
    "baby": ["0-6M", "6-12M", "12-18M", "18-24M"],
}
SIZE_LABEL = {
    "id": {"1-2Y": "1–2 th", "3-4Y": "3–4 th", "5-6Y": "5–6 th", "7-8Y": "7–8 th", "9-10Y": "9–10 th", "11-12Y": "11–12 th",
           "0-6M": "0–6 bln", "6-12M": "6–12 bln", "12-18M": "12–18 bln", "18-24M": "18–24 bln"},
    "en": {"1-2Y": "1–2 y", "3-4Y": "3–4 y", "5-6Y": "5–6 y", "7-8Y": "7–8 y", "9-10Y": "9–10 y", "11-12Y": "11–12 y",
           "0-6M": "0–6 m", "6-12M": "6–12 m", "12-18M": "12–18 m", "18-24M": "18–24 m"},
}

# Family roles a customer can pick in "build your set", with the cuts that suit them (best first).
ROLES: dict[str, dict] = {
    "dad": {"id": "Ayah", "en": "Dad", "cuts": ["men", "unisex_adult"]},
    "mom": {"id": "Ibu", "en": "Mom", "cuts": ["women", "unisex_adult"]},
    "husband": {"id": "Suami", "en": "Husband", "cuts": ["men", "unisex_adult"]},
    "wife": {"id": "Istri", "en": "Wife", "cuts": ["women", "unisex_adult"]},
    "son": {"id": "Anak laki-laki", "en": "Son", "cuts": ["boys", "unisex_kids", "baby"]},
    "daughter": {"id": "Anak perempuan", "en": "Daughter", "cuts": ["girls", "unisex_kids", "baby"]},
    "brother": {"id": "Kakak/adik laki-laki", "en": "Brother", "cuts": ["boys", "men", "unisex_kids", "unisex_adult"]},
    "sister": {"id": "Kakak/adik perempuan", "en": "Sister", "cuts": ["girls", "women", "unisex_kids", "unisex_adult"]},
    "baby": {"id": "Bayi", "en": "Baby", "cuts": ["baby", "unisex_kids"]},
    "grandpa": {"id": "Kakek", "en": "Grandpa", "cuts": ["men", "unisex_adult"]},
    "grandma": {"id": "Nenek", "en": "Grandma", "cuts": ["women", "unisex_adult"]},
    "other": {"id": "Lainnya", "en": "Other", "cuts": list(CUTS)},
}

# Quick presets for the family builder.
PRESETS = {
    "couple": {"id": "Pasangan", "en": "Couple", "roles": ["husband", "wife"]},
    "family3": {"id": "Keluarga (3)", "en": "Family of 3", "roles": ["dad", "mom", "daughter"]},
    "family4": {"id": "Keluarga (4)", "en": "Family of 4", "roles": ["dad", "mom", "son", "daughter"]},
    "mom_daughter": {"id": "Ibu & anak", "en": "Mom & daughter", "roles": ["mom", "daughter"]},
    "dad_son": {"id": "Ayah & anak", "en": "Dad & son", "roles": ["dad", "son"]},
    "siblings": {"id": "Kakak-adik", "en": "Siblings", "roles": ["brother", "sister"]},
}


def sizes_for_cut(cut: str) -> list[str]:
    return SIZES[CUTS[cut]["group"]] if cut in CUTS else []


def size_label(size: str, lang: str = "id") -> str:
    return SIZE_LABEL.get(lang, {}).get(size, size)


def label(d: dict, key: str, lang: str) -> str:
    item = d.get(key) or {}
    return item.get(lang) or item.get("id") or key


def tr(rec: dict, field: str, lang: str) -> str:
    """Bilingual record field: `<field>_<lang>` with Indonesian fallback."""
    return (rec.get(f"{field}_{lang}") or rec.get(f"{field}_id") or rec.get(f"{field}_en") or "").strip()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_pb_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None


def sale_active(product: dict, at: datetime | None = None) -> bool:
    pct = int(product.get("sale_percent") or 0)
    if pct <= 0:
        return False
    at = at or now_utc()
    start, end = parse_pb_date(product.get("sale_start")), parse_pb_date(product.get("sale_end"))
    return (not start or start <= at) and (not end or at <= end)


def round_price(x: float) -> int:
    """Rupiah prices round to Rp100."""
    return int(round(x / 100.0)) * 100


def cut_price(product: dict, cut: str) -> tuple[int, int]:
    """(regular, current) price for a cut; current applies an active sale."""
    base = int((product.get("cut_prices") or {}).get(cut) or 0)
    if base and sale_active(product):
        return base, round_price(base * (100 - int(product["sale_percent"])) / 100)
    return base, base


def price_range(product: dict) -> tuple[int, int, int, int]:
    """(min_current, max_current, min_regular, max_regular) over the product's cuts."""
    cur, reg = [], []
    for cut in product.get("cuts") or []:
        r, c = cut_price(product, cut)
        if r:
            reg.append(r)
            cur.append(c)
    if not cur:
        return 0, 0, 0, 0
    return min(cur), max(cur), min(reg), max(reg)


def media_url(key: str, width: int = 800) -> str:
    return f"/media/{key}/{width}.webp" if key else ""


MEDIA_WIDTHS = [400, 800, 1200, 1800]


def srcset(key: str) -> str:
    return ", ".join(f"/media/{key}/{w}.webp {w}w" for w in MEDIA_WIDTHS) if key else ""


def rupiah(n: int | float | None) -> str:
    n = int(n or 0)
    return ("−" if n < 0 else "") + "Rp" + f"{abs(n):,}".replace(",", ".")


def set_types(product: dict) -> list[str]:
    """Which kinds of sets a product can make, for filters: couple / family / kids."""
    groups = {CUTS[c]["group"] for c in (product.get("cuts") or []) if c in CUTS}
    out = []
    if "adult" in groups:
        out.append("couple")
    if "adult" in groups and (groups & {"kids", "baby"}):
        out.append("family")
    if groups & {"kids", "baby"}:
        out.append("kids")
    return out


TZ = config.TZ


# ---------------------------------------------------------------------------
# Default size charts (Asian/Indonesian, garment measurements in cm). Seeded
# into shop_size_charts named "Default …"; the admin edits them per product line.
# ---------------------------------------------------------------------------

def _chart(name: str, cut: str, cols: list[tuple[str, str, str]], sizes: list[str], values: dict[str, list],
           heights: list[str] | None = None) -> dict:
    rows = []
    for i, size in enumerate(sizes):
        rows.append({"size": size, "height": heights[i] if heights else "",
                     "values": {k: str(v[i]) for k, v in values.items()}})
    return {"name": name, "cut": cut, "columns": [{"key": k, "id": a, "en": b} for k, a, b in cols], "rows": rows,
            "notes_id": "Ukuran badan jadi (garmen) dalam cm, toleransi ±1–2 cm. Bingung? Tanya kami via WhatsApp.",
            "notes_en": "Garment measurements in cm, ±1–2 cm. Not sure? Ask us on WhatsApp."}


_ADULT = SIZES["adult"]
_KIDS = SIZES["kids"]
_BABY = SIZES["baby"]
_KID_H = ["80–92", "98–104", "110–116", "122–128", "134–140", "146–152"]
_BABY_H = ["56–68", "68–80", "80–86", "86–92"]
_C = ("chest", "Lingkar dada", "Chest")
_L = ("length", "Panjang", "Length")
_S = ("shoulder", "Bahu", "Shoulder")
_SL = ("sleeve", "Panjang lengan", "Sleeve")

DEFAULT_CHARTS = [
    _chart("Default men", "men", [_C, _L, _S, _SL], _ADULT, {
        "chest": [96, 100, 104, 110, 116, 122], "length": [68, 70, 72, 74, 76, 78],
        "shoulder": [42, 44, 46, 48, 50, 52], "sleeve": [58, 59, 60, 61, 62, 63]}),
    _chart("Default women", "women", [("bust", "Lingkar dada", "Bust"), ("waist", "Lingkar pinggang", "Waist"),
                                      ("hip", "Lingkar pinggul", "Hip"), _S, _SL], _ADULT, {
        "bust": [88, 92, 96, 102, 108, 114], "waist": [70, 74, 78, 84, 90, 96], "hip": [94, 98, 102, 108, 114, 120],
        "shoulder": [36, 37, 38, 40, 42, 44], "sleeve": [56, 57, 58, 59, 60, 61]}),
    _chart("Default unisex adult", "unisex_adult", [_C, _L, _S], _ADULT, {
        "chest": [100, 104, 108, 114, 120, 126], "length": [68, 70, 72, 74, 76, 78],
        "shoulder": [43, 45, 47, 49, 51, 53]}),
    _chart("Default boys", "boys", [_C, _L, _S], _KIDS, {
        "chest": [54, 58, 62, 66, 72, 78], "length": [38, 42, 46, 50, 54, 58], "shoulder": [25, 27, 29, 31, 33, 35]}, _KID_H),
    _chart("Default girls", "girls", [_C, _L, _S], _KIDS, {
        "chest": [52, 56, 60, 64, 70, 76], "length": [45, 52, 60, 68, 76, 84], "shoulder": [24, 26, 28, 30, 32, 34]}, _KID_H),
    _chart("Default unisex kids", "unisex_kids", [_C, _L], _KIDS, {
        "chest": [54, 58, 62, 66, 72, 78], "length": [38, 42, 46, 50, 54, 58]}, _KID_H),
    _chart("Default baby", "baby", [_C, _L], _BABY, {"chest": [44, 48, 50, 52], "length": [30, 34, 36, 38]}, _BABY_H),
]
