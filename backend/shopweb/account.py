"""Optional customer accounts: register, log in, profile, family sizes, orders,
personal vouchers. Plain HTML forms (they work without JavaScript)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from cs import catalog, util
from cs.pb import PBError, pb, q

from . import i18n, session, stats, store
from .render import lang_of, render

router = APIRouter(prefix="/account")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,}$", re.I)
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
login_limit = util.Window(10, 600)
register_limit = util.Window(5, 3600)


def ip(request: Request) -> str:
    return request.client.host if request.client else ""


def safe_next(value: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") and len(value) < 300 else "/account"


def need_customer(request: Request) -> dict:
    c = request.state.customer
    if not c:
        raise HTTPException(401)
    return c


def privacy_page():
    return next((p for p in store.C.pages if p["slug"] in ("privacy", "kebijakan-privasi")), None)


# ---------------------------------------------------------------------------
# Log in / register / log out
# ---------------------------------------------------------------------------

@router.get("/login")
async def login_form(request: Request, next: str = "/account"):
    if request.state.customer:
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "account/login.html", title=i18n.t("a.login", lang_of(request)), next=safe_next(next),
                  noindex=True)


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/account")):
    lang = lang_of(request)
    ok, _ = login_limit.allow(ip(request))
    res = await session.login(email, password) if ok and len(password) <= 72 else None
    if not res:
        return render(request, "account/login.html", 400, title=i18n.t("a.login", lang), next=safe_next(next),
                      email=email, error=i18n.t("a.bad_login", lang) if ok else "Too many attempts. Wait 10 minutes.",
                      noindex=True)
    _, token = res
    resp = RedirectResponse(safe_next(next), status_code=303)
    session.set_session(resp, token)
    stats.add("logins")
    return resp


@router.get("/register")
async def register_form(request: Request, next: str = "/account"):
    if request.state.customer:
        return RedirectResponse("/account", status_code=303)
    return render(request, "account/register.html", title=i18n.t("a.register", lang_of(request)), next=safe_next(next),
                  privacy=privacy_page(), noindex=True, form={})


@router.post("/register")
async def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...),
                   phone: str = Form(""), marketing: str = Form(""), agree: str = Form(""), next: str = Form("/account"),
                   website: str = Form("")):
    lang = lang_of(request)
    form = {"name": name, "email": email, "phone": phone, "marketing": marketing}

    def fail(msg: str, status: int = 400):
        return render(request, "account/register.html", status, title=i18n.t("a.register", lang), next=safe_next(next),
                      privacy=privacy_page(), error=msg, form=form, noindex=True)

    if website:  # honeypot field, hidden from people
        return fail("Blocked.")
    ok, _ = register_limit.allow(ip(request))
    if not ok:
        return fail("Too many new accounts from this network. Try later.", 429)
    email = email.strip().lower()
    name = name.strip()[:120]
    if not EMAIL.match(email) or len(email) > 200:
        return fail("Email?")
    if not (8 <= len(password) <= 72):
        return fail(i18n.t("a.password_new", lang))
    if not name:
        return fail(i18n.t("a.name", lang) + ": " + i18n.t("co.required", lang))
    if agree != "1":
        return fail(i18n.t("a.agree", lang, link=i18n.t("co.privacy_link", lang)))
    digits = util.normalize_phone(phone)
    if phone and not util.valid_phone(digits):
        return fail(i18n.t("co.bad_phone", lang))
    try:
        await pb.create("shop_customers", {"email": email, "password": password, "passwordConfirm": password,
                                           "name": name, "phone": digits if phone else "", "lang": lang,
                                           "marketing_ok": marketing == "1", "emailVisibility": False})
    except PBError as e:
        if "email" in str(e.data):
            return fail(i18n.t("a.exists", lang), 409)
        raise
    res = await session.login(email, password)
    resp = RedirectResponse(safe_next(next) if next != "/account" else "/account/family?welcome=1", status_code=303)
    if res:
        session.set_session(resp, res[1])
    stats.add("registrations")
    return resp


@router.post("/logout")
async def logout(request: Request):
    resp = RedirectResponse("/", status_code=303)
    session.clear_session(resp, request.cookies.get(session.COOKIE, ""))
    return resp


# ---------------------------------------------------------------------------
# Account home
# ---------------------------------------------------------------------------

@router.get("")
async def account(request: Request):
    c = request.state.customer
    if not c:
        return RedirectResponse("/account/login", status_code=303)
    orders = (await pb.list("shop_orders", filter=f"customer = {q(c['id'])}", sort="-created", per_page=50,
                            fields="id,number,status,total,created,token")).get("items", [])
    now = util.pb_now()
    vouchers = await pb.all("shop_vouchers", filter=f"customer = {q(c['id'])} && active = true && (ends = '' || ends > {q(now)})")
    members = await pb.all("shop_family_members", filter=f"customer = {q(c['id'])}", sort="sort,created")
    return render(request, "account/home.html", title=i18n.t("nav.account", lang_of(request)), orders=orders,
                  vouchers=vouchers, members=members, saved=request.query_params.get("saved") == "1", noindex=True)


@router.post("/profile")
async def profile(request: Request, name: str = Form(""), phone: str = Form(""), birthday: str = Form(""),
                  anniversary: str = Form(""), marketing: str = Form(""), lang: str = Form("id")):
    c = need_customer(request)
    digits = util.normalize_phone(phone)
    await pb.update("shop_customers", c["id"], {
        "name": name.strip()[:120], "phone": digits if phone and util.valid_phone(digits) else c.get("phone", ""),
        "birthday": birthday if DATE.match(birthday) else "", "anniversary": anniversary if DATE.match(anniversary) else "",
        "marketing_ok": marketing == "1", "lang": lang if lang in i18n.LANGS else "id"})
    session.forget(request.cookies.get(session.COOKIE, ""))
    resp = RedirectResponse(f"/account?saved=1&lang={lang if lang in i18n.LANGS else 'id'}", status_code=303)
    return resp


@router.post("/password")
async def password(request: Request, old: str = Form(...), new: str = Form(...)):
    c = need_customer(request)
    lang = lang_of(request)
    if not (8 <= len(new) <= 72):
        raise HTTPException(400, i18n.t("a.password_new", lang))
    if not await session.login(c["email"], old):
        raise HTTPException(400, i18n.t("a.wrong_old", lang))
    await pb.update("shop_customers", c["id"], {"oldPassword": old, "password": new, "passwordConfirm": new})
    res = await session.login(c["email"], new)
    resp = RedirectResponse("/account?saved=1", status_code=303)
    if res:
        session.set_session(resp, res[1])
    return resp


# ---------------------------------------------------------------------------
# Family size profiles
# ---------------------------------------------------------------------------

@router.get("/family")
async def family(request: Request):
    c = request.state.customer
    if not c:
        return RedirectResponse("/account/login?next=/account/family", status_code=303)
    members = await pb.all("shop_family_members", filter=f"customer = {q(c['id'])}", sort="sort,created")
    lang = lang_of(request)
    cut_sizes = {cut: [{"id": s, "label": catalog.size_label(s, lang)} for s in catalog.sizes_for_cut(cut)]
                 for cut in catalog.CUTS}
    roles = [{"id": k, "label": v[lang], "cuts": v["cuts"]} for k, v in catalog.ROLES.items()]
    return render(request, "account/family.html", title=i18n.t("a.family", lang), members=members, roles=roles,
                  cut_sizes=cut_sizes, welcome=request.query_params.get("welcome") == "1", noindex=True)


@router.post("/family")
async def family_save(request: Request, action: str = Form("save"), member_id: str = Form(""), name: str = Form(""),
                      role: str = Form(""), cut: str = Form(""), size: str = Form(""), birthday: str = Form("")):
    c = need_customer(request)
    if action == "delete":
        rec = await pb.get("shop_family_members", util.rid(member_id))
        if rec["customer"] != c["id"]:
            raise HTTPException(404)
        await pb.delete("shop_family_members", rec["id"])
        return RedirectResponse("/account/family", status_code=303)
    if cut not in catalog.CUTS:
        raise HTTPException(400, "Choose a cut.")
    if size and size not in catalog.sizes_for_cut(cut):
        size = ""
    data = {"customer": c["id"], "name": name.strip()[:80], "role": (role or "other").strip()[:40], "cut": cut,
            "size": size, "birthday": birthday if DATE.match(birthday) else ""}
    if member_id:
        rec = await pb.get("shop_family_members", util.rid(member_id))
        if rec["customer"] != c["id"]:
            raise HTTPException(404)
        await pb.update("shop_family_members", rec["id"], data)
    else:
        count = len(await pb.all("shop_family_members", filter=f"customer = {q(c['id'])}", fields="id"))
        if count >= 20:
            raise HTTPException(400, "That's a big family! Max 20.")
        await pb.create("shop_family_members", {**data, "sort": count})
    return RedirectResponse("/account/family", status_code=303)
