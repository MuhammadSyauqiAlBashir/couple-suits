"""AI design studio.

Flow (the browser drives it one step at a time, so each request stays short):
  1. create a design (title, family roles, notes) and upload sketches / detail crops;
  2. analyse → Gemini (free) turns the inputs into a structured brief + image prompts;
  3. generate options → FLUX.2 [klein] with the sketch + details as references (one image per request);
  4. choose one → technical flats (front/back) from the chosen option;
  5. other family roles → from the flat + fabric/detail crops only (never a photo of a person, or the
     model copies that person), wearer described in the prompt;
  6. mockup board (Pillow), tech pack + size charts (Gemini + grading tables), PDF (fpdf2);
  7. turn into a draft product (photos copied to the public media folder).

Studio files are private: STATE_DIR/studio/<design>/, served only through this API."""

from __future__ import annotations

import io
import logging
import os
import random
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, Field

from cs import ai, catalog, config, flux, media, util
from cs.pb import pb, q

from .security import User, admin

log = logging.getLogger("shopadmin.studio")
router = APIRouter(prefix="/api/studio")
FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cs", "fonts")
DAILY_FREE = 75

# Who wears what, in words the image model understands.
WEARER = {
    "dad": "an Indonesian man in his thirties", "husband": "an Indonesian man in his thirties",
    "mom": "an Indonesian woman in her thirties", "wife": "an Indonesian woman in her thirties",
    "son": "a 7-year-old Indonesian boy", "daughter": "a 6-year-old Indonesian girl",
    "brother": "a 10-year-old Indonesian boy", "sister": "a 10-year-old Indonesian girl",
    "baby": "an Indonesian baby about one year old", "grandpa": "an Indonesian grandfather in his sixties",
    "grandma": "an Indonesian grandmother in her sixties", "other": "an Indonesian adult",
}
PHOTO_STYLE = ("Editorial fashion catalogue photograph, full body, standing, warm off-white seamless studio backdrop, "
               "soft natural light, true-to-life fabric texture, no text, no watermark.")
FLAT_STYLE = ("Technical fashion flat sketch, clean black line drawing on pure white background, no person, no "
              "mannequin, symmetrical, garment laid flat, stitching shown as dashed lines, no shading, no text.")


def design_dir(did: str) -> str:
    path = os.path.join(config.STATE_DIR, "studio", did)
    os.makedirs(path, exist_ok=True)
    return path


def save_image(did: str, data: bytes, max_side: int = 1600) -> tuple[str, int, int]:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    name = util.new_key(12) + ".jpg"
    img.save(os.path.join(design_dir(did), name), "JPEG", quality=90)
    return name, img.width, img.height


def asset_bytes(asset: dict) -> bytes:
    with open(os.path.join(design_dir(asset["design"]), asset["path"]), "rb") as f:
        return f.read()


async def usage_today() -> int:
    return int(await pb.kv_get(f"flux:{util.today()}", 0) or 0)


async def count_image(n: int = 1):
    await pb.kv_set(f"flux:{util.today()}", await usage_today() + n)


async def get_design(did: str) -> tuple[dict, list[dict]]:
    d = await pb.get("shop_designs", util.rid(did))
    assets = await pb.all("shop_design_assets", filter=f"design = {q(did)}", sort="created")
    return d, assets


def asset_view(a: dict) -> dict:
    return {"id": a["id"], "kind": a["kind"], "label": a.get("label") or "", "round": a.get("round") or 0,
            "favorite": a.get("favorite", False), "meta": a.get("meta") or {}, "url": f"/api/studio/assets/{a['id']}"}


# ---------------------------------------------------------------------------
# Designs
# ---------------------------------------------------------------------------

class DesignIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    roles: list[str] = Field(default_factory=list, max_length=12)
    notes: str = Field(default="", max_length=5000)


@router.get("/designs")
async def designs(user: User = Depends(admin)):
    items = await pb.all("shop_designs", sort="-updated", fields="id,title,status,roles,chosen,product,updated")
    covers = {}
    for a in await pb.all("shop_design_assets", filter="kind = 'option' || kind = 'sketch' || kind = 'mockup'",
                          fields="id,design,kind,favorite", sort="created"):
        cur = covers.get(a["design"])
        rank = {"mockup": 3, "option": 2, "sketch": 1}[a["kind"]]
        if not cur or rank > cur[0]:
            covers[a["design"]] = (rank, a["id"])
    for d in items:
        chosen = (d.get("chosen") or {}).get("asset")
        d["cover"] = f"/api/studio/assets/{chosen or covers.get(d['id'], (0, ''))[1]}" if (chosen or d["id"] in covers) else ""
    return {"designs": items, "usage": await usage_today(), "free": DAILY_FREE, "flux": flux.available(),
            "gemini": bool(config.GEMINI_API_KEY)}


