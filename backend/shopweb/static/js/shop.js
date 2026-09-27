// Storefront scripts: cart, wishlist, family set builder, checkout.
// Everything the server renders works on its own; this adds the shopping bits.

const $ = (s, r = document) => r.querySelector(s)
const $$ = (s, r = document) => [...r.querySelectorAll(s)]
const T = JSON.parse(($("#i18n") || {}).textContent || "{}")
const t = (k, vars = {}) => (T[k] || k).replace(/\{(\w+)\}/g, (_, v) => (v in vars ? vars[v] : `{${v}}`))
const LANG = document.body.dataset.lang || "id"
const IS_CUSTOMER = document.body.dataset.customer === "1"
const nf = new Intl.NumberFormat("id-ID")
const rp = (n) => (n < 0 ? "−Rp" : "Rp") + nf.format(Math.abs(Math.round(n || 0)))
const round100 = (x) => Math.round(x / 100) * 100
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag)
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue
    if (k === "class") n.className = v
    else if (k === "text") n.textContent = v
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v)
    else if (k === "value") n.value = v
    else n.setAttribute(k, v === true ? "" : v)
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) n.append(c instanceof Node ? c : document.createTextNode(String(c)))
  return n
}
const SVGNS = "http://www.w3.org/2000/svg"
function ico(name) {
  const s = document.createElementNS(SVGNS, "svg")
  s.setAttribute("class", "i")
  const u = document.createElementNS(SVGNS, "use")
  u.setAttribute("href", `#i-${name}`)
  s.append(u)
  return s
}

const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v) } catch (_) { return d } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch (_) {} },
}

let toastTimer
function toast(msg) {
  const box = $("#toast")
  if (!box) return
  box.textContent = msg
  box.hidden = false
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (box.hidden = true), 3000)
}

// iOS may reuse a dead connection after a long sleep: retry reads, never writes.
async function api(path, { method = "GET", json } = {}) {
  const opts = { method, credentials: "same-origin", headers: { "X-CS": "1" } }
  if (json !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(json) }
  let res
  for (let i = 0; ; i++) {
    try { res = await fetch(path, opts); break } catch (e) {
      if (method !== "GET" || i >= 2) throw new Error(LANG === "en" ? "No connection. Check your internet." : "Tidak ada koneksi. Cek internetmu.")
      await sleep(600 * (i + 1))
    }
  }
  let data = {}
  try { data = await res.json() } catch (_) {}
  if (!res.ok) { const err = new Error(data.error || `Error ${res.status}`); err.status = res.status; err.data = data; throw err }
  return data
}
const ev = (e, p = "", n = 1) => { api("/api/ev", { method: "POST", json: { e, p, n } }).catch(() => {}) }

