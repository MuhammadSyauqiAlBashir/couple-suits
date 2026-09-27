import { $, api, armed, busy, el, filePicker, form, icon, moneyInput, rp, statusPill, thumb, toast, uploadImage, mediaUrl, CUTS, sizesFor } from "./lib.js?v=__VERSION__"
import { go, state } from "./app.js?v=__VERSION__"

export async function renderProducts(page) {
  const d = await api("/products")
  let filter = "", search = ""
  const grid = el("div", { class: "prod-grid" })
  const draw = () => {
    const items = d.products.filter((p) => (!filter || p.status === filter) && (!search || p.name_id.toLowerCase().includes(search) || (p.name_en || "").toLowerCase().includes(search)))
    grid.replaceChildren(...items.map((p) => el("a", { class: "prod-card", href: `#product/${p.id}` }, thumb((p.media || [])[0], "", 400),
      el("div", {}, el("b", { text: p.name_id }),
        el("small", { text: p.price_min === p.price_max ? rp(p.price_min) : `${rp(p.price_min)} – ${rp(p.price_max)}` }),
        el("span", { class: "row gap" }, statusPill(p.status), p.stock_mode === "preorder" ? el("span", { class: "pill info", text: "pre-order" }) : el("span", { class: `pill${p.stock ? "" : " bad"}`, text: `${p.stock} in stock` }),
          p.demo ? el("span", { class: "pill", text: "demo" }) : null)))))
    if (!items.length) grid.replaceChildren(el("div", { class: "empty-state" }, el("p", { text: "No products yet." })))
  }
  const input = el("input", { type: "search", placeholder: "Search products…" })
  input.oninput = () => { search = input.value.trim().toLowerCase(); draw() }
  const chips = el("div", { class: "chips" }, [["", "All"], ["live", "Live"], ["draft", "Draft"], ["archived", "Archived"]].map(([k, l]) =>
    el("button", { class: `chip${k === filter ? " on" : ""}`, type: "button", text: l, onclick: (e) => { filter = k; for (const c of chips.children) c.classList.toggle("on", c === e.target); draw() } })))
  const add = el("button", { class: "btn primary", type: "button" }, icon("plus"), "New product")
  add.onclick = () => busy(add, async () => { const r = await api("/products", { method: "POST", json: { name_id: "Produk baru" } }); go(`product/${r.product.id}`) })
  page.append(el("div", { class: "page-head" }, el("h1", { text: "Products" }), add),
    el("div", { class: "search", style: { marginBottom: "12px" } }, icon("search"), input), chips, grid)
  draw()
}

