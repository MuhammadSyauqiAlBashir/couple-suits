import { api, armed, busy, copyText, el, fmtDate, icon, rp, statusPill, thumb, toast, CUTS, mediaUrl } from "./lib.js?v=__VERSION__"
import { go, refreshBadges } from "./app.js?v=__VERSION__"

export async function renderCustomers(page) {
  let search = ""
  const list = el("div", { class: "card list" })
  const input = el("input", { type: "search", placeholder: "Search name, email, phone…" })
  let timer
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { search = input.value; load() }, 300) }
  const count = el("p", { class: "muted small" })
  page.append(el("h1", { text: "Customers" }), el("div", { class: "search", style: { marginBottom: "12px" } }, icon("search"), input), count, list,
    el("p", { class: "muted small", text: "Guests who order without an account appear only in Orders." }))
  async function load() {
    const d = await api(`/customers?search=${encodeURIComponent(search)}`)
    count.textContent = `${d.total} account${d.total === 1 ? "" : "s"}`
    list.replaceChildren(...d.customers.map((c) => el("a", { class: "list-item", href: `#customer/${c.id}` },
      el("span", { class: "li-main" }, el("b", { text: c.name || c.email }), el("small", { text: `${c.email}${c.phone ? " · +" + c.phone : ""}` })),
      el("span", { class: "li-side" }, el("small", { class: "muted", text: `since ${fmtDate(c.created)}` }), c.marketing_ok ? el("span", { class: "pill ok", text: "offers ok" }) : null))))
    if (!d.customers.length) list.replaceChildren(el("p", { class: "muted small", style: { padding: "12px 16px" }, text: "No accounts yet." }))
  }
  await load()
}

export async function renderCustomer(page, id) {
  const d = await api(`/customers/${id}`)
  const c = d.customer
  const reset = el("button", { class: "btn small", type: "button", text: "Set a new password" })
  const out = el("div")
  reset.onclick = () => busy(reset, async () => {
    const r = await api(`/customers/${id}/password`, { method: "POST" })
    out.replaceChildren(el("div", { class: "ai-box", style: { marginTop: "10px" } }, el("p", {}, "New password: ", el("b", { text: r.password })),
      el("p", { class: "small muted", text: "Shown only now. Send it on WhatsApp and ask them to change it under Account." }),
      el("div", { class: "row gap" }, el("button", { class: "btn small", type: "button", onclick: () => copyText(r.password) }, icon("copy"), "Copy"),
        c.phone ? el("a", { class: "btn small wa", href: `https://wa.me/${c.phone}?text=${encodeURIComponent(`Halo ${c.name || ""}, kata sandi baru akun kamu: ${r.password}\nSilakan masuk lalu ganti di menu Akun.`)}`, target: "_blank", rel: "noopener" }, icon("wa"), "Send on WhatsApp") : null)))
  })
  const del = armed(el("button", { class: "btn small danger", type: "button", text: "Delete account (data request)" }), "Tap again to delete permanently", async () => {
    await api(`/customers/${id}`, { method: "DELETE" }); toast("Account deleted"); go("customers")
  })
  page.append(el("a", { class: "back", href: "#customers" }, icon("back"), "Customers"),
    el("h1", { text: c.name || c.email }),
    el("div", { class: "card" }, el("p", {}, c.email, el("br"), c.phone ? `+${c.phone}` : el("span", { class: "muted", text: "no phone" })),
      el("p", { class: "small muted", text: [c.birthday && `Birthday ${c.birthday}`, c.anniversary && `Anniversary ${c.anniversary}`, c.marketing_ok ? "allows offers" : "no offers", c.lang === "en" ? "English" : "Indonesian"].filter(Boolean).join(" · ") }),
      el("div", { class: "row gap" }, d.wa ? el("a", { class: "btn small wa", href: d.wa, target: "_blank", rel: "noopener" }, icon("wa"), "WhatsApp") : null, reset), out),
    el("div", { class: "card" }, el("h2", { text: "Family sizes" }),
      d.family.length ? d.family.map((m) => el("div", { class: "rank" }, el("span", { text: `${m.name || m.role} · ${m.role}` }), el("b", { text: `${CUTS[m.cut] || m.cut} ${m.size || "—"}` }))) : el("p", { class: "muted small", text: "None saved." })),
    el("div", { class: "card list" }, el("h2", { style: { padding: "12px 16px 0" }, text: "Orders" }),
      d.orders.map((o) => el("a", { class: "list-item", href: `#order/${o.id}` }, el("span", { class: "li-main" }, el("b", { text: o.number }), el("small", { text: fmtDate(o.created) })), el("span", { class: "li-side" }, statusPill(o.status), el("small", { text: rp(o.total) })))),
      d.orders.length ? null : el("p", { class: "muted small", style: { padding: "0 16px 12px" }, text: "No orders yet." })),
    d.vouchers.length ? el("div", { class: "card" }, el("h2", { text: "Personal vouchers" }), d.vouchers.map((v) => el("div", { class: "rank" }, el("span", { text: `${v.code} · ${v.label_id || ""}` }), el("b", { text: v.ends ? `until ${v.ends.slice(0, 10)}` : "" })))) : null,
    d.wishlist.length ? el("div", { class: "card" }, el("h2", { text: "Wishlist" }), d.wishlist.map((p) => el("a", { class: "rank", href: `#product/${p.id}` }, el("span", { text: p.name_id })))) : null,
    el("div", { class: "card" }, el("h2", { text: "Privacy" }), el("p", { class: "small muted", text: "If the customer asks to delete their data (UU PDP), this removes the account, family sizes and wishlist. Orders stay for bookkeeping without the account link." }), del))
}