// ---------------------------------------------------------------------------
// Shared UI: dialogs, swatches, countdowns, selects, events
// ---------------------------------------------------------------------------
function wireDialogs(root = document) {
  for (const b of $$("[data-open]", root)) b.addEventListener("click", () => {
    const d = document.getElementById(b.dataset.open)
    if (!d) return
    d.showModal()
    if (b.dataset.open === "search") setTimeout(() => $("input", d).focus(), 30)
  })
  for (const d of $$("dialog", root)) {
    d.addEventListener("click", (e) => { if (e.target === d || e.target.closest("[data-close]")) d.close() })
  }
}
function paintSwatches(root = document) {
  for (const i of $$("[data-hex]", root)) if (/^#[0-9a-f]{3,8}$/i.test(i.dataset.hex)) i.style.background = i.dataset.hex
}
function countdowns() {
  for (const box of $$("[data-countdown]")) {
    const end = new Date(box.dataset.countdown.replace(" ", "T")).getTime()
    const out = $("b", box)
    const tick = () => {
      let s = Math.max(0, Math.floor((end - Date.now()) / 1000))
      if (!s) { box.hidden = true; return }
      const d = Math.floor(s / 86400); s -= d * 86400
      const h = Math.floor(s / 3600); s -= h * 3600
      const m = Math.floor(s / 60)
      out.textContent = `${d ? d + t("days") + " " : ""}${h}${t("hours")} ${m}${t("minutes")}`
      setTimeout(tick, 30000)
    }
    tick()
  }
}
for (const s of $$("[data-autosubmit]")) s.addEventListener("change", () => s.form.submit())
document.addEventListener("click", (e) => { const a = e.target.closest("[data-ev]"); if (a) ev(a.dataset.ev) })

// ---------------------------------------------------------------------------
// Cart (browser storage; the server re-prices everything)
// ---------------------------------------------------------------------------
const cart = {
  lines: () => store.get("cs_cart", []),
  save(lines) { store.set("cs_cart", lines); badge() },
  add(newLines) {
    const lines = cart.lines()
    for (const n of newLines) {
      const same = !n.set_key && lines.find((l) => !l.set_key && l.product === n.product && l.cut === n.cut && l.size === n.size && l.color === n.color && l.role === n.role && l.member === n.member)
      if (same) same.qty = Math.min(20, same.qty + n.qty)
      else lines.push(n)
    }
    cart.save(lines)
  },
  count: () => cart.lines().reduce((a, l) => a + (l.qty || 1), 0),
}
function badge() {
  const n = cart.count()
  for (const b of $$("[data-cart-count]")) { b.textContent = n > 99 ? "99+" : n; b.hidden = !n }
  const w = wish.ids().length
  for (const b of $$("[data-wish-count]")) { b.textContent = w; b.hidden = !w }
}

// ---------------------------------------------------------------------------
// Wishlist
// ---------------------------------------------------------------------------
const wish = {
  ids: () => store.get("cs_wish", []),
  has: (id) => wish.ids().includes(id),
  async toggle(id) {
    const ids = wish.ids()
    const on = !ids.includes(id)
    store.set("cs_wish", on ? [id, ...ids].slice(0, 200) : ids.filter((x) => x !== id))
    paintWish()
    badge()
    if (IS_CUSTOMER) api("/api/wishlist", { method: "POST", json: { product: id, on } }).catch(() => {})
    toast(on ? t("p.wished") : "♡")
  },
  async sync() {
    if (!IS_CUSTOMER || sessionStorage.getItem("cs_wish_synced")) return
    try {
      const data = await api("/api/wishlist/merge", { method: "POST", json: { ids: wish.ids() } })
      store.set("cs_wish", data.ids)
      sessionStorage.setItem("cs_wish_synced", "1")
      paintWish(); badge()
    } catch (_) {}
  },
}
function paintWish() {
  const ids = wish.ids()
  for (const b of $$("[data-wish]")) {
    const on = ids.includes(b.dataset.wish)
    b.setAttribute("aria-pressed", on ? "true" : "false")
    const lab = $("[data-wish-label]", b)
    if (lab) lab.textContent = on ? t("p.wished") : t("p.wish")
  }
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-wish]")
  if (b) { e.preventDefault(); wish.toggle(b.dataset.wish) }
})

