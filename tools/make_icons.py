"""Generate the app icons (monogram) for the storefront and the admin app.
Usage: python tools/make_icons.py [MONOGRAM]"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "backend/cs/fonts/Cormorant-Medium.ttf")
mono = sys.argv[1] if len(sys.argv) > 1 else "CS"


def icon(size, bg, fg, path, ring=False):
    img = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, int(size * 0.42))
    box = d.textbbox((0, 0), mono, font=font, anchor="mm")
    d.text((size / 2, size / 2 - (box[1] + box[3]) / 2 * 0.1), mono, font=font, fill=fg, anchor="mm")
    if ring:
        m = size * 0.12
        d.ellipse((m, m, size - m, size - m), outline=fg, width=max(2, size // 90))
    img.save(path, optimize=True)


for s in (180, 192, 512):
    icon(s, "#fbfaf8", "#1c1b19", os.path.join(ROOT, f"backend/shopweb/static/icons/icon-{s}.png"), ring=True)
    icon(s, "#1c1b19", "#f4efe7", os.path.join(ROOT, f"admin-ui/icons/icon-{s}.png"))
print("icons written")
