"""Cloudflare Workers AI image generation (FLUX.2 [klein]).

Free tier: 10,000 neurons/day ≈ 75–80 images/day on the 4B model. Reference
images (up to 4) are downscaled to ≤512 px here before upload.
Rule learned in testing: never pass a photo of a *person* as a reference for a
different family member (the model copies that person); pass garment flats and
fabric/detail crops only, and describe the wearer in the prompt."""

from __future__ import annotations

import base64
import io
import logging

import httpx
from PIL import Image

from . import config

log = logging.getLogger("cs.flux")

MODELS = {
    "klein-4b": "@cf/black-forest-labs/flux-2-klein-4b",
    "klein-9b": "@cf/black-forest-labs/flux-2-klein-9b",
}
URL = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"


class FluxError(Exception):
    pass


def available() -> bool:
    return bool(config.CF_ACCOUNT_ID and config.CF_API_TOKEN)


def ref_jpeg(data: bytes, max_side: int = 512) -> bytes:
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


async def generate(prompt: str, *, refs: list[bytes] | None = None, width: int = 768, height: int = 1024,
                   seed: int | None = None, model: str = "klein-4b", timeout: float = 120) -> bytes:
    """Returns JPEG/PNG bytes of one generated image."""
    if not available():
        raise FluxError("Cloudflare Workers AI is not configured (CF_ACCOUNT_ID / CF_API_TOKEN).")
    files: dict = {"prompt": (None, prompt[:2000]), "width": (None, str(width)), "height": (None, str(height))}
    if seed is not None:
        files["seed"] = (None, str(seed))
    for i, ref in enumerate((refs or [])[:4]):
        files[f"input_image_{i}"] = (f"ref{i}.jpg", ref_jpeg(ref), "image/jpeg")
    url = URL.format(account=config.CF_ACCOUNT_ID, model=MODELS.get(model, MODELS["klein-4b"]))
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15)) as http:
        try:
            r = await http.post(url, files=files, headers={"Authorization": f"Bearer {config.CF_API_TOKEN}"})
        except httpx.HTTPError as e:
            raise FluxError(f"Image service unreachable: {e}") from e
    try:
        data = r.json()
    except ValueError:
        raise FluxError(f"Image service answered HTTP {r.status_code}.")
    if r.status_code != 200 or not data.get("success", True):
        errs = data.get("errors") or [{}]
        msg = errs[0].get("message") if isinstance(errs[0], dict) else str(errs[0])
        if r.status_code == 429 or "neurons" in str(msg).lower() or "limit" in str(msg).lower():
            raise FluxError("Today's free image quota is used up. It resets at 07:00 WIB (00:00 UTC).")
        raise FluxError(f"Image generation failed: {msg or r.status_code}")
    b64 = (data.get("result") or {}).get("image")
    if not b64:
        raise FluxError("Image service returned no image.")
    return base64.b64decode(b64)