// Cards rendered in the browser (wishlist, recently viewed, picks).
function cardEl(c) {
  const price = el("span", { class: "price" },
    c.price_max && c.price_max !== c.price ? [el("span", { class: "from", text: t("price.from") }), " "] : null,
    el("span", { class: `now${c.on_sale ? " sale" : ""}`, text: rp(c.price) }),
    c.on_sale ? [" ", el("s", { class: "was", text: rp(c.regular) })] : null)
  const img = (key, cls) => key ? el("img", { src: `/media/${key}/800.webp`, srcset: [400, 800, 1200].map((w) => `/media/${key}/${w}.webp ${w}w`).join(", "),
    sizes: "(max-width: 700px) 50vw, 25vw", alt: cls === "a" ? c.name : "", loading: "lazy", class: cls }) : el("span", { class: "ph" })
  const node = el("article", { class: "card", "data-product": c.id },
    el("a", { class: "card-media", href: `/p/${c.slug}`, tabindex: "-1", "aria-hidden": "true" }, img(c.image, "a"), c.image2 ? img(c.image2, "b") : null,
      el("span", { class: "badges" }, c.on_sale ? el("b", { class: "badge sale", text: `−${c.sale_percent}%` }) : null,
        c.preorder ? el("b", { class: "badge", text: t("badge.preorder") }) : null)),
    el("button", { class: "wish", type: "button", "data-wish": c.id, "aria-label": t("p.wish"), "aria-pressed": "false" }, ico("heart")),
    el("div", { class: "card-body" }, el("h3", {}, el("a", { href: `/p/${c.slug}`, text: c.name })),
      c.for_text ? el("p", { class: "card-for", text: c.for_text }) : null,
      el("div", { class: "card-foot" }, price)))
  return node
}
async function fillGrid(grid, ids, url = "/api/cards") {
  if (!ids.length) return 0
  const data = await api(`${url}?ids=${ids.join(",")}`)
  const order = new Map(ids.map((id, i) => [id, i]))
  const cards = url === "/api/cards" ? data.cards.sort((a, b) => order.get(a.id) - order.get(b.id)) : data.cards
  grid.replaceChildren(...cards.map(cardEl))
  paintWish()
  return cards.length
}

// ---------------------------------------------------------------------------
// Product page: gallery dots, recently viewed, the family set builder
// ---------------------------------------------------------------------------
function gallery() {
  const g = $("[data-gallery]")
  if (!g) return
  const dots = $$(".dots i", g.parentElement)
  if (!dots.length) return
  dots[0].classList.add("on")
  g.addEventListener("scroll", () => {
    const i = Math.round(g.scrollLeft / g.clientWidth)
    dots.forEach((d, j) => d.classList.toggle("on", i === j))
  }, { passive: true })
}

