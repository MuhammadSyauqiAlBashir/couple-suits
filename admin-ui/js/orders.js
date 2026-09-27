import { api, armed, busy, copyText, el, fmtDate, fmtTime, icon, moneyInput, rp, STATUS, statusPill, thumb, toast, CUTS } from "./lib.js?v=__VERSION__"
import { refreshBadges } from "./app.js?v=__VERSION__"

const FILTERS = [["open", "Open"], ["new", "New"], ["awaiting_payment", "Awaiting payment"], ["paid", "Paid"],
  ["in_production", "In production"], ["shipped", "Shipped"], ["completed", "Completed"], ["cancelled", "Cancelled"], ["", "All"]]

export async function renderOrders(page, filter = "open") {
  let status = filter || "open", search = "", pageNo = 1
  const list = el("div", { class: "card list" })
  const input = el("input", { type: "search", placeholder: "Search number, name, phone…" })
  let timer
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { search = input.value; pageNo = 1; load() }, 300) }
  const chips = el("div", { class: "chips" }, FILTERS.map(([k, label]) => el("button", { class: `chip${k === status ? " on" : ""}`, type: "button", text: label,
    onclick: (e) => { status = k; pageNo = 1; for (const c of chips.children) c.classList.toggle("on", c === e.target); load() } })))
  const more = el("div", { class: "center" })
  page.append(el("div", { class: "page-head" }, el("h1", { text: "Orders" })), el("div", { class: "search", style: { marginBottom: "12px" } }, icon("search"), input), chips, list, more)

  async function load() {
    const d = await api(`/orders?status=${status}&search=${encodeURIComponent(search)}&page=${pageNo}`)
    const rows = d.orders.map((o) => el("a", { class: "list-item", href: `#order/${o.id}` },
      el("span", { class: "li-main" }, el("b", { text: `${o.contact_name}` }),
        el("small", { text: `${o.number} · ${fmtDate(o.created)} ${fmtTime(o.created)} · ${(o.address || {}).city || ""}${o.has_preorder ? " · pre-order" : ""}` })),
      el("span", { class: "li-side" }, statusPill(o.status), el("small", { text: rp(o.total + (o.shipping_set ? o.shipping_cost : 0)) }))))
    if (pageNo === 1) list.replaceChildren(...rows)
    else list.append(...rows)
    if (!d.orders.length && pageNo === 1) list.replaceChildren(el("div", { class: "empty-state" }, el("p", { text: "No orders here." })))
    more.replaceChildren(d.page < d.pages ? el("button", { class: "btn small", text: "Load more", onclick: () => { pageNo++; load() } }) : "")
  }
  await load()
}

export async function renderOrder(page, id) {
  const d = await api(`/orders/${id}`)
  draw(page, d)
}