export async function renderReviews(page, filter = "pending") {
  let status = filter || "pending"
  const list = el("div")
  const chips = el("div", { class: "chips" }, [["pending", "Waiting"], ["approved", "Approved"], ["hidden", "Hidden"]].map(([k, l]) =>
    el("button", { class: `chip${k === status ? " on" : ""}`, type: "button", text: l, onclick: (e) => { status = k; for (const c of chips.children) c.classList.toggle("on", c === e.target); load() } })))
  page.append(el("h1", { text: "Reviews" }), chips, list)
  async function load() {
    const d = await api(`/reviews?status=${status}`)
    list.replaceChildren(...d.reviews.map((r) => {
      const reply = el("textarea", { class: "inline", rows: 2, value: r.reply || "", placeholder: "Public reply (optional)" })
      const act = (st) => async (e) => busy(e.currentTarget, async () => { await api(`/reviews/${r.id}`, { method: "PATCH", json: { status: st, reply: reply.value } }); toast(st === "approved" ? "Approved — now visible" : "Saved"); refreshBadges(); load() })
      const p = (r.expand || {}).product || {}
      return el("div", { class: "card" },
        el("div", { class: "row between" }, el("b", { text: `${"★".repeat(r.rating)}${"☆".repeat(5 - r.rating)}  ${r.name}` }), statusPill(r.status)),
        el("p", { class: "small muted", text: `${p.name_id || ""}${r.family ? " · " + r.family : ""} · ${fmtDate(r.created)}` }),
        r.text ? el("p", { text: r.text }) : null,
        r.photos && r.photos.length ? el("div", { class: "row gap" }, r.photos.map((k) => el("a", { href: mediaUrl(k, 1800), target: "_blank", rel: "noopener" }, thumb(k, "thumb big")))) : null,
        reply,
        el("div", { class: "row gap", style: { marginTop: "8px" } },
          r.status !== "approved" ? el("button", { class: "btn small primary", type: "button", text: "Approve", onclick: act("approved") }) : el("button", { class: "btn small", type: "button", text: "Save reply", onclick: act("approved") }),
          r.status !== "hidden" ? el("button", { class: "btn small", type: "button", text: "Hide", onclick: act("hidden") }) : null,
          armed(el("button", { class: "btn small danger", type: "button", text: "Delete" }), "Tap again", async () => { await api(`/reviews/${r.id}`, { method: "DELETE" }); refreshBadges(); load() })))
    }))
    if (!d.reviews.length) list.replaceChildren(el("div", { class: "empty-state" }, el("p", { text: status === "pending" ? "No reviews waiting. 🎉" : "Nothing here." })))
  }
  await load()
}