function productPage() {
  const P = JSON.parse($("#product-data").textContent)
  const recent = store.get("cs_recent", []).filter((x) => x !== P.id)
  store.set("cs_recent", [P.id, ...recent].slice(0, 16))
  gallery()
  const app = $("[data-builder-app]")
  if (!P.cuts.length || !P.roles.length) { app.replaceChildren(el("p", { class: "muted", text: t("p.soldout") })); return }

  const cutById = Object.fromEntries(P.cuts.map((c) => [c.id, c]))
  const roleById = Object.fromEntries(P.roles.map((r) => [r.id, r]))
  const state = { color: P.colors.length ? P.colors[0].key : "", members: [] }

  const colorBox = $("[data-colors]")
  if (colorBox) colorBox.addEventListener("change", (e) => {
    state.color = e.target.value
    const c = P.colors.find((x) => x.key === state.color)
    $("[data-color-name]").textContent = c ? c.name : ""
    for (const m of state.members) if (m.size && !available(m.cut, m.size)) m.size = ""
    draw()
  })

  const stockOf = (cut, size) => {
    const k1 = `${cut}|${size}|${state.color}`, k2 = `${cut}|${size}|`
    return k1 in P.stock ? P.stock[k1] : k2 in P.stock ? P.stock[k2] : null
  }
  const available = (cut, size) => { const s = stockOf(cut, size); return s !== null && (P.preorder || s > 0) }
  const member = (roleId, extra = {}) => {
    const role = roleById[roleId] || roleById.other || P.roles[0]
    return { role: role.id, name: "", cut: role.cuts[0], size: "", qty: 1, ...extra }
  }
  const setMembers = (list) => { state.members = list; draw() }

  function presetBar() {
    const bar = el("div", { class: "presets", role: "group", "aria-label": t("p.presets") })
    bar.append(el("button", { class: "chip", type: "button", text: t("p.single"), onclick: () => setMembers([member(P.roles[0].id)]) }))
    for (const pr of P.presets) bar.append(el("button", { class: "chip", type: "button", text: pr.label, onclick: () => setMembers(pr.roles.map((r) => member(r))) }))
    const fam = P.family.filter((f) => cutById[f.cut])
    if (fam.length) {
      bar.prepend(el("button", { class: "chip family-chip", type: "button", onclick: () => {
        setMembers(fam.map((f) => member(roleById[f.role] ? f.role : "other", { name: f.name, cut: f.cut, size: available(f.cut, f.size) ? f.size : "" })))
        ev("set_built", P.id, fam.length)
      } }, ico("users"), " ", t("p.use_family")))
    }
    return bar
  }

  function memberRow(m, i) {
    const role = roleById[m.role] || P.roles[0]
    const roleSel = el("select", { "aria-label": t("p.role") }, P.roles.map((r) => el("option", { value: r.id, text: r.label })))
    roleSel.value = m.role
    roleSel.onchange = () => {
      m.role = roleSel.value
      const r = roleById[m.role]
      if (!r.cuts.includes(m.cut)) { m.cut = r.cuts[0]; m.size = "" }
      draw()
    }
    const name = el("input", { value: m.name, maxlength: 80, "aria-label": t("p.name"), placeholder: m.role === "other" ? t("roles.other_ph") : t("p.name") })
    name.oninput = () => { m.name = name.value }
    const remove = state.members.length > 1 ? el("button", { class: "icon-btn", type: "button", "aria-label": t("p.remove"), onclick: () => { state.members.splice(i, 1); draw() } }, ico("x")) : el("span")
    const cuts = role.cuts.length > 1 ? el("div", { class: "m-cuts", role: "group", "aria-label": t("p.cut") },
      role.cuts.map((c) => el("button", { type: "button", class: `seg${m.cut === c ? " on" : ""}`, text: cutById[c].label,
        onclick: () => { m.cut = c; if (!available(c, m.size)) m.size = ""; draw() } }))) : null
    const cut = cutById[m.cut]
    const sizes = el("div", { class: "m-sizes", role: "group", "aria-label": t("p.size") }, cut.sizes.map((s) => {
      const st = stockOf(m.cut, s.id)
      const ok = available(m.cut, s.id)
      const b = el("button", { type: "button", class: `size${m.size === s.id ? " on" : ""}`, disabled: !ok, "aria-pressed": m.size === s.id ? "true" : "false",
        onclick: () => { m.size = m.size === s.id ? "" : s.id; draw() } }, s.label)
      if (ok && !P.preorder && st !== null && st <= 3) b.append(el("small", { text: t("p.left", { n: st }) }))
      return b
    }))
    const qty = el("span", { class: "qty" },
      el("button", { type: "button", "aria-label": "−", onclick: () => { m.qty = Math.max(1, m.qty - 1); draw() } }, ico("minus")),
      el("span", { text: m.qty }),
      el("button", { type: "button", "aria-label": "+", onclick: () => { m.qty = Math.min(20, m.qty + 1); draw() } }, ico("plus")))
    const price = cut.price * m.qty
    return el("li", { class: `member${m.missing ? " missing" : ""}` },
      el("div", { class: "m-top" }, roleSel, name, remove), cuts, sizes,
      el("div", { class: "m-foot" }, qty, el("span", {}, cut.regular !== cut.price ? el("s", { class: "muted small", text: rp(cut.regular * m.qty) + " " }) : null, rp(price))))
  }

  function totals() {
    const people = state.members.reduce((a, m) => a + m.qty, 0)
    const sub = state.members.reduce((a, m) => a + cutById[m.cut].price * m.qty, 0)
    const rule = state.members.length > 1 ? [...P.set_rules].sort((a, b) => b.min - a.min).find((r) => people >= r.min) : null
    const disc = rule ? round100(sub * rule.percent / 100) : 0
    return { people, sub, disc, rule, total: sub - disc }
  }

  function draw() {
    const tt = totals()
    const list = el("ol", { class: "members" }, state.members.map(memberRow))
    const sum = el("div", { class: "set-sum" },
      state.members.length > 1 ? el("div", {}, el("span", { text: `${t("p.set_total")} (${tt.people})` }), el("span", { text: rp(tt.sub) })) : null,
      tt.disc ? el("div", { class: "disc" }, el("span", { text: `${t("p.set_discount")} −${tt.rule.percent}%` }), el("span", { text: "−" + rp(tt.disc) })) : null,
      el("div", { class: "grand" }, el("span", { text: t("cart.total") }), el("span", { text: rp(tt.total) })))
    const add = el("button", { class: "btn primary wide big", type: "button", text: state.members.length > 1 ? t("p.add_set") : t("p.add_to_cart"), onclick: addToCart })
    app.replaceChildren(presetBar(), list,
      el("button", { class: "add-member", type: "button", onclick: () => { state.members.push(member(P.roles.find((r) => r.id === "other") ? "other" : P.roles[0].id)); draw() } }, ico("plus"), t("p.add_member")),
      sum, add)
  }

  function addToCart() {
    let missing = false
    for (const m of state.members) { m.missing = !m.size; missing = missing || m.missing }
    if (missing) { draw(); toast(t("p.pick_all")); $(".member.missing", app)?.scrollIntoView({ behavior: "smooth", block: "center" }); return }
    const setKey = state.members.length > 1 ? "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6) : ""
    const roleLabel = (m) => (roleById[m.role] || {}).label || m.role
    cart.add(state.members.map((m) => ({
      product: P.id, slug: P.slug, name: P.name, image: P.image, cut: m.cut, size: m.size, color: state.color, qty: m.qty,
      role: m.role === "other" ? (m.name || "other") : m.role, role_label: roleLabel(m), member: m.role === "other" ? "" : m.name.trim(),
      set_key: setKey, price: cutById[m.cut].price,
    })))
    ev("add_to_cart", P.id, state.members.reduce((a, m) => a + m.qty, 0))
    for (const m of state.members) m.missing = false
    const bar = $("[data-added]")
    bar.hidden = false
    clearTimeout(bar._t)
    bar._t = setTimeout(() => (bar.hidden = true), 6000)
  }

  const couple = P.presets.find((p) => p.id === "couple")
  state.members = couple ? couple.roles.map((r) => member(r)) : [member(P.roles[0].id)]
  draw()
}