@router.post("/designs")
async def create_design(body: DesignIn, user: User = Depends(admin)):
    roles = [r for r in body.roles if r in catalog.ROLES] or ["wife"]
    rec = await pb.create("shop_designs", {"title": body.title.strip(), "status": "draft", "roles": roles,
                                           "notes": body.notes.strip(), "brief": {}, "chosen": {}, "spec": {},
                                           "engine": "klein-4b", "product": "", "created_by": user.username})
    return {"design": rec}


@router.get("/designs/{did}")
async def design(did: str, user: User = Depends(admin)):
    d, assets = await get_design(did)
    return {"design": d, "assets": [asset_view(a) for a in assets], "usage": await usage_today(), "free": DAILY_FREE,
            "roles": {k: v["en"] for k, v in catalog.ROLES.items()}}


class DesignPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    roles: list[str] | None = Field(default=None, max_length=12)
    notes: str | None = Field(default=None, max_length=5000)
    brief: dict | None = None


@router.patch("/designs/{did}")
async def patch_design(did: str, body: DesignPatch, user: User = Depends(admin)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if "roles" in data:
        data["roles"] = [r for r in data["roles"] if r in catalog.ROLES]
    await pb.update("shop_designs", util.rid(did), data)
    return await design(did, user)


@router.delete("/designs/{did}")
async def delete_design(did: str, user: User = Depends(admin)):
    await pb.delete("shop_designs", util.rid(did))  # assets cascade
    shutil.rmtree(os.path.join(config.STATE_DIR, "studio", did), ignore_errors=True)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

@router.post("/designs/{did}/inputs")
async def upload_input(did: str, file: UploadFile = File(...), kind: str = Form("sketch"), label: str = Form(""),
                       user: User = Depends(admin)):
    """Sketches, detail crops, or (manual Gemini-app path) a generated option."""
    if kind not in ("sketch", "detail", "option"):
        raise HTTPException(400, "Unknown kind.")
    d = await pb.get("shop_designs", util.rid(did))
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Image too large.")
    try:
        name, w, h = save_image(d["id"], data)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "That file isn't a supported image.")
    a = await pb.create("shop_design_assets", {"design": d["id"], "kind": kind, "path": name, "label": label[:200],
                                               "round": 0, "meta": {"w": w, "h": h, "source": "upload"}, "favorite": False})
    return {"asset": asset_view(a)}


