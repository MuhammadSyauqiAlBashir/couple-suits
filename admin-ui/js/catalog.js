import { api, armed, busy, el, icon, sheet, thumb, toast, CUTS, sizesFor } from "./lib.js?v=__VERSION__"
import { manager } from "./crud.js?v=__VERSION__"

export async function renderCatalog(page) {
  const cats = el("div", { class: "card" }), colls = el("div", { class: "card" }), charts = el("div", { class: "card" })
  page.append(el("h1", { text: "Categories & sizes" }), cats, colls, charts)
  const common = [
    { key: "name", type: "bi", label: "Name" },
    { key: "description", type: "bi", label: "Description", rows: 2 },
    { key: "slug", label: "Link name", hint: "Leave empty to make one from the name." },
    { key: "image", type: "image", label: "Image" },
    { key: "sort", type: "number", label: "Order" },
    { key: "active", type: "check", label: "Shown in the shop" },
  ]
  await manager(cats, { name: "categories", title: "Categories", single: "category", defaults: { active: true }, fields: common,
    row: (c) => ({ title: c.name_id, sub: `/c/${c.slug}`, image: thumb(c.image), side: c.active ? null : el("span", { class: "pill", text: "hidden" }) }) })
  await manager(colls, { name: "collections", title: "Collections", single: "collection", defaults: { active: true },
    note: "Themed groups like “Lebaran 2027”. Add products to a collection from the product page.",
    fields: [...common, { key: "featured", type: "check", label: "Featured" }],
    row: (c) => ({ title: c.name_id, sub: `/collections/${c.slug}`, image: thumb(c.image), side: c.active ? null : el("span", { class: "pill", text: "hidden" }) }) })
  await chartsManager(charts)
}

async function chartsManager(box) {
  const list = el("div", { class: "card list" })
  const add = el("button", { class: "btn small primary", type: "button" }, icon("plus"), "New chart")
  add.onclick = () => editChart({ name: "", cut: "men", columns: [{ key: "chest", id: "Lingkar dada", en: "Chest" }, { key: "length", id: "Panjang", en: "Length" }], rows: [] })
  box.append(el("div", { class: "row between" }, el("h2", { style: { margin: 0 }, text: "Size charts" }), add),
    el("p", { class: "muted small", text: "Garment measurements in cm. The “Default …” chart of each cut is used when a product doesn't pick one. Check against a real sample!" }), list)
  async function load() {
    const d = await api("/c/charts")
    list.replaceChildren(...d.items.map((c) => el("button", { class: "list-item", type: "button", onclick: () => editChart(c) },
      el("span", { class: "li-main" }, el("b", { text: c.name }), el("small", { text: `${CUTS[c.cut]} · ${(c.columns || []).map((x) => x.en).join(", ")}` })), icon("chevron"))))
  }
  function editChart(c) {
    const s = sheet(c.id ? "Edit size chart" : "New size chart", { tall: true })
    let columns = (c.columns || []).map((x) => ({ ...x }))
    const rows = {}
    for (const r of c.rows || []) rows[r.size] = { height: r.height || "", values: { ...(r.values || {}) } }
    const name = el("input", { class: "inline", value: c.name })
    const cut = el("select", { class: "inline" }, Object.entries(CUTS).map(([k, l]) => el("option", { value: k, text: l })))
    cut.value = c.cut
    const notesId = el("textarea", { class: "inline", rows: 2, value: c.notes_id || "" })
    const notesEn = el("textarea", { class: "inline", rows: 2, value: c.notes_en || "" })
    const table = el("div", { class: "table-scroll" })
    const draw = () => {
      const kids = cut.value !== "men" && cut.value !== "women" && cut.value !== "unisex_adult"
      const head = el("tr", {}, el("th", { text: "Size" }), kids ? el("th", { text: "Height" }) : null,
        columns.map((col, i) => el("th", {}, el("input", { class: "wide", value: col.en, title: "Column name (EN)", oninput: (e) => { col.en = e.target.value; col.key = col.key || e.target.value.toLowerCase().replace(/\W+/g, "_") } }),
          el("br"), el("input", { class: "wide", value: col.id, title: "Column name (ID)", oninput: (e) => { col.id = e.target.value } }),
          el("button", { class: "link-btn small", type: "button", text: "remove", onclick: () => { columns.splice(i, 1); draw() } }))))
      const body = sizesFor(cut.value).map((size) => {
        const r = rows[size] = rows[size] || { height: "", values: {} }
        return el("tr", {}, el("th", { text: size }),
          kids ? el("td", {}, el("input", { class: "wide", value: r.height, oninput: (e) => { r.height = e.target.value } })) : null,
          columns.map((col) => el("td", {}, el("input", { value: r.values[col.key] || "", inputmode: "decimal", oninput: (e) => { r.values[col.key] = e.target.value } }))))
      })
      table.replaceChildren(el("table", { class: "stock-table chart-table" }, head, body))
    }
    cut.onchange = draw
    draw()
    const addCol = el("button", { class: "btn small", type: "button", onclick: () => { const n = columns.length + 1; columns.push({ key: `col${n}_${Date.now() % 1000}`, id: "Ukuran", en: "Measure" }); draw() } }, icon("plus"), "Add measurement")
    const save = el("button", { class: "btn primary", type: "button", text: "Save" })
    save.onclick = () => busy(save, async () => {
      const body = { name: name.value.trim() || `${CUTS[cut.value]} chart`, cut: cut.value, columns, notes_id: notesId.value, notes_en: notesEn.value,
        rows: sizesFor(cut.value).map((size) => ({ size, height: (rows[size] || {}).height || "", values: (rows[size] || {}).values || {} })) }
      try {
        if (c.id) await api(`/c/charts/${c.id}`, { method: "PATCH", json: body })
        else await api("/c/charts", { method: "POST", json: body })
        toast("Saved"); s.close(); load()
      } catch (e) { toast(e.message, "bad") }
    })
    const del = c.id ? armed(el("button", { class: "btn danger", type: "button", text: "Delete" }), "Tap again", async () => { await api(`/c/charts/${c.id}`, { method: "DELETE" }); s.close(); load() }) : el("span")
    s.body.append(el("div", { class: "form" },
      el("div", { class: "two" }, el("label", { class: "field" }, el("span", { text: "Name" }), name), el("label", { class: "field" }, el("span", { text: "Cut" }), cut)),
      table, addCol,
      el("label", { class: "field" }, el("span", { text: "Note (ID)" }), notesId), el("label", { class: "field" }, el("span", { text: "Note (EN)" }), notesEn)),
    el("div", { class: "row between", style: { marginTop: "16px" } }, del, save))
  }
  await load()
}
