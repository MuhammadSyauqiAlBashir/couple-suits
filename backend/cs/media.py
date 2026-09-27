"""Image pipeline: every upload becomes a set of WebP files that Caddy serves
directly from /media/<key>/<width>.webp. Originals are not kept (EXIF, GPS and
other metadata are dropped on the way)."""

from __future__ import annotations

import io
import os
import shutil

from PIL import Image, ImageOps

from . import config
from .catalog import MEDIA_WIDTHS
from .util import new_key

Image.MAX_IMAGE_PIXELS = 50_000_000  # refuse decompression bombs
MAX_BYTES = 25 * 1024 * 1024


class BadImage(ValueError):
    pass


def open_image(data: bytes) -> Image.Image:
    if len(data) > MAX_BYTES:
        raise BadImage("The image is too large (max 25 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:  # noqa: BLE001 - any decoding problem is a bad upload
        raise BadImage("That file isn't a supported image.") from e
    img = ImageOps.exif_transpose(img)
    if img.mode in ("P", "LA", "PA"):
        img = img.convert("RGBA")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    return img


def average_color(img: Image.Image) -> str:
    small = img.convert("RGB").resize((1, 1), Image.Resampling.BOX)
    r, g, b = small.getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"


def save_webp_set(img: Image.Image, key: str, root: str | None = None) -> dict:
    """Write <root>/<key>/<w>.webp for every standard width (never upscaled)."""
    folder = os.path.join(root or config.MEDIA_DIR, key)
    os.makedirs(folder, exist_ok=True)
    for w in MEDIA_WIDTHS:
        copy = img.copy()
        if copy.width > w:
            copy = copy.resize((w, round(copy.height * w / copy.width)), Image.Resampling.LANCZOS)
        tmp = os.path.join(folder, f".{w}.webp.tmp")
        copy.save(tmp, "WEBP", quality=82, method=5)
        os.replace(tmp, os.path.join(folder, f"{w}.webp"))
    return {"key": key, "width": img.width, "height": img.height, "color": average_color(img),
            "sizes": MEDIA_WIDTHS}


def ingest(data: bytes, root: str | None = None) -> dict:
    """Store an uploaded image; returns key, size and average colour."""
    return save_webp_set(open_image(data), new_key(), root)


def remove(key: str, root: str | None = None):
    if key and key.isalnum():
        shutil.rmtree(os.path.join(root or config.MEDIA_DIR, key), ignore_errors=True)


def path_for(key: str, width: int = 1200, root: str | None = None) -> str:
    return os.path.join(root or config.MEDIA_DIR, key, f"{width}.webp")
