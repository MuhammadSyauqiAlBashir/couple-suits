"""Jinja rendering with the shop's helpers (language, prices, images, links)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from cs import catalog, config, util

from . import i18n, store

HERE = os.path.dirname(__file__)
STATIC = os.path.join(HERE, "static")

env = Environment(loader=FileSystemLoader(os.path.join(HERE, "templates")), autoescape=select_autoescape(["html", "xml"]),
                  trim_blocks=True, lstrip_blocks=True)


def _static_version() -> str:
    h = hashlib.sha256()
    for root, _, files in sorted(os.walk(STATIC)):
        for f in sorted(files):
            if f.endswith((".css", ".js")):
                with open(os.path.join(root, f), "rb") as fh:
                    h.update(fh.read())
    return h.hexdigest()[:10]


VERSION = _static_version()


def static(path: str) -> str:
    return f"/static/{path}?v={VERSION}"


def lang_of(request: Request) -> str:
    return getattr(request.state, "lang", "id")


def rupiah(n) -> str:
    return catalog.rupiah(n)


def img(key: str, alt: str = "", sizes: str = "(max-width: 700px) 50vw, 25vw", cls: str = "", eager: bool = False,
        width: int = 800) -> Markup:
    if not key:
        return Markup(f'<span class="ph {cls}" role="img" aria-label="{Markup.escape(alt)}"></span>')
    loading = 'fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
    return Markup(
        f'<img src="{catalog.media_url(key, width)}" srcset="{catalog.srcset(key)}" sizes="{sizes}" '
        f'alt="{Markup.escape(alt)}" class="{cls}" {loading}>')


def md(text: str) -> Markup:
    return Markup(util.markdown(text))


def tojson_attr(value) -> str:
    return json.dumps(value, ensure_ascii=False)


env.filters["rupiah"] = rupiah
env.filters["md"] = md
env.globals.update(img=img, static=static, catalog=catalog, config=config, util=util, urlencode=urlencode)


def render(request: Request, template: str, status: int = 200, **ctx) -> HTMLResponse:
    lang = lang_of(request)
    settings = request.state.settings

    def t(key: str, **kw) -> str:
        return i18n.t(key, lang, **kw)

    def tr(rec: dict, field: str) -> str:
        return catalog.tr(rec or {}, field, lang)

    def tl(key: str, href: str, link_key: str) -> Markup:
        """Translated sentence with one link in it ({link} in the text)."""
        before, _, after = i18n.t(key, lang, link="\x00").partition("\x00")
        return (Markup.escape(before) + Markup('<a href="%s">') % href + Markup.escape(i18n.t(link_key, lang))
                + Markup("</a>") + Markup.escape(after))

    def lang_url(to: str) -> str:
        params = dict(request.query_params)
        params["lang"] = to
        return f"{request.url.path}?{urlencode(params)}"

    base = {
        "request": request, "lang": lang, "t": t, "tl": tl, "tr": tr, "s": settings, "lang_url": lang_url,
        "customer": getattr(request.state, "customer", None), "categories": store.C.categories,
        "collections": store.C.collections, "footer_pages": [p for p in store.C.pages if p.get("in_footer")],
        "brand": settings.get("brand_name") or "Couple Suits", "path": request.url.path,
        "canonical": config.SHOP_URL + request.url.path, "js_strings": i18n.js_strings(lang),
        "wa": util.wa_link(settings.get("whatsapp") or "", ""), "label": lambda d, k: catalog.label(d, k, lang),
        "size_label": lambda s: catalog.size_label(s, lang),
        "accent": settings["accent"] if re.fullmatch(r"#[0-9a-fA-F]{6}", str(settings.get("accent") or "")) else "#1c1b19",
    }
    base.update(ctx)
    html = env.get_template(template).render(**base)
    return HTMLResponse(html, status_code=status)
