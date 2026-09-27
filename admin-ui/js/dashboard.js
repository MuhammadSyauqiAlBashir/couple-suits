import { api, bars, el, fmtDate, greeting, icon, rp, rpShort, thumb, statusPill, fmtTime } from "./lib.js?v=__VERSION__"
import { state } from "./app.js?v=__VERSION__"

export async function renderDashboard(page) {
  let days = 30
  const body = el("div")
  const range = el("div", { class: "chips" }, [7, 30, 90].map((d) => el("button", { class: `chip${d === days ? " on" : ""}`, type: "button", text: `${d} days`,
    onclick: (e) => { days = d; for (const c of range.children) c.classList.toggle("on", c === e.target); load() } })))
  page.append(el("div", { class: "page-head" }, el("h1", { text: `${greeting()}, ${state.me.username}` })), range, body)

  async function load() {
    const [d, orders] = await Promise.all([api(`/dashboard?days=${days}`), api("/orders?status=open")])
    const t = d.totals
    const kpi = (label, value, sub, cls = "") => el("div", { class: `kpi ${cls}` }, el("small", { text: label }), el("b", { text: value }), sub ? el("small", { text: sub }) : null)
    const alerts = []
    if (d.counts.new_orders) alerts.push(el("a", { class: "list-item", href: "#orders" }, icon("bag"), el("span", { class: "li-main" }, el("b", { text: `${d.counts.new_orders} new order${d.counts.new_orders > 1 ? "s" : ""} to confirm` }), el("small", { text: "Message them on WhatsApp with the shipping cost" })), icon("chevron")))
    if (d.counts.pending_reviews) alerts.push(el("a", { class: "list-item", href: "#reviews" }, icon("star"), el("span", { class: "li-main" }, el("b", { text: `${d.counts.pending_reviews} review${d.counts.pending_reviews > 1 ? "s" : ""} waiting` }), el("small", { text: "Approve to show them in the shop" })), icon("chevron")))
    if (d.counts.low_stock) alerts.push(el("a", { class: "list-item", href: "#products" }, icon("alert"), el("span", { class: "li-main" }, el("b", { text: `${d.counts.low_stock} sizes almost sold out` }), el("small", { text: d.low_stock.slice(0, 3).map((v) => `${v.product} ${v.size}`).join(" · ") })), icon("chevron")))

    const funnelRow = (label, n, of) => el("div", { class: "funnel-row" }, el("span", { text: label }),
      el("span", { class: "funnel-bar" }, el("i", { style: { width: `${of ? Math.max(2, Math.min(100, (n / of) * 100)) : 0}%` } })), el("b", { text: n.toLocaleString("id-ID") }))
    const rankList = (items, empty) => items.length ? items.map((p) => el("a", { class: "rank", href: `#product/${p.id}` }, thumb(p.image), el("span", { text: p.name }), el("b", { text: p.count }))) : el("p", { class: "muted small", text: empty })
    const labels = d.days.map((x) => fmtDate(x))

    body.replaceChildren(
      alerts.length ? el("div", { class: "card list" }, alerts) : null,
      el("div", { class: "kpis" },
        kpi("Visitors", t.visitors.toLocaleString("id-ID"), `${days} days`),
        kpi("Orders", String(t.orders), `${t.conversion}% of visitors`),
        kpi("Order value", rp(t.revenue), t.orders ? `avg ${rp(t.revenue / t.orders)}` : ""),
        kpi("Open orders", String(d.counts.open_orders), d.counts.new_orders ? `${d.counts.new_orders} new` : "all handled", d.counts.new_orders ? "alert" : "")),
      el("div", { class: "dash-grid" },
        el("div", { class: "card" }, el("h2", { text: "Visitors per day" }), bars(d.visitors, { labels }), el("div", { class: "axis" }, el("span", { text: labels[0] }), el("span", { text: labels[labels.length - 1] }))),
        el("div", { class: "card" }, el("h2", { text: "Orders per day" }), bars(d.orders, { labels }), el("div", { class: "axis" }, el("span", { text: labels[0] }), el("span", { text: `Total ${rpShort(t.revenue)}` })))),
      el("div", { class: "dash-grid" },
        el("div", { class: "card" }, el("h2", { text: "From visit to order" }), el("div", { class: "funnel" },
          funnelRow("Visitors", t.visitors, t.visitors), funnelRow("Added to bag", t.add_to_cart, t.visitors),
          funnelRow("Checkout", t.checkout_view, t.visitors), funnelRow("Ordered", t.orders, t.visitors),
          funnelRow("WhatsApp taps", t.wa_click, t.visitors))),
        el("div", { class: "card list" }, el("h2", { style: { padding: "12px 16px 0" }, text: "Open orders" }),
          orders.orders.slice(0, 6).map((o) => el("a", { class: "list-item", href: `#order/${o.id}` },
            el("span", { class: "li-main" }, el("b", { text: `${o.number} · ${o.contact_name}` }), el("small", { text: `${fmtDate(o.created)} ${fmtTime(o.created)} · ${(o.address || {}).city || ""}` })),
            el("span", { class: "li-side" }, statusPill(o.status), el("small", { text: rp(o.total) })))),
          orders.orders.length ? null : el("p", { class: "muted small", style: { padding: "0 16px 12px" }, text: "No open orders." }))),
      el("div", { class: "dash-grid" },
        el("div", { class: "card" }, el("h2", { text: "Most viewed" }), rankList(d.top_viewed, "No product views yet.")),
        el("div", { class: "card" }, el("h2", { text: "Best sellers" }), rankList(d.top_sold, "No sales yet."))),
      el("div", { class: "dash-grid" },
        el("div", { class: "card" }, el("h2", { text: "Where visitors come from" }),
          d.sources.length ? d.sources.map(([s, n]) => el("div", { class: "rank" }, el("span", { text: s }), el("b", { text: n }))) : el("p", { class: "muted small", text: "No data yet." }),
          d.devices.length ? el("p", { class: "muted small", style: { marginTop: "10px" }, text: d.devices.map(([k, n]) => `${k}: ${n}`).join(" · ") }) : null),
        el("div", { class: "card" }, el("h2", { text: "What people search for" }),
          d.searches.length ? d.searches.map(([s, n]) => el("div", { class: "rank" }, el("span", { text: s }), el("b", { text: n }))) : el("p", { class: "muted small", text: "No searches yet." }))),
      el("p", { class: "muted small center", text: "Privacy-friendly stats: no cookies, no personal data. Updated every minute." }))
  }
  await load()
}
