// A list + edit sheet for simple collections (categories, vouchers, pages…).
import { api, armed, busy, el, form, icon, sheet, toast } from "./lib.js?v=__VERSION__"

/**
 * manager(container, { name, title, fields, row(item) → {title, sub, side, image}, defaults, addLabel, note, extra(item, f) })
 */
export async function manager(container, opts) {
  const list = el("div", { class: "card list" })
  const add = el("button", { class: "btn small primary", type: "button" }, icon("plus"), opts.addLabel || "Add")
  add.onclick = () => edit({ ...(opts.defaults || {}) })
  container.append(el("div", { class: "row between", style: { margin: "6px 0 10px" } }, el("h2", { style: { margin: 0 }, text: opts.title }), add),
    opts.note ? el("p", { class: "muted small", text: opts.note }) : null, list)

  async function load() {
    const d = await api(`/c/${opts.name}`)
    list.replaceChildren(...d.items.map((it) => {
      const r = opts.row(it)
      return el("button", { class: "list-item", type: "button", onclick: () => edit(it) }, r.image || null,
        el("span", { class: "li-main" }, el("b", { text: r.title || "—" }), r.sub ? el("small", { text: r.sub }) : null),
        el("span", { class: "li-side" }, r.side || null, icon("chevron")))
    }))
    if (!d.items.length) list.replaceChildren(el("p", { class: "muted small", style: { padding: "12px 16px" }, text: "Nothing yet." }))
  }

  function edit(item) {
    const s = sheet(item.id ? `Edit ${opts.single || ""}`.trim() : `New ${opts.single || ""}`.trim(), { tall: true })
    const f = form(opts.fields, item)
    const extra = opts.extra ? opts.extra(item, f) : null
    const save = el("button", { class: "btn primary", type: "button", text: "Save" })
    save.onclick = () => busy(save, async () => {
      try {
        const body = { ...f.values(), ...(extra && extra.values ? extra.values() : {}) }
        if (item.id) await api(`/c/${opts.name}/${item.id}`, { method: "PATCH", json: body })
        else await api(`/c/${opts.name}`, { method: "POST", json: body })
        toast("Saved"); s.close(); load()
      } catch (e) { toast(e.message, "bad") }
    })
    const del = item.id ? armed(el("button", { class: "btn danger", type: "button", text: "Delete" }), "Tap again", async () => {
      try { await api(`/c/${opts.name}/${item.id}`, { method: "DELETE" }); toast("Deleted"); s.close(); load() } catch (e) { toast(e.message, "bad") }
    }) : null
    s.body.append(f.node, extra ? extra.node : null, el("div", { class: "row between", style: { marginTop: "16px" } }, del || el("span"), save))
  }
  await load()
  return { reload: load }
}
