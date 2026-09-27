"""Unit tests for pure helpers (no PocketBase needed): python -m pytest tests"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from cs import catalog, util  # noqa: E402
from shopadmin.scheduler import upcoming  # noqa: E402
from shopadmin.studio import chart_for  # noqa: E402


def test_sizes_and_sets():
    assert catalog.sizes_for_cut("men")[0] == "S"
    assert catalog.sizes_for_cut("girls")[-1] == "11-12Y"
    assert catalog.sizes_for_cut("baby")[0] == "0-6M"
    assert catalog.set_types({"cuts": ["men", "women"]}) == ["couple"]
    assert catalog.set_types({"cuts": ["men", "girls"]}) == ["couple", "family", "kids"]
    assert catalog.set_types({"cuts": ["baby"]}) == ["kids"]


def test_prices_and_sale():
    p = {"cuts": ["men", "boys"], "cut_prices": {"men": 389000, "boys": 229000}, "sale_percent": 20,
         "sale_start": "", "sale_end": ""}
    assert catalog.cut_price(p, "men") == (389000, 311200)
    assert catalog.price_range(p) == (183200, 311200, 229000, 389000)
    p["sale_end"] = "2020-01-01 00:00:00.000Z"
    assert catalog.cut_price(p, "men") == (389000, 389000)
    assert catalog.rupiah(1231200) == "Rp1.231.200"


def test_phone_and_wa():
    assert util.normalize_phone("0812-3456-7890") == "6281234567890"
    assert util.normalize_phone("+62 812 3456 7890") == "6281234567890"
    assert util.normalize_phone("81234567890") == "6281234567890"
    assert util.wa_link("0812", "Halo ya").endswith("?text=Halo%20ya")


def test_markdown_is_safe():
    html = util.markdown("<script>alert(1)</script>\n\n**bold**")
    assert "<script>" not in html and "<strong>bold</strong>" in html


def test_upcoming_special_days():
    assert upcoming("1990-10-03", date(2026, 9, 30)) == date(2026, 10, 3)
    assert upcoming("1990-10-30", date(2026, 9, 30)) is None
    assert upcoming("1992-01-02", date(2026, 12, 30)) == date(2027, 1, 2)
    assert upcoming("2000-02-29", date(2027, 2, 25)) == date(2027, 2, 28)


def test_graded_chart():
    ch = chart_for("men", "relaxed", "+4", "Test")
    s = next(r for r in ch["rows"] if r["size"] == "S")
    assert s["values"]["chest"] == "100" and s["values"]["length"] == "72"
