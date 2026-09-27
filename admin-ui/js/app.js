import { $, $$, api, el, fetchRetry, icon, setAuthHandler } from "./lib.js?v=__VERSION__"
import { renderDashboard } from "./dashboard.js?v=__VERSION__"
import { renderOrders, renderOrder } from "./orders.js?v=__VERSION__"
import { renderProducts, renderProduct } from "./products.js?v=__VERSION__"
import { renderCustomers, renderCustomer, renderReviews } from "./customers.js?v=__VERSION__"
import { renderPromos } from "./promos.js?v=__VERSION__"
import { renderContent } from "./content.js?v=__VERSION__"
import { renderCatalog } from "./catalog.js?v=__VERSION__"
import { renderSettings } from "./settings.js?v=__VERSION__"
import { renderStudio, renderDesign } from "./studio.js?v=__VERSION__"

export const state = { me: null, locked: false, brand: "Shop Admin", shopUrl: "" }

function show(which) {
  $("#splash").hidden = true
  for (const id of ["authView", "lockView", "appView"]) $(`#${id}`).hidden = id !== which
}
for (const span of $$(".tab-ico")) span.replaceWith(icon(span.dataset.icon))

function renderMore(page) {
  const item = (hash, ico, label, sub) => el("a", { class: "more-item", href: `#${hash}` }, icon(ico), el("span", {}, el("b", { text: label }), el("small", { text: sub })), icon("chevron"))
  page.append(el("h1", { text: "More" }), el("div", { class: "card list" },
    item("customers", "users", "Customers", "Accounts, family sizes, password resets"),
    item("reviews", "star", "Reviews", "Approve family reviews and photos"),
    item("promos", "tag", "Promotions", "Vouchers, family-set discounts, sales"),
    item("content", "layout", "Content", "Homepage, pages, journal, lookbook"),
    item("catalog", "grid", "Categories & sizes", "Categories, collections, size charts"),
    item("settings", "gear", "Settings", "Brand, WhatsApp, admins, notifications, Face ID")),
  el("a", { class: "btn wide", href: state.shopUrl || "#", target: "_blank", rel: "noopener", style: { marginTop: "16px" } }, icon("store"), "Open the shop"))
}

const ROUTES = {
  dashboard: [renderDashboard, "dashboard"], orders: [renderOrders, "orders"], order: [renderOrder, "orders"],
  products: [renderProducts, "products"], product: [renderProduct, "products"], studio: [renderStudio, "studio"],
  design: [renderDesign, "studio"], customers: [renderCustomers, "customers"], customer: [renderCustomer, "customers"],
  reviews: [renderReviews, "reviews"], promos: [renderPromos, "promos"], content: [renderContent, "content"],
  catalog: [renderCatalog, "catalog"], settings: [renderSettings, "settings"], more: [renderMore, "more"],
}
const MOBILE_TAB = { customers: "more", reviews: "more", promos: "more", content: "more", catalog: "more", settings: "more" }