function draw(page, d) {
  const o = d.order
  const save = async (patch, btn) => {
    const run = async () => {
      try { const nd = await api(`/orders/${o.id}`, { method: "PATCH", json: patch }); page.replaceChildren(); draw(page, nd); toast("Saved"); refreshBadges() } catch (e) { toast(e.message, "bad") }
    }
    return btn ? busy(btn, run) : run()
  }
  const grand = o.total + (o.shipping_set ? o.shipping_cost : 0)
  const a = o.address || {}

  // Status buttons in the normal order of work
  const steps = el("div", { class: "status-steps" }, d.statuses.filter((s) => s.id !== "cancelled").map((s) =>
    el("button", { type: "button", class: s.id === o.status ? "on" : "", text: s.label, disabled: o.status === "cancelled",
      onclick: (e) => save({ status: s.id }, e.target) })))
  const cancel = o.status === "cancelled" ? null : armed(el("button", { class: "btn small danger", type: "button", text: "Cancel order" }), "Tap again to cancel (stock returns)", () => save({ status: "cancelled" }))

  // Items, grouped by family set
  const groups = []
  const byKey = {}
  for (const it of d.items) {
    const k = it.set_key || `single-${it.id}`
    if (!byKey[k]) { byKey[k] = []; groups.push(byKey[k]) }
    byKey[k].push(it)
  }
  const itemRow = (it) => el("div", { class: "line" }, thumb(it.image),
    el("div", { class: "li-main" }, el("b", { text: it.product_name }),
      el("small", { text: [it.role && `${it.role}${it.member_name ? ` (${it.member_name})` : ""}`, CUTS[it.cut] || it.cut, it.size, it.color].filter(Boolean).join(" · ") }),
      el("small", { text: `${it.qty} × ${rp(it.price)}${it.preorder ? ` · pre-order ${it.preorder_days || ""}d` : " · ready stock"}` })),
    el("b", { text: rp(it.line_total) }))

  const ship = moneyInput(o.shipping_cost || 0, { placeholder: "0" })
  const shipBtn = el("button", { class: "btn small primary", type: "button", text: o.shipping_set ? "Update" : "Set shipping" })
  shipBtn.onclick = () => save({ shipping_cost: ship.money() }, shipBtn)

  const courier = el("input", { class: "inline", value: o.shipping_courier || "", placeholder: "JNE / J&T / SiCepat…" })
  const tracking = el("input", { class: "inline", value: o.tracking_number || "", placeholder: "Tracking number" })
  const note = el("textarea", { class: "inline", rows: 3, value: o.admin_note || "", placeholder: "Private note (only admins see this)" })
  const saveMeta = el("button", { class: "btn small", type: "button", text: "Save" })
  saveMeta.onclick = () => save({ shipping_courier: courier.value, tracking_number: tracking.value, admin_note: note.value }, saveMeta)

  page.append(
    el("a", { class: "back", href: "#orders" }, icon("back"), "Orders"),
    el("div", { class: "page-head" }, el("div", {}, el("h1", { text: o.number }), el("p", { class: "muted small", text: `${fmtDate(o.created, { day: "numeric", month: "long", year: "numeric" })} ${fmtTime(o.created)} · ${o.lang === "en" ? "English" : "Bahasa Indonesia"}` })), statusPill(o.status)),
    el("div", { class: "card" }, el("h2", { text: "Status" }), steps, el("div", { class: "row between", style: { marginTop: "12px" } }, el("span", { class: "muted small", text: "The customer sees this on their order page." }), cancel)),
    el("div", { class: "card" }, el("h2", {}, icon("wa"), "Message the customer"),
      el("p", { class: "muted small", text: `+${o.phone} · opens WhatsApp with a ready message you can edit before sending.` }),
      el("div", { class: "wa-grid" }, d.wa.map((w) => el("a", { class: "wa-btn", href: w.url, target: "_blank", rel: "noopener" }, icon("wa"), el("span", {}, w.label, el("small", { text: w.text.slice(0, 70) + "…" }))))),
      el("div", { class: "row gap", style: { marginTop: "10px" } },
        el("button", { class: "link-btn", type: "button", onclick: () => copyText(d.link) }, icon("link"), "Copy order link"),
        el("a", { class: "link-btn", href: d.link, target: "_blank", rel: "noopener" }, icon("eye"), "View as customer"))),
    el("div", { class: "card order-items" }, el("h2", { text: `Items (${d.items.reduce((s, i) => s + i.qty, 0)})` }),
      groups.map((g) => g.length > 1 ? el("div", { class: "set-box" }, el("small", { class: "muted", text: `Family set · ${g.length} people` }), g.map(itemRow)) : itemRow(g[0])),
      el("dl", { class: "totals", style: { marginTop: "12px" } },
        el("dt", { text: "Items" }), el("dd", { text: rp(o.items_total) }),
        ...(o.discounts || []).flatMap((x) => [el("dt", { text: x.label }), el("dd", { text: "−" + rp(x.amount) })]),
        el("dt", { text: "Shipping" }), el("dd", { text: o.shipping_set ? rp(o.shipping_cost) : "not set yet" }),
        el("dt", { class: "grand", text: "Total to pay" }), el("dd", { class: "grand", text: rp(grand) }))),
    el("div", { class: "card" }, el("h2", {}, icon("truck"), "Shipping"),
      el("p", { class: "muted small", text: `${o.contact_name} · ${a.street || ""}, ${a.city || ""}${a.province ? ", " + a.province : ""} ${a.postal || ""}` }),
      el("div", { class: "row gap" }, el("label", { class: "field grow" }, el("span", { text: "Shipping cost" }), ship), shipBtn),
      el("div", { class: "two", style: { marginTop: "12px" } }, el("label", { class: "field" }, el("span", { text: "Courier" }), courier), el("label", { class: "field" }, el("span", { text: "Tracking number" }), tracking)),
      el("label", { class: "field", style: { marginTop: "12px" } }, el("span", { text: "Admin note" }), note),
      el("div", { class: "row", style: { justifyContent: "flex-end", marginTop: "8px" } }, saveMeta)),
    el("div", { class: "card" }, el("h2", { text: "Customer" }),
      el("p", {}, el("b", { text: o.contact_name }), el("br"), `+${o.phone}`, o.email ? [el("br"), o.email] : null),
      o.customer_note ? el("p", { class: "ai-box", text: `“${o.customer_note}”` }) : null,
      d.customer ? el("a", { class: "link-btn", href: `#customer/${d.customer.id}`, text: "Open customer account" }) : el("p", { class: "muted small", text: "Guest order (no account)." }),
      d.history.length ? el("div", { style: { marginTop: "10px" } }, el("small", { class: "muted", text: "Earlier orders from this number:" }),
        d.history.map((h) => el("a", { class: "rank", href: `#order/${h.id}` }, el("span", { text: `${h.number} · ${fmtDate(h.created)}` }), statusPill(h.status), el("b", { text: rp(h.total) })))) : null),
    el("div", { class: "card" }, el("h2", { text: "History" }), el("ul", { class: "timeline" },
      [...(o.timeline || [])].reverse().map((t) => el("li", {}, el("b", { text: t.status ? STATUS[t.status] || t.status : t.note }), ` · ${fmtDate(t.at)} ${fmtTime(t.at)} · ${t.by || ""}`)))))
}