export async function renderProduct(page, id) {
  const [d, cats, colls, charts] = await Promise.all([api(`/products/${id}`), api("/c/categories"), api("/c/collections"), api("/c/charts")])
  const p = d.product
  let media = [...(p.media || [])]
  let colors = (p.colors || []).map((c) => ({ ...c }))
  const variants = {}
  for (const v of d.variants) variants[`${v.cut}|${v.size}|${v.color || ""}`] = v

  // --- photos -------------------------------------------------------------
  const photos = el("div", { class: "photos" })
  const drawPhotos = () => {
    photos.replaceChildren(...media.map((k, i) => el("div", { class: "photo" }, el("img", { src: mediaUrl(k, 400), alt: "" }),
      i === 0 ? el("span", { class: "first", text: "Cover" }) : null,
      el("div", { class: "tools" },
        el("button", { type: "button", "aria-label": "Move left", onclick: () => { if (i > 0) { [media[i - 1], media[i]] = [media[i], media[i - 1]]; drawPhotos() } } }, icon("back")),
        el("button", { type: "button", "aria-label": "Remove", onclick: () => { media.splice(i, 1); drawPhotos() } }, icon("trash")),
        el("button", { type: "button", "aria-label": "Move right", onclick: () => { if (i < media.length - 1) { [media[i + 1], media[i]] = [media[i], media[i + 1]]; drawPhotos() } } }, icon("chevron"))))),
    el("button", { class: "add-photo", type: "button", onclick: addPhotos }, el("span", {}, icon("plus"), el("br"), "Add photos")))
  }
  async function addPhotos(e) {
    const files = await filePicker({ multiple: true })
    const btn = e.currentTarget
    await busy(btn, async () => {
      for (const f of files) { try { const m = await uploadImage(f, "product"); media.push(m.key); drawPhotos() } catch (err) { toast(err.message, "bad") } }
    })
  }
  drawPhotos()

  // --- texts ---------------------------------------------------------------
  const texts = form([
    { key: "name", type: "bi", label: "Name" },
    { key: "summary", type: "bi", label: "Short summary", rows: 2, hint: "One sentence under the name and on cards." },
    { key: "description", type: "bimd", label: "Description", hint: "Markdown: - for bullet points, **bold**." },
    { key: "material", type: "bi", label: "Material", rows: 2 },
    { key: "care", type: "bi", label: "Care", rows: 2 },
  ], p)
  const aiNotes = el("textarea", { class: "inline", rows: 3, placeholder: "Notes for the AI: fabric, fit, occasion, what makes it special…" })
  const aiBtn = el("button", { class: "btn small primary", type: "button" }, icon("spark"), "Write texts with AI")
  aiBtn.onclick = () => busy(aiBtn, async () => {
    try {
      const r = await api("/ai/product-copy", { method: "POST", json: { notes: aiNotes.value, name: texts.values().name_id, cuts: selectedCuts(), image: media[0] || "" } })
      for (const k of ["name_id", "name_en", "summary_id", "summary_en", "description_id", "description_en", "material_id", "material_en", "care_id", "care_en"]) texts.set(k, r[k])
      meta.set("tags", r.tags); seo.set("seo_title", r.seo_title); seo.set("seo_description", r.seo_description)
      toast("Drafted — check and edit before publishing")
    } catch (e) { toast(e.message, "bad") }
  })

  // --- organisation --------------------------------------------------------
  const meta = form([
    { key: "category", type: "select", label: "Category", options: [["", "—"], ...cats.items.map((c) => [c.id, c.name_id])] },
    { key: "tags", type: "tags", label: "Tags", hint: "Used for search and “similar” suggestions." },
    { key: "featured", type: "check", label: "Featured on the homepage" },
    { key: "sort", type: "number", label: "Order (lower shows first)" },
  ], p)
  const collBoxes = colls.items.map((c) => { const b = el("input", { type: "checkbox", checked: (p.collections || []).includes(c.id) }); b.dataset.id = c.id; return el("label", { class: "check" }, b, el("span", { text: c.name_id })) })

  // --- cuts & prices --------------------------------------------------------
  const cutRows = {}
  const cutBox = el("div", {}, Object.entries(CUTS).map(([k, label]) => {
    const on = el("input", { type: "checkbox", checked: (p.cuts || []).includes(k) })
    const price = moneyInput((p.cut_prices || {})[k] || 0, { placeholder: "Price" })
    on.onchange = () => drawStock()
    cutRows[k] = { on, price }
    return el("div", { class: "cut-row" }, on, el("span", { text: label }), price)
  }))
  const selectedCuts = () => Object.keys(CUTS).filter((k) => cutRows[k].on.checked)

  // --- colours --------------------------------------------------------------
  const colorBox = el("div")
  const drawColors = () => {
    colorBox.replaceChildren(...colors.map((c, i) => {
      const hex = el("input", { type: "color", value: c.hex || "#cccccc", oninput: (e) => { c.hex = e.target.value } })
      const nid = el("input", { value: c.name_id || "", placeholder: "Nama (ID)", oninput: (e) => { c.name_id = e.target.value; if (!c.fixed) c.key = slug(e.target.value) } })
      const nen = el("input", { value: c.name_en || "", placeholder: "Name (EN)", oninput: (e) => { c.name_en = e.target.value } })
      return el("div", { class: "color-row" }, hex, nid, nen, el("button", { class: "icon-btn", type: "button", "aria-label": "Remove", onclick: () => { colors.splice(i, 1); drawColors(); drawStock() } }, icon("x")))
    }), el("button", { class: "btn small", type: "button", onclick: () => { colors.push({ key: "", name_id: "", name_en: "", hex: "#cccccc" }); drawColors() } }, icon("plus"), "Add colour"),
    el("p", { class: "hint", text: "Leave empty if the product comes in one colour. After adding colours, update the stock grid." }))
  }
  for (const c of colors) c.fixed = true
  drawColors()

  // --- sizes & stock -------------------------------------------------------
  const mode = form([
    { key: "stock_mode", type: "select", label: "Stock", options: [["ready", "Ready stock (count pieces)"], ["preorder", "Pre-order (made to order)"]] },
    { key: "preorder_days", type: "number", label: "Pre-order: days to make", min: 0, max: 120 },
  ], p)
  const stockBox = el("div")
  const cells = {}
  function drawStock() {
    const preorder = mode.values().stock_mode === "preorder"
    const cols = colors.length ? colors.map((c) => c.key || slug(c.name_id)) : [""]
    const tables = selectedCuts().map((cut) => {
      const head = el("tr", {}, el("th", { text: CUTS[cut] }), cols.map((c, i) => el("th", { text: colors[i] ? colors[i].name_id || c : (preorder ? "Offered" : "Stock") })))
      const rows = sizesFor(cut).map((size) => el("tr", {}, el("td", { text: size }), cols.map((color) => {
        const key = `${cut}|${size}|${color}`
        const v = variants[key]
        let input
        if (preorder) input = el("input", { type: "checkbox", checked: v ? v.active !== false : true })
        else { input = el("input", { type: "number", min: 0, value: v ? v.stock : 0, inputmode: "numeric" }); input.classList.toggle("zero", !Number(input.value)); input.oninput = () => input.classList.toggle("zero", !Number(input.value)) }
        cells[key] = input
        return el("td", {}, input)
      })))
      return el("div", { class: "table-scroll", style: { marginBottom: "14px" } }, el("table", { class: "stock-table" }, head, rows))
    })
    const fill = el("input", { type: "number", min: 0, value: 5, class: "inline", style: { width: "80px" } })
    stockBox.replaceChildren(...(tables.length ? tables : [el("p", { class: "muted", text: "Choose the cuts above first." })]),
      !preorder && tables.length ? el("div", { class: "row gap" }, el("span", { class: "small", text: "Set every size to" }), fill,
        el("button", { class: "btn small", type: "button", text: "Apply", onclick: () => { for (const [, i] of Object.entries(cells)) if (i.type === "number" && document.contains(i)) { i.value = fill.value; i.classList.toggle("zero", !Number(fill.value)) } } })) : null)
  }
  mode.node.addEventListener("change", drawStock)
  drawStock()

  // --- promotion, charts, SEO -------------------------------------------------
  const promo = form([
    { key: "sale_percent", type: "number", label: "Sale % off (0 = no sale)", min: 0, max: 90 },
    { key: "sale_start", type: "datetime", label: "Sale starts (optional)" },
    { key: "sale_end", type: "datetime", label: "Sale ends (shows a countdown)" },
  ], p)
  const chartBoxes = charts.items.map((c) => { const b = el("input", { type: "checkbox", checked: (p.size_charts || []).includes(c.id) }); b.dataset.id = c.id; return el("label", { class: "check" }, b, el("span", { text: `${c.name} (${CUTS[c.cut] || c.cut})` })) })
  const seo = form([
    { key: "slug", label: "Link name", hint: "shop address: /p/link-name" },
    { key: "seo_title", label: "Search title (optional)", max: 200 },
    { key: "seo_description", type: "textarea", label: "Search description (optional)", rows: 2 },
  ], p)

  const status = el("select", { class: "inline", style: { width: "auto" } }, [["draft", "Draft (hidden)"], ["live", "Live in the shop"], ["archived", "Archived"]].map(([v, l]) => el("option", { value: v, text: l })))
  status.value = p.status

  async function save(btn) {
    const cuts = selectedCuts()
    const cut_prices = Object.fromEntries(cuts.map((k) => [k, cutRows[k].price.money()]))
    const cleanColors = colors.filter((c) => c.name_id || c.name_en).map((c) => ({ key: c.key || slug(c.name_id || c.name_en), name_id: c.name_id, name_en: c.name_en, hex: c.hex, media: c.media || [] }))
    const m = mode.values()
    const body = {
      ...texts.values(), ...meta.values(), ...promo.values(), ...seo.values(), ...m, cuts, cut_prices, colors: cleanColors, media,
      collections: collBoxes.map((l) => $("input", l)).filter((b) => b.checked).map((b) => b.dataset.id),
      size_charts: chartBoxes.map((l) => $("input", l)).filter((b) => b.checked).map((b) => b.dataset.id),
    }
    const preorder = m.stock_mode === "preorder"
    const vs = []
    const colorKeys = cleanColors.length ? cleanColors.map((c) => c.key) : [""]
    for (const cut of cuts) for (const size of sizesFor(cut)) for (const color of colorKeys) {
      const input = cells[`${cut}|${size}|${color}`]
      if (!input) continue
      if (preorder) { if (input.checked) vs.push({ cut, size, color, stock: 0, active: true }) }
      else vs.push({ cut, size, color, stock: Math.max(0, Number(input.value) || 0), active: true })
    }
    await busy(btn, async () => {
      try {
        await api(`/products/${p.id}`, { method: "PATCH", json: { ...body, status: p.status === "live" && status.value === "live" ? "live" : "draft" } })
        const r = await api(`/products/${p.id}/variants`, { method: "PUT", json: { variants: vs } })
        for (const k of Object.keys(variants)) delete variants[k]
        for (const v of r.variants) variants[`${v.cut}|${v.size}|${v.color || ""}`] = v
        if (status.value !== "draft") await api(`/products/${p.id}`, { method: "PATCH", json: { status: status.value } })
        p.status = status.value
        for (const c of colors) c.fixed = true
        toast(status.value === "live" ? "Saved — live in the shop" : "Saved")
      } catch (e) { toast(e.message, "bad") }
    })
  }
  const saveBtn = el("button", { class: "btn primary", type: "button", text: "Save" })
  saveBtn.onclick = () => save(saveBtn)
  const dup = el("button", { class: "btn small", type: "button" }, icon("copy"), "Duplicate")
  dup.onclick = () => busy(dup, async () => { const r = await api(`/products/${p.id}/duplicate`, { method: "POST" }); go(`product/${r.product.id}`) })
  const del = armed(el("button", { class: "btn small danger", type: "button" }, "Delete"), "Tap again to delete", async () => {
    const r = await api(`/products/${p.id}`, { method: "DELETE" })
    toast(r.archived ? "Archived (it has orders)" : "Deleted"); go("products")
  })

  page.append(
    el("a", { class: "back", href: "#products" }, icon("back"), "Products"),
    el("div", { class: "page-head" }, el("h1", { text: p.name_id || "Product" }), el("div", { class: "row gap" }, status,
      el("a", { class: "btn small", href: `${state.shopUrl}/p/${p.slug}`, target: "_blank", rel: "noopener" }, icon("eye"), "View"))),
    p.demo ? el("p", { class: "ai-box small", text: "Demo product with AI-generated photos. Replace it with real products before launch (Settings → Remove demo catalog)." }) : null,
    el("div", { class: "card" }, el("h2", { text: "Photos" }), el("p", { class: "muted small", text: "First photo is the cover. Portrait 3:4 looks best. Photos are compressed automatically." }), photos),
    el("div", { class: "card ai-box" }, el("h2", {}, icon("spark"), "AI copywriter"), el("p", { class: "small muted", text: "Uses the cover photo and your notes to draft names and descriptions in both languages." }), aiNotes, el("div", { style: { marginTop: "8px" } }, aiBtn)),
    el("div", { class: "card" }, el("h2", { text: "Texts" }), texts.node),
    el("div", { class: "card" }, el("h2", { text: "Cuts & prices" }), el("p", { class: "muted small", text: "Which versions exist. Customers build a family set from these; each person picks a cut and size." }), cutBox),
    el("div", { class: "card" }, el("h2", { text: "Colours" }), colorBox),
    el("div", { class: "card" }, el("h2", { text: "Sizes & stock" }), mode.node, el("div", { style: { marginTop: "14px" } }, stockBox)),
    el("div", { class: "card" }, el("h2", { text: "Organise" }), meta.node, collBoxes.length ? el("div", { class: "field", style: { marginTop: "12px" } }, el("span", { text: "Collections" }), collBoxes) : null),
    el("div", { class: "card" }, el("h2", { text: "Sale" }), promo.node),
    el("div", { class: "card" }, el("h2", { text: "Size charts" }), el("p", { class: "muted small", text: "Optional. Without a choice, the default chart for each cut is shown." }), chartBoxes),
    el("div", { class: "card" }, el("h2", { text: "Search engines" }), seo.node),
    el("div", { class: "row gap", style: { marginBottom: "12px" } }, dup, del),
    el("div", { class: "sticky-save" }, saveBtn))
}

function slug(s) {
  return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40)
}