let rendering = 0
export async function route() {
  if (!state.me || state.locked) return
  const [name, arg, arg2] = (location.hash.replace(/^#/, "") || "dashboard").split("/")
  const [fn, tab] = ROUTES[name] || ROUTES.dashboard
  show("appView")
  for (const a of $$(".side a[data-tab]")) a.classList.toggle("on", a.dataset.tab === tab)
  for (const a of $$(".tabbar a")) a.classList.toggle("on", a.dataset.tab === (MOBILE_TAB[tab] || tab))
  const my = ++rendering
  const page = el("div", { class: "view" })
  $("#page").replaceChildren(page)
  window.scrollTo(0, 0)
  try {
    await fn(page, arg, arg2)
  } catch (err) {
    if (my !== rendering || [401, 403, 423].includes(err.status)) return
    page.replaceChildren(el("div", { class: "empty-state" }, el("h3", { text: "Couldn't load this page" }), el("p", { class: "muted", text: err.message }),
      el("button", { class: "btn small", onclick: route, text: "Try again" })))
  }
  refreshBadges()
}
window.addEventListener("hashchange", route)
export const go = (hash) => { if (location.hash === `#${hash}`) route(); else location.hash = hash }

export async function refreshBadges() {
  try {
    const d = await api("/badges", { quiet: true })
    for (const b of $$("[data-badge]")) {
      const n = d[b.dataset.badge] || 0
      b.textContent = n > 99 ? "99+" : String(n)
      b.hidden = !n
    }
    if ("setAppBadge" in navigator) navigator.setAppBadge(d.orders || 0).catch(() => {})
  } catch (_) {}
}

// ---------------------------------------------------------------------------
// Login + Face ID lock
// ---------------------------------------------------------------------------
function renderAuth(message = "") {
  show("authView")
  const user = el("input", { autocomplete: "username", autocapitalize: "none", autocorrect: "off", spellcheck: "false", maxlength: 32, required: true })
  const pass = el("input", { type: "password", autocomplete: "current-password", maxlength: 72, required: true })
  const msg = el("p", { class: "form-msg", role: "alert", text: message })
  const submit = el("button", { class: "btn primary wide", type: "submit", text: "Log in" })
  const f = el("form", {}, el("label", { class: "field" }, el("span", { text: "Username" }), user),
    el("label", { class: "field" }, el("span", { text: "Password" }), pass), msg, submit,
    el("p", { class: "hint center", text: "Same account as lyrsync and the finance app." }))
  f.addEventListener("submit", async (e) => {
    e.preventDefault()
    msg.textContent = ""
    submit.disabled = true
    try {
      const d = await api("/login", { method: "POST", json: { username: user.value.trim().toLowerCase(), password: pass.value }, quiet: true })
      pass.value = ""
      state.me = d.user
      if (d.locked) return renderLock()
      await afterLogin()
    } catch (err) { msg.textContent = err.message } finally { submit.disabled = false }
  })
  $("#authView").replaceChildren(el("div", { class: "card auth-card" },
    el("div", { class: "brand" }, el("img", { src: "/icons/icon-192.png", width: 56, height: 56, alt: "" }), el("h1", { text: "Shop Admin" }),
      el("p", { class: "muted", text: "Orders, products, content and the AI design studio." })), f))
}

const b64u = {
  toBuf: (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0)).buffer,
  fromBuf: (b) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""),
}
function credToJSON(cred) {
  if (cred.toJSON) { try { return cred.toJSON() } catch (_) {} }
  const r = cred.response
  const out = { id: cred.id, rawId: b64u.fromBuf(cred.rawId), type: cred.type, clientExtensionResults: cred.getClientExtensionResults(), response: { clientDataJSON: b64u.fromBuf(r.clientDataJSON) } }
  if (r.attestationObject) { out.response.attestationObject = b64u.fromBuf(r.attestationObject); if (r.getTransports) out.response.transports = r.getTransports() }
  else { out.response.authenticatorData = b64u.fromBuf(r.authenticatorData); out.response.signature = b64u.fromBuf(r.signature); if (r.userHandle) out.response.userHandle = b64u.fromBuf(r.userHandle) }
  return out
}
export async function registerPasskey() {
  if (!window.PublicKeyCredential) throw new Error("This device doesn't support Face ID sign-in here.")
  const opts = await api("/passkey/register/options", { method: "POST" })
  const publicKey = PublicKeyCredential.parseCreationOptionsFromJSON ? PublicKeyCredential.parseCreationOptionsFromJSON(opts) : {
    ...opts, challenge: b64u.toBuf(opts.challenge), user: { ...opts.user, id: b64u.toBuf(opts.user.id) },
    excludeCredentials: (opts.excludeCredentials || []).map((c) => ({ ...c, id: b64u.toBuf(c.id) })) }
  const cred = await navigator.credentials.create({ publicKey })
  await api("/passkey/register/verify", { method: "POST", json: { credential: credToJSON(cred), name: navigator.platform || "iPhone" } })
}
async function unlockWithPasskey() {
  const opts = await api("/passkey/auth/options", { method: "POST", quiet: true })
  const publicKey = PublicKeyCredential.parseRequestOptionsFromJSON ? PublicKeyCredential.parseRequestOptionsFromJSON(opts) : {
    ...opts, challenge: b64u.toBuf(opts.challenge), allowCredentials: (opts.allowCredentials || []).map((c) => ({ ...c, id: b64u.toBuf(c.id) })) }
  const cred = await navigator.credentials.get({ publicKey })
  await api("/passkey/auth/verify", { method: "POST", json: { credential: credToJSON(cred) }, quiet: true })
}
function renderLock() {
  state.locked = true
  show("lockView")
  const msg = el("p", { class: "form-msg", role: "alert" })
  const btn = el("button", { class: "btn primary wide", type: "button" }, icon("face"), "Unlock with Face ID")
  btn.onclick = async () => {
    msg.textContent = ""
    btn.disabled = true
    try { await unlockWithPasskey(); state.locked = false; await afterLogin() } catch (err) {
      msg.textContent = err.name === "NotAllowedError" ? "Face ID was cancelled. Try again." : err.message
    } finally { btn.disabled = false }
  }
  const logout = el("button", { class: "link-btn", type: "button", text: "Log out instead" })
  logout.onclick = async () => { await api("/logout", { method: "POST", quiet: true }).catch(() => {}); state.me = null; state.locked = false; renderAuth() }
  $("#lockView").replaceChildren(el("div", { class: "card lock-card" }, icon("lock", "big"), el("h2", { text: "Locked" }),
    el("p", { class: "muted", text: "Shop data is protected. Unlock to continue." }), btn, msg, logout))
}
let hiddenAt = 0
document.addEventListener("visibilitychange", async () => {
  if (document.hidden) { hiddenAt = Date.now(); return }
  if (state.me && !state.locked && hiddenAt && Date.now() - hiddenAt > 5 * 60 * 1000) {
    try { const me = await api("/me", { quiet: true }); if (me.locked) return renderLock() } catch (_) {}
  }
  if (state.me && !state.locked) refreshBadges()
})
setAuthHandler((status, data) => {
  if (status === 423) { if (!state.locked) renderLock() }
  else if (status === 401) { state.me = null; renderAuth(data.error || "Please log in.") }
  else if (status === 403 && /access/.test(data.error || "")) { state.me = null; renderAuth(data.error) }
})

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------
export async function enablePush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) throw new Error("Notifications need the Home Screen app (Share → Add to Home Screen), iOS 16.4 or later.")
  const perm = await Notification.requestPermission()
  if (perm !== "granted") throw new Error("Notifications are blocked. Allow them in the phone's Settings → Notifications.")
  const reg = await navigator.serviceWorker.ready
  const { key } = await api("/push/key")
  let sub = await reg.pushManager.getSubscription()
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: new Uint8Array(b64u.toBuf(key)) })
  const j = sub.toJSON()
  await api("/push/subscribe", { method: "POST", json: { endpoint: j.endpoint, p256dh: j.keys.p256dh, auth: j.keys.auth, ua: navigator.userAgent.slice(0, 300) } })
}
export async function pushStatus() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return "unsupported"
  if (Notification.permission === "denied") return "blocked"
  const reg = await navigator.serviceWorker.ready
  return (await reg.pushManager.getSubscription()) ? "on" : "off"
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function afterLogin() {
  const me = await api("/me")
  state.brand = me.brand || "Shop Admin"
  state.shopUrl = me.shop_url || ""
  $("#brandName").textContent = state.brand
  $("#shopLink").href = state.shopUrl || "#"
  await route()
}
async function boot() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {})
    navigator.serviceWorker.addEventListener("message", (e) => {
      if (e.data && e.data.type === "navigate" && e.data.url) location.hash = e.data.url.split("#")[1] || "dashboard"
    })
  }
  try {
    const res = await fetchRetry("/api/me", { credentials: "same-origin" }, 4)
    const data = await res.json().catch(() => ({}))
    if (res.status === 200) { state.me = data.user; if (data.locked) return renderLock(); await afterLogin() }
    else renderAuth(res.status === 403 ? data.error : "")
  } catch (_) {
    renderAuth("No connection yet. Retrying when you're back online…")
    window.addEventListener("online", () => boot(), { once: true })
    setTimeout(() => { if (!state.me) boot() }, 5000)
  }
}
boot()