// ---------------------------------------------------------------------------
// Cart + checkout
// ---------------------------------------------------------------------------
let voucher = store.get("cs_voucher", "")

async function quote() {
  const lines = cart.lines()
  const phone = ($("[data-checkout] [name=phone]") || {}).value || ""
  return lines.length ? api("/api/quote", { method: "POST", json: { lines, voucher, phone } }) : null
}

function renderTotals(box, q) {
  box.replaceChildren(
    el("dt", { text: t("cart.subtotal") }), el("dd", { text: rp(q.items_total) }),
    ...q.discounts.flatMap((d) => [el("dt", { class: "disc", text: d.label }), el("dd", { class: "disc", text: "−" + rp(d.amount) })]),
    el("dt", { text: t("cart.shipping") }), el("dd", { class: "muted", text: t("cart.shipping_tbc") }),
    el("dt", { class: "grand", text: t("cart.total") }), el("dd", { class: "grand", text: rp(q.total) }))
}

function lineEls(q, { editable }) {
  const local = cart.lines()
  const byIdx = new Map(q.lines.map((l) => [l.idx, l]))
  const groups = []
  const seen = new Map()
  local.forEach((l, i) => {
    const key = l.set_key || `single-${i}`
    if (!seen.has(key)) { seen.set(key, []); groups.push(seen.get(key)) }
    seen.get(key).push([l, i])
  })
  const change = (i, fn) => { const lines = cart.lines(); fn(lines, i); cart.save(lines.filter((x) => x.qty > 0)); refreshCart() }
  return groups.map((g) => {
    const isSet = g.length > 1 || g[0][0].set_key
    return el("div", { class: "cart-group" },
      isSet ? el("p", { class: "eyebrow" }, el("span", { text: `${t("cart.set")} · ${g[0][0].name}` })) : null,
      g.map(([l, i]) => {
        const s = byIdx.get(i)
        const who = [l.role_label || "", l.member ? `(${l.member})` : ""].filter(Boolean).join(" ")
        const cutLabel = s && s.cut_label !== l.role_label ? s.cut_label : ""
        const detail = s ? [who, cutLabel, s.size_label, s.color_label].filter(Boolean).join(" · ") : [who, l.size].join(" · ")
        return el("div", { class: `line${s ? "" : " bad"}` },
          el("a", { class: "line-img", href: `/p/${l.slug}` }, l.image ? el("img", { src: `/media/${l.image}/400.webp`, alt: "", loading: "lazy" }) : el("span", { class: "ph" })),
          el("div", { class: "line-info" }, el("b", { text: l.name }), el("span", { class: "muted small", text: detail }),
            s && s.preorder ? el("span", { class: "small", text: t("badge.preorder") }) : null,
            editable ? el("div", { class: "line-actions" },
              el("span", { class: "qty" },
                el("button", { type: "button", "aria-label": "−", onclick: () => change(i, (ls, j) => { ls[j].qty -= 1 }) }, ico("minus")),
                el("span", { text: l.qty }),
                el("button", { type: "button", "aria-label": "+", onclick: () => change(i, (ls, j) => { ls[j].qty = Math.min(20, ls[j].qty + 1) }) }, ico("plus"))),
              el("button", { class: "link-btn", type: "button", text: t("cart.remove"), onclick: () => change(i, (ls, j) => { ls[j].qty = 0 }) })) : (l.qty > 1 ? el("span", { class: "small", text: `× ${l.qty}` }) : null)),
          el("span", { class: "line-price" }, s ? [s.regular !== s.price ? el("s", { text: rp(s.regular * s.qty) }) : null, rp(s.line_total)] : "—"))
      }))
  })
}