@router.get("/assets/{aid}")
async def asset_file(aid: str, user: User = Depends(admin)):
    a = await pb.get("shop_design_assets", util.rid(aid))
    path = os.path.join(design_dir(a["design"]), a["path"])
    if not os.path.exists(path):
        raise HTTPException(404, "Missing file.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


class AssetPatch(BaseModel):
    favorite: bool | None = None
    label: str | None = Field(default=None, max_length=200)


@router.patch("/assets/{aid}")
async def patch_asset(aid: str, body: AssetPatch, user: User = Depends(admin)):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    return asset_view(await pb.update("shop_design_assets", util.rid(aid), data))


@router.delete("/assets/{aid}")
async def delete_asset(aid: str, user: User = Depends(admin)):
    a = await pb.get("shop_design_assets", util.rid(aid))
    try:
        os.remove(os.path.join(design_dir(a["design"]), a["path"]))
    except OSError:
        pass
    await pb.delete("shop_design_assets", aid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# 1. Analyse → brief (Gemini, free)
# ---------------------------------------------------------------------------

S = {"type": "string"}


def obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "propertyOrdering": list(props)}


def arr(items: dict) -> dict:
    return {"type": "array", "items": items}


BRIEF_SCHEMA = obj({
    "garment_type": S, "silhouette": S, "details": arr(S), "fabric": S,
    "colors": arr(obj({"name": S, "hex": S})), "trims": arr(S), "occasion": S,
    "roles": arr(obj({"role": S, "garment": S, "notes": S})),
    "questions": arr(S), "summary_id": S,
    "prompt_primary": S, "flat_description": S,
})

BRIEF_SYSTEM = """You are a senior fashion designer for an Indonesian brand that makes matching outfits for couples
and families. From the owner's sketches, detail crops (collars, buttons, fabric, waist shapes…) and notes, write a
precise design brief. For every family role given, adapt the SAME design language (same fabric, colour, key details)
into an appropriate garment for that person (e.g. a dress for mum → a shirt for dad, a smaller dress for a daughter,
a romper for a baby). Be concrete about construction (collar type, closure, sleeve length, hem, pleats).
- prompt_primary: one English paragraph (≤ 90 words) describing the primary role's garment for an image model
  (garment only, fabric, colour, details; do not describe the person's face).
- flat_description: one English paragraph (≤ 70 words) describing the garment for a technical flat drawing.
- colors: hex like #aabbcc. summary_id: 2 sentences in Bahasa Indonesia for the owner.
- questions: up to 3 short questions (in Bahasa Indonesia) about anything unclear; empty if all clear."""


@router.post("/designs/{did}/analyze")
async def analyze(did: str, user: User = Depends(admin)):
    d, assets = await get_design(did)
    inputs = [a for a in assets if a["kind"] in ("sketch", "detail")]
    if not inputs and not d.get("notes"):
        raise HTTPException(400, "Upload a sketch or write some notes first.")
    roles = ", ".join(catalog.ROLES[r]["en"] for r in d.get("roles") or [] if r in catalog.ROLES)
    parts: list = [f"Design title: {d['title']}\nFamily roles (first is the primary wearer): {roles}\n"
                   f"Owner's notes: {d.get('notes') or '(none)'}"]
    for a in inputs[:6]:
        parts.append(f"[{a['kind']}{': ' + a['label'] if a.get('label') else ''}]")
        parts.append(ai.image_part(asset_bytes(a), "image/jpeg"))
    try:
        brief = await ai.generate(parts, system=BRIEF_SYSTEM, schema=BRIEF_SCHEMA, smart=True)
    except ai.AIUnavailable as e:
        raise HTTPException(503, f"The AI is busy right now; try again in a minute. ({str(e)[:100]})")
    await pb.update("shop_designs", did, {"brief": brief})
    return await design(did, user)


# ---------------------------------------------------------------------------
# 2. Generate images (one per request)
# ---------------------------------------------------------------------------

class GenIn(BaseModel):
    kind: str = Field(pattern="^(option|flat_front|flat_back|role)$")
    role: str = Field(default="", max_length=40)
    feedback: str = Field(default="", max_length=1000)
    hq: bool = False
    seed: int | None = None


def role_garment(brief: dict, role: str) -> str:
    for r in brief.get("roles") or []:
        if str(r.get("role", "")).lower() in (role, catalog.ROLES.get(role, {}).get("en", "").lower()):
            return f"{r.get('garment', '')}. {r.get('notes', '')}"
    return brief.get("garment_type", "")


@router.post("/designs/{did}/generate")
async def generate(did: str, body: GenIn, user: User = Depends(admin)):
    d, assets = await get_design(did)
    brief = d.get("brief") or {}
    if not brief:
        raise HTTPException(400, "Run “Analyse” first.")
    by_id = {a["id"]: a for a in assets}
    details = [a for a in assets if a["kind"] == "detail"]
    sketches = [a for a in assets if a["kind"] == "sketch"]
    chosen = by_id.get((d.get("chosen") or {}).get("asset", ""))
    colors = ", ".join(f"{c.get('name')} ({c.get('hex')})" for c in brief.get("colors") or [])
    roles = d.get("roles") or ["wife"]
    feedback = f" Changes requested: {body.feedback}." if body.feedback else ""
    width, height = 768, 1024
    if body.kind == "option":
        primary = roles[0]
        prompt = (f"{WEARER.get(primary, WEARER['other'])} wearing: {brief.get('prompt_primary', '')} Colours: {colors}."
                  f"{feedback} Follow the silhouette of the sketch reference and the exact details in the detail "
                  f"references. {PHOTO_STYLE}")
        refs = [asset_bytes(a) for a in (sketches[:1] + details[:3])]
        label = catalog.ROLES.get(primary, {}).get("en", primary)
        rnd = max([a.get("round") or 0 for a in assets if a["kind"] == "option"] or [0])
        rnd = rnd + 1 if body.feedback or not any(a["kind"] == "option" for a in assets) else max(rnd, 1)
    elif body.kind in ("flat_front", "flat_back"):
        if not chosen:
            raise HTTPException(400, "Choose an option first.")
        side = "front view" if body.kind == "flat_front" else "back view (show the back: closures, yoke, pleats, zip)"
        prompt = (f"{side} of this garment: {brief.get('flat_description', '')}{feedback} Match the garment in the "
                  f"reference exactly. {FLAT_STYLE}")
        refs = [asset_bytes(chosen)] + [asset_bytes(a) for a in details[:2]]
        label, rnd, width, height = ("Flat — front" if body.kind == "flat_front" else "Flat — back"), 0, 1024, 1024
    else:
        role = body.role if body.role in catalog.ROLES else "other"
        flat = next((a for a in reversed(assets) if a["kind"] == "flat" and (a.get("meta") or {}).get("side") == "front"), None)
        if not flat:
            raise HTTPException(400, "Make the front flat sketch first (it keeps every family member's outfit consistent).")
        prompt = (f"{WEARER.get(role, WEARER['other'])} wearing {role_garment(brief, role)} Same fabric, colour and "
                  f"details as the garment in the flat sketch reference and the fabric/detail references. Colours: "
                  f"{colors}.{feedback} {PHOTO_STYLE}")
        # Garment references only — never a photo of a person.
        refs = [asset_bytes(flat)] + [asset_bytes(a) for a in details[:3]]
        label, rnd = catalog.ROLES[role]["en"], 0
    used = await usage_today()
    model = "klein-9b" if body.hq else "klein-4b"
    seed = body.seed if body.seed is not None else random.randint(1, 10**7)
    try:
        img = await flux.generate(prompt, refs=refs, width=width, height=height, seed=seed, model=model)
    except flux.FluxError as e:
        raise HTTPException(503, str(e))
    await count_image(12 if body.hq else 1)
    name, w, h = save_image(did, img, 1400)
    kind = "flat" if body.kind.startswith("flat") else body.kind
    meta = {"w": w, "h": h, "seed": seed, "model": model, "prompt": prompt[:1500], "feedback": body.feedback}
    if kind == "flat":
        meta["side"] = "front" if body.kind == "flat_front" else "back"
    if kind == "role":
        meta["role"] = body.role
    a = await pb.create("shop_design_assets", {"design": did, "kind": kind, "path": name, "label": label, "round": rnd,
                                               "meta": meta, "favorite": False})
    if d["status"] == "draft":
        await pb.update("shop_designs", did, {"status": "options"})
    return {"asset": asset_view(a), "usage": used + (12 if body.hq else 1)}


@router.get("/designs/{did}/gemini-prompt")
async def gemini_prompt(did: str, user: User = Depends(admin)):
    """For the manual path: paste into the Gemini app with the sketch, then upload the result as an option."""
    d, _ = await get_design(did)
    brief = d.get("brief") or {}
    colors = ", ".join(f"{c.get('name')} ({c.get('hex')})" for c in brief.get("colors") or [])
    roles = ", ".join(catalog.ROLES[r]["en"] for r in d.get("roles") or [] if r in catalog.ROLES)
    return {"prompt": f"Using my attached sketch and detail photos, create a realistic catalogue photo of a matching "
                      f"family outfit for: {roles}. Main garment: {brief.get('prompt_primary', d.get('notes', ''))} "
                      f"Colours: {colors}. Each person's outfit is adapted to them but uses the same fabric and details. "
                      f"Warm off-white studio background, soft light, full body, no text."}


class ChooseIn(BaseModel):
    asset: str = Field(max_length=20)


@router.post("/designs/{did}/choose")
async def choose(did: str, body: ChooseIn, user: User = Depends(admin)):
    a = await pb.get("shop_design_assets", util.rid(body.asset))
    if a["design"] != did or a["kind"] != "option":
        raise HTTPException(400, "Choose one of this design's options.")
    await pb.update("shop_designs", did, {"chosen": {"asset": a["id"]}, "status": "chosen"})
    return await design(did, user)


# ---------------------------------------------------------------------------
# 3. Mockup board (the family set side by side)
# ---------------------------------------------------------------------------

def font(size: int, bold: bool = False):
    return ImageFont.truetype(os.path.join(FONTS, "Inter-SemiBold.ttf" if bold else "Inter-Regular.ttf"), size)


@router.post("/designs/{did}/mockup")
async def mockup(did: str, user: User = Depends(admin)):
    d, assets = await get_design(did)
    by_id = {a["id"]: a for a in assets}
    chosen = by_id.get((d.get("chosen") or {}).get("asset", ""))
    if not chosen:
        raise HTTPException(400, "Choose an option first.")
    panels = [(chosen.get("label") or "Main", chosen)]
    seen = set()
    for a in reversed(assets):
        role = (a.get("meta") or {}).get("role")
        if a["kind"] == "role" and role not in seen:
            seen.add(role)
            panels.append((a.get("label") or role, a))
    panels = [panels[0]] + list(reversed(panels[1:]))
    if len(panels) < 2:
        raise HTTPException(400, "Generate at least one other family member first.")
    pw, ph, pad, head = 600, 800, 40, 150
    W = pad + len(panels) * (pw + pad)
    board = Image.new("RGB", (W, ph + head + pad * 2 + 60), "#fbfaf8")
    draw = ImageDraw.Draw(board)
    title_font = ImageFont.truetype(os.path.join(FONTS, "Cormorant-SemiBold.ttf"), 64)
    draw.text((pad, pad), d["title"], font=title_font, fill="#1c1b19")
    for i, (label, a) in enumerate(panels):
        img = Image.open(io.BytesIO(asset_bytes(a))).convert("RGB")
        img = ImageOps.fit(img, (pw, ph), Image.Resampling.LANCZOS, centering=(0.5, 0.35))
        x = pad + i * (pw + pad)
        board.paste(img, (x, head))
        draw.text((x, head + ph + 16), label, font=font(30, True), fill="#1c1b19")
    name = util.new_key(12) + ".jpg"
    board.save(os.path.join(design_dir(did), name), "JPEG", quality=88)
    a = await pb.create("shop_design_assets", {"design": did, "kind": "mockup", "path": name, "label": "Family mockup",
                                               "round": 0, "meta": {"w": board.width, "h": board.height}, "favorite": False})
    return {"asset": asset_view(a)}


# ---------------------------------------------------------------------------
# 4. Tech pack + size charts (Gemini + standard grading tables)
# ---------------------------------------------------------------------------

SPEC_SCHEMA = obj({
    "name_id": S, "name_en": S, "summary_id": S, "summary_en": S, "description_id": S, "description_en": S,
    "components": arr(S),
    "fabrics": arr(obj({"name": S, "weight": S, "notes": S})),
    "colors": arr(obj({"name_id": S, "name_en": S, "hex": S, "reference": S})),
    "trims": arr(obj({"item": S, "spec": S, "qty": S})),
    "construction": arr(S),
    "points_of_measure": arr(obj({"code": S, "name": S, "how": S})),
    "cuts": arr(obj({"cut": {"type": "string", "enum": list(catalog.CUTS)}, "garment": S, "notes": S,
                     "fit": {"type": "string", "enum": ["slim", "regular", "relaxed", "oversized"]},
                     "length_adjust_cm": S})),
    "care_id": S, "care_en": S, "material_id": S, "material_en": S,
})

SPEC_SYSTEM = """You are a technical designer preparing a tech pack for a tailor / small garment factory in
Indonesia. Use the design brief and images. Be practical and specific: fabric names available in Indonesia
(e.g. katun toyobo, linen rami, rayon viscose, katun primisima, satin velvet), weights in gsm, trims with sizes
(e.g. 'kancing kayu 15 mm'), construction steps and seam types, and points of measure (A = chest ½ at 2.5 cm below
armhole, etc.). cuts: one entry per garment cut needed for the family roles (men, women, boys, girls, baby,
unisex_adult, unisex_kids), with fit and length_adjust_cm (a number as text, e.g. "0", "+8" for a longer dress,
"-4") relative to a standard shirt/top length. Names: short, elegant product names. Descriptions: 1 paragraph +
3 markdown bullets. Everything is a draft for a pattern maker to check."""

EASE = {"slim": -2, "regular": 0, "relaxed": 4, "oversized": 8}


def chart_for(cut: str, fit: str, length_adjust: str, title: str) -> dict:
    base = next(c for c in catalog.DEFAULT_CHARTS if c["cut"] == cut)
    ease = EASE.get(fit, 0)
    try:
        dlen = int(float(str(length_adjust).replace("+", "").strip() or 0))
    except ValueError:
        dlen = 0
    rows = []
    for r in base["rows"]:
        vals = {}
        for k, v in r["values"].items():
            n = float(v)
            if k in ("chest", "bust", "waist", "hip"):
                n += ease * (0.5 if cut in ("baby", "boys", "girls", "unisex_kids") else 1)
            elif k == "length":
                n += dlen * (0.5 if cut in ("baby", "boys", "girls", "unisex_kids") else 1)
            vals[k] = str(int(round(n)))
        rows.append({**r, "values": vals})
    return {"name": f"{title} — {catalog.CUTS[cut]['en']}", "cut": cut, "columns": base["columns"], "rows": rows,
            "notes_id": f"Draf dari tabel standar ({fit}). Cek dengan sampel.", "notes_en": f"Draft from standard tables ({fit} fit). Check against a sample."}


@router.post("/designs/{did}/techpack")
async def techpack(did: str, user: User = Depends(admin)):
    d, assets = await get_design(did)
    by_id = {a["id"]: a for a in assets}
    chosen = by_id.get((d.get("chosen") or {}).get("asset", ""))
    if not chosen:
        raise HTTPException(400, "Choose an option first.")
    roles = ", ".join(catalog.ROLES[r]["en"] for r in d.get("roles") or [] if r in catalog.ROLES)
    import json  # noqa: PLC0415
    parts: list = [f"Design: {d['title']}\nRoles: {roles}\nOwner notes: {d.get('notes') or ''}\nBrief: {json.dumps(d.get('brief') or {}, ensure_ascii=False)}",
                   "[chosen design]", ai.image_part(asset_bytes(chosen), "image/jpeg")]
    for a in assets:
        if a["kind"] == "flat":
            parts += [f"[flat {(a.get('meta') or {}).get('side', '')}]", ai.image_part(asset_bytes(a), "image/jpeg")]
    try:
        spec = await ai.generate(parts, system=SPEC_SYSTEM, schema=SPEC_SCHEMA, smart=True)
    except ai.AIUnavailable as e:
        raise HTTPException(503, f"The AI is busy right now; try again in a minute. ({str(e)[:100]})")
    wanted = {catalog.ROLES[r]["cuts"][0] for r in d.get("roles") or [] if r in catalog.ROLES}
    cuts = {c["cut"]: c for c in spec.get("cuts") or [] if c.get("cut") in catalog.CUTS}
    for cut in wanted:
        cuts.setdefault(cut, {"cut": cut, "garment": "", "notes": "", "fit": "regular", "length_adjust_cm": "0"})
    spec["cuts"] = list(cuts.values())
    spec["size_charts"] = [chart_for(c["cut"], c.get("fit", "regular"), c.get("length_adjust_cm", "0"), d["title"])
                           for c in spec["cuts"]]
    await pb.update("shop_designs", did, {"spec": spec, "status": "done" if d["status"] != "done" else "done"})
    return await design(did, user)


class SpecPatch(BaseModel):
    spec: dict


@router.put("/designs/{did}/spec")
async def put_spec(did: str, body: SpecPatch, user: User = Depends(admin)):
    await pb.update("shop_designs", util.rid(did), {"spec": body.spec})
    return {"ok": True}


# ---------------------------------------------------------------------------
# 5. PDF tech pack
# ---------------------------------------------------------------------------

@router.get("/designs/{did}/pdf")
async def pdf(did: str, user: User = Depends(admin)):
    from fpdf import FPDF  # noqa: PLC0415
    d, assets = await get_design(did)
    spec = d.get("spec") or {}
    if not spec:
        raise HTTPException(400, "Make the tech pack first.")
    by_id = {a["id"]: a for a in assets}
    chosen = by_id.get((d.get("chosen") or {}).get("asset", ""))
    s = await util.settings()

    doc = FPDF(format="A4", unit="mm")
    doc.set_auto_page_break(True, 15)
    doc.add_font("Inter", "", os.path.join(FONTS, "Inter-Regular.ttf"))
    doc.add_font("Inter", "B", os.path.join(FONTS, "Inter-SemiBold.ttf"))
    doc.add_font("Serif", "", os.path.join(FONTS, "Cormorant-SemiBold.ttf"))
    doc.set_title(f"Tech pack — {d['title']}")

    def h1(text):
        doc.set_font("Serif", "", 26)
        doc.cell(0, 12, text, new_x="LMARGIN", new_y="NEXT")

    def h2(text):
        doc.ln(3)
        doc.set_font("Inter", "B", 11)
        doc.cell(0, 7, text.upper(), new_x="LMARGIN", new_y="NEXT")
        doc.set_draw_color(200, 195, 188)
        doc.line(doc.l_margin, doc.get_y(), doc.w - doc.r_margin, doc.get_y())
        doc.ln(2)

    def para(text, size=9.5):
        doc.set_font("Inter", "", size)
        doc.multi_cell(0, 5, str(text or ""), new_x="LMARGIN", new_y="NEXT")

    def bullets(items):
        doc.set_font("Inter", "", 9.5)
        for it in items or []:
            doc.multi_cell(0, 5, f"•  {it}", new_x="LMARGIN", new_y="NEXT")

    def image(a, w, h=None, x=None):
        if not a:
            return
        img = Image.open(io.BytesIO(asset_bytes(a))).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        buf.seek(0)
        doc.image(buf, x=x, w=w, h=h or w * img.height / img.width)

    # Cover
    doc.add_page()
    doc.set_font("Inter", "", 9)
    doc.set_text_color(120, 115, 108)
    doc.cell(0, 6, f"{s['brand_name']} · TECH PACK · {util.today()}", new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(28, 27, 25)
    h1(spec.get("name_en") or d["title"])
    para(spec.get("summary_en") or "")
    doc.ln(3)
    image(chosen, 95)
    doc.set_xy(doc.l_margin + 100, 40)
    doc.set_font("Inter", "B", 9)
    doc.multi_cell(0, 5, "Roles: " + ", ".join(catalog.ROLES[r]["en"] for r in d.get("roles") or [] if r in catalog.ROLES))
    doc.set_x(doc.l_margin + 100)
    doc.set_font("Inter", "", 9)
    for c in spec.get("colors") or []:
        doc.set_x(doc.l_margin + 100)
        try:
            r, g, b = (int(c.get("hex", "#999999")[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            r, g, b = 150, 150, 150
        doc.set_fill_color(r, g, b)
        doc.cell(6, 6, "", fill=True, border=1)
        doc.cell(0, 6, f"  {c.get('name_en')} / {c.get('name_id')}  {c.get('hex')}  {c.get('reference', '')}", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Inter", "", 7.5)
    doc.set_text_color(120, 115, 108)
    doc.set_y(-25)
    doc.multi_cell(0, 4, "AI-assisted draft. Measurements, fabric weights and construction must be checked by a pattern maker against a physical sample.")
    doc.set_text_color(28, 27, 25)

    # Flats
    flats = [a for a in assets if a["kind"] == "flat"]
    front = next((a for a in reversed(flats) if (a.get("meta") or {}).get("side") == "front"), None)
    back = next((a for a in reversed(flats) if (a.get("meta") or {}).get("side") == "back"), None)
    if front or back:
        doc.add_page()
        h2("Technical flats")
        y = doc.get_y()
        if front:
            image(front, 88, x=doc.l_margin)
        if back:
            doc.set_y(y)
            image(back, 88, x=doc.l_margin + 94)
        doc.ln(4)

    # Spec
    doc.add_page()
    h2("Components")
    bullets(spec.get("components"))
    h2("Fabric")
    for f in spec.get("fabrics") or []:
        para(f"{f.get('name')} — {f.get('weight')}. {f.get('notes', '')}")
    h2("Trims")
    for t in spec.get("trims") or []:
        para(f"{t.get('item')}: {t.get('spec')} (qty {t.get('qty')})")
    h2("Construction")
    bullets(spec.get("construction"))
    h2("Per cut")
    for c in spec.get("cuts") or []:
        para(f"{catalog.CUTS[c['cut']]['en']} ({c.get('fit', 'regular')} fit, length {c.get('length_adjust_cm', '0')} cm): "
             f"{c.get('garment', '')}. {c.get('notes', '')}")
    h2("Points of measure")
    for pom in spec.get("points_of_measure") or []:
        para(f"{pom.get('code')}  {pom.get('name')} — {pom.get('how')}")

    # Size charts
    for chart in spec.get("size_charts") or []:
        if doc.get_y() > 200:
            doc.add_page()
        h2(f"Size chart — {catalog.CUTS[chart['cut']]['en']} (cm)")
        cols = chart["columns"]
        has_h = any(r.get("height") for r in chart["rows"])
        widths = [22] + ([24] if has_h else []) + [min(30, (doc.w - 30 - 22 - (24 if has_h else 0)) / max(1, len(cols)))] * len(cols)
        doc.set_font("Inter", "B", 8.5)
        for w, t in zip(widths, ["Size"] + (["Height"] if has_h else []) + [c["en"] for c in cols]):
            doc.cell(w, 7, t, border="B", align="C")
        doc.ln()
        doc.set_font("Inter", "", 8.5)
        for r in chart["rows"]:
            vals = [r["size"]] + ([r.get("height", "")] if has_h else []) + [r["values"].get(c["key"], "") for c in cols]
            for w, t in zip(widths, vals):
                doc.cell(w, 6.5, str(t), border="B", align="C")
            doc.ln()
        doc.set_font("Inter", "", 7.5)
        doc.cell(0, 6, chart.get("notes_en", ""), new_x="LMARGIN", new_y="NEXT")

    # Family
    mock = next((a for a in reversed(assets) if a["kind"] == "mockup"), None)
    roles = [a for a in assets if a["kind"] == "role"]
    if mock or roles:
        doc.add_page(orientation="L")
        h2("Family set")
        if mock:
            image(mock, doc.w - 30)
    data = bytes(doc.output())
    fname = util.slugify(d["title"]) + "-techpack.pdf"
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------------------------------------------------------------------------
# 6. Turn into a draft product
# ---------------------------------------------------------------------------

@router.post("/designs/{did}/product")
async def to_product(did: str, user: User = Depends(admin)):
    d, assets = await get_design(did)
    spec = d.get("spec") or {}
    by_id = {a["id"]: a for a in assets}
    chosen = by_id.get((d.get("chosen") or {}).get("asset", ""))
    if not chosen or not spec:
        raise HTTPException(400, "Choose an option and make the tech pack first.")
    picks = [chosen] + [a for a in assets if a["kind"] in ("role", "mockup")]
    keys = []
    for a in picks[:10]:
        info = media.ingest(asset_bytes(a))
        await pb.create("shop_media", {"key": info["key"], "kind": "product", "alt_id": d["title"], "alt_en": d["title"],
                                       "width": info["width"], "height": info["height"], "sizes": info["sizes"],
                                       "color": info["color"], "uploaded_by": f"studio:{user.username}"})
        keys.append(info["key"])
    chart_ids = []
    for ch in spec.get("size_charts") or []:
        rec = await pb.create("shop_size_charts", ch)
        chart_ids.append(rec["id"])
    cuts = [c["cut"] for c in spec.get("cuts") or [] if c.get("cut") in catalog.CUTS]
    colors = [{"key": util.slugify(c.get("name_id") or c.get("name_en") or "warna", 40), "name_id": c.get("name_id", ""),
               "name_en": c.get("name_en", ""), "hex": c.get("hex") if str(c.get("hex", "")).startswith("#") and len(c["hex"]) == 7 else "#cccccc",
               "media": []} for c in (spec.get("colors") or [])[:1]]
    from .routes_catalog import free_slug  # noqa: PLC0415
    slug = await free_slug(util.slugify(spec.get("name_id") or d["title"], 100))
    product = await pb.create("shop_products", {
        "slug": slug, "name_id": spec.get("name_id") or d["title"], "name_en": spec.get("name_en") or d["title"],
        "summary_id": spec.get("summary_id", ""), "summary_en": spec.get("summary_en", ""),
        "description_id": spec.get("description_id", ""), "description_en": spec.get("description_en", ""),
        "material_id": spec.get("material_id", ""), "material_en": spec.get("material_en", ""),
        "care_id": spec.get("care_id", ""), "care_en": spec.get("care_en", ""),
        "status": "draft", "stock_mode": "preorder", "preorder_days": 21, "cuts": cuts, "cut_prices": {c: 0 for c in cuts},
        "colors": colors, "media": keys, "size_charts": chart_ids, "tags": [], "collections": [], "sale_percent": 0,
        "featured": False, "sort": 0, "design_id": did, "demo": False,
    })
    color_key = colors[0]["key"] if colors else ""
    for cut in cuts:
        for size in catalog.sizes_for_cut(cut):
            await pb.create("shop_variants", {"product": product["id"], "cut": cut, "size": size, "color": color_key,
                                              "stock": 0, "sku": "", "active": True})
    await pb.update("shop_designs", did, {"product": product["id"], "status": "done"})
    return {"product": product}