async function refreshCart() {
  badge()
  const linesBox = $("[data-cart-lines]") || $("[data-co-lines]")
  if (!linesBox) return
  const editable = !!$("[data-cart-lines]")
  const summary = $("[data-cart-summary]")
  const empty = $("[data-cart-empty]")
  if (!cart.lines().length) {
    if (editable) { linesBox.replaceChildren(); summary.hidden = true; empty.hidden = false }
    else location.replace("/cart")
    return null
  }
  let q
  try { q = await quote() } catch (e) { linesBox.replaceChildren(el("p", { class: "form-msg", text: e.message })); return null }
  const problems = q.errors.length ? el("div", { class: "problems" }, el("b", { text: t("cart.problems") }), el("ul", {}, q.errors.map((x) => el("li", { text: x })))) : null
  linesBox.replaceChildren(...[problems, ...lineEls(q, { editable })].filter(Boolean))
  if (summary) summary.hidden = false
  for (const box of $$("[data-totals]")) renderTotals(box, q)
  for (const f of $$("[data-voucher]")) { const inp = $("input", f); if (document.activeElement !== inp) inp.value = voucher }
  for (const m of $$("[data-voucher-msg]")) { m.textContent = q.voucher_error || ""; m.style.color = "" }
  if (q.voucher && !q.voucher_error) for (const m of $$("[data-voucher-msg]")) { m.textContent = `✓ ${q.voucher.code}`; m.style.color = "var(--ok)" }
  const go = $("[data-go-checkout]")
  if (go) go.classList.toggle("loading", q.errors.length > 0 && !q.lines.length)
  return q
}

function voucherForms() {
  for (const f of $$("[data-voucher]")) f.addEventListener("submit", (e) => {
    e.preventDefault()
    voucher = $("input", f).value.trim().toUpperCase()
    store.set("cs_voucher", voucher)
    refreshCart()
  })
}

function checkoutPage() {
  ev("checkout_view")
  const form = $("[data-checkout]")
  const msg = $("[data-co-msg]")
  const btn = $("[data-co-submit]")
  const saved = store.get("cs_contact", {})
  for (const k of ["name", "phone", "email", "street", "city", "province", "postal"]) {
    const inp = form.elements[k]
    if (inp && !inp.value && saved[k]) inp.value = saved[k]
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault()
    msg.textContent = ""
    const f = form.elements
    const need = ["name", "phone", "street", "city"].filter((k) => !f[k].value.trim())
    for (const k of ["name", "phone", "street", "city"]) f[k].setAttribute("aria-invalid", need.includes(k) ? "true" : "false")
    if (need.length) { msg.textContent = `${t("co.required")}: ${need.map((k) => f[k].closest("label").querySelector("span").textContent).join(", ")}`; f[need[0]].focus(); return }
    const body = {
      lines: cart.lines().map(({ product, cut, size, color, qty, role, member, set_key }) => ({ product, cut, size, color, qty, role, member, set_key })),
      name: f.name.value.trim(), phone: f.phone.value.trim(), email: f.email.value.trim(),
      address: { street: f.street.value.trim(), city: f.city.value.trim(), province: f.province.value.trim(), postal: f.postal.value.trim() },
      note: f.note.value.trim(), voucher, save: f.save ? f.save.checked : false, website: f.website.value,
    }
    store.set("cs_contact", { name: body.name, phone: body.phone, email: body.email, ...body.address })
    btn.disabled = true
    btn.classList.add("loading")
    try {
      const res = await api("/api/orders", { method: "POST", json: body })
      const orders = store.get("cs_orders", [])
      store.set("cs_orders", [{ number: res.number, token: res.token, at: Date.now() }, ...orders].slice(0, 30))
      cart.save([])
      store.set("cs_voucher", "")
      location.href = res.url
    } catch (err) {
      msg.textContent = (err.data && err.data.errors && err.data.errors.join(" ")) || err.message
      if (err.status === 409) refreshCart()
      btn.disabled = false
      btn.classList.remove("loading")
    }
  })
}

// ---------------------------------------------------------------------------
// Other pages
// ---------------------------------------------------------------------------
async function wishlistPage() {
  const grid = $("[data-wish-grid]")
  await wish.sync()
  const n = await fillGrid(grid, wish.ids()).catch(() => 0)
  $("[data-wish-empty]").hidden = n > 0
  const recent = store.get("cs_recent", [])
  if (recent.length) {
    const m = await fillGrid($("[data-recent-grid]"), recent.slice(0, 8)).catch(() => 0)
    $("[data-recent]").hidden = !m
  }
}

async function homeRecs() {
  const box = $("[data-recs]")
  const recent = store.get("cs_recent", [])
  if (!box || !recent.length) return
  const n = await fillGrid($("[data-recs-grid]", box), recent.slice(0, 6), "/api/recs").catch(() => 0)
  box.hidden = !n
}

function familyForms() {
  const data = JSON.parse($("#family-data").textContent)
  const roles = Object.fromEntries(data.roles.map((r) => [r.id, r]))
  for (const f of $$("[data-member-form]")) {
    const role = $("[data-role]", f), cut = $("[data-cut]", f), size = $("[data-size]", f)
    const sync = () => {
      for (const g of $$("optgroup", size)) { g.hidden = g.dataset.for !== cut.value; g.disabled = g.dataset.for !== cut.value }
      const opt = size.selectedOptions[0]
      if (opt && opt.parentElement.tagName === "OPTGROUP" && opt.parentElement.dataset.for !== cut.value) size.value = ""
    }
    role.addEventListener("change", () => { const r = roles[role.value]; if (r && !r.cuts.includes(cut.value)) cut.value = r.cuts[0]; sync() })
    cut.addEventListener("change", sync)
    if (!f.querySelector("[name=member_id]") && roles[role.value]) cut.value = cut.value || roles[role.value].cuts[0]
    sync()
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
wireDialogs()
paintSwatches()
countdowns()
paintWish()
badge()
wish.sync()
const page = document.body.dataset.page
if (page === "product") productPage()
else if (page === "cart") { voucherForms(); refreshCart() }
else if (page === "checkout") { voucherForms(); refreshCart(); checkoutPage() }
else if (page === "wishlist") wishlistPage()
else if (page === "home") homeRecs()
else if (page === "family") familyForms()

if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("/sw.js").catch(() => {})
window.addEventListener("appinstalled", () => ev("install"))
