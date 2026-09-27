import { api, armed, busy, el, form, icon, sheet, thumb, toast } from "./lib.js?v=__VERSION__"
import { manager } from "./crud.js?v=__VERSION__"
import { state } from "./app.js?v=__VERSION__"

const TABS = [["home", "Homepage"], ["pages", "Pages"], ["posts", "Journal"], ["lookbooks", "Lookbook"]]

export async function renderContent(page, tab = "home") {
  const body = el("div")
  const chips = el("div", { class: "chips" }, TABS.map(([k, l]) => el("a", { class: `chip${k === tab ? " on" : ""}`, href: `#content/${k}`, text: l })))
  page.append(el("div", { class: "page-head" }, el("h1", { text: "Content" }), el("a", { class: "btn small", href: state.shopUrl, target: "_blank", rel: "noopener" }, icon("eye"), "Preview shop")), chips, body)
  const card = el("div", { class: "card" })
  body.append(card)
  if (tab === "pages") {
    await manager(card, { name: "pages", title: "Pages", single: "page", defaults: { status: "draft", in_footer: true },
      note: "Help pages linked in the footer: how to order, FAQ, returns, privacy policy. Please review the privacy policy draft.",
      fields: [
        { key: "title", type: "bi", label: "Title" },
        { key: "body", type: "bimd", label: "Text", rows: 14, hint: "Markdown: ## heading, - bullet, **bold**, [link](https://…)" },
        { key: "slug", label: "Link name", hint: "/page/link-name" },
        { key: "status", type: "select", label: "Status", options: [["draft", "Draft"], ["live", "Live"]] },
        { key: "in_footer", type: "check", label: "Show in the footer" },
        { key: "sort", type: "number", label: "Order" },
      ],
      row: (p) => ({ title: p.title_id, sub: `/page/${p.slug}`, side: el("span", { class: `pill st-${p.status}`, text: p.status }) }) })
  } else if (tab === "posts") {
    await manager(card, { name: "posts", title: "Journal", single: "post", addLabel: "New post", defaults: { status: "draft" },
      note: "Stories and tips (good for Google). Posts with tags that match product tags show those products below.",
      fields: [
        { key: "title", type: "bi", label: "Title" },
        { key: "excerpt", type: "bi", label: "Short intro", rows: 2 },
        { key: "cover", type: "image", label: "Cover photo" },
        { key: "body", type: "bimd", label: "Text", rows: 16 },
        { key: "tags", type: "tags", label: "Tags" },
        { key: "slug", label: "Link name" },
        { key: "published_at", type: "datetime", label: "Publish date" },
        { key: "status", type: "select", label: "Status", options: [["draft", "Draft"], ["live", "Live"]] },
      ],
      row: (p) => ({ title: p.title_id, sub: (p.published_at || p.created || "").slice(0, 10), image: thumb(p.cover), side: el("span", { class: `pill st-${p.status}`, text: p.status }) }) })
  } else if (tab === "lookbooks") {
    const products = (await api("/products")).products
    await manager(card, { name: "lookbooks", title: "Lookbook", single: "lookbook", addLabel: "New lookbook", defaults: { status: "draft", blocks: [] },
      note: "Photo stories. Each photo can link the products in it.",
      fields: [
        { key: "title", type: "bi", label: "Title" },
        { key: "intro", type: "bi", label: "Intro", rows: 3 },
        { key: "cover", type: "image", label: "Cover photo" },
        { key: "slug", label: "Link name" },
        { key: "status", type: "select", label: "Status", options: [["draft", "Draft"], ["live", "Live"]] },
        { key: "sort", type: "number", label: "Order" },
      ],
      extra: (item) => blocksEditor(item.blocks || [], products),
      row: (l) => ({ title: l.title_id, sub: `${(l.blocks || []).length} photos`, image: thumb(l.cover), side: el("span", { class: `pill st-${l.status}`, text: l.status }) }) })
  } else {
    await homeEditor(card)
  }
}

function blocksEditor(initial, products) {
  const blocks = initial.map((b) => ({ ...b, products: [...(b.products || [])] }))
  const node = el("div", { class: "field", style: { marginTop: "14px" } })
  const draw = () => {
    node.replaceChildren(el("span", { text: "Photos" }), ...blocks.map((b, i) => {
      const f = form([{ key: "image", type: "image", label: "Photo" }, { key: "caption", type: "bi", label: "Caption", rows: 2 }], b)
      b._f = f
      const picks = el("div", {}, products.map((p) => {
        const box = el("input", { type: "checkbox", checked: b.products.includes(p.id), onchange: (e) => { if (e.target.checked) b.products.push(p.id); else b.products = b.products.filter((x) => x !== p.id) } })
        return el("label", { class: "check" }, box, el("span", { text: p.name_id }))
      }))
      return el("div", { class: "block-card" }, f.node, el("details", {}, el("summary", { text: `Products in this photo (${b.products.length})` }), picks),
        el("div", { class: "row gap", style: { marginTop: "8px" } },
          el("button", { class: "btn small", type: "button", onclick: () => { if (i > 0) { sync(); [blocks[i - 1], blocks[i]] = [blocks[i], blocks[i - 1]]; draw() } } }, icon("up")),
          el("button", { class: "btn small", type: "button", onclick: () => { sync(); if (i < blocks.length - 1) { [blocks[i + 1], blocks[i]] = [blocks[i], blocks[i + 1]]; draw() } } }, icon("down")),
          el("button", { class: "btn small danger", type: "button", onclick: () => { sync(); blocks.splice(i, 1); draw() } }, "Remove")))
    }), el("button", { class: "btn small", type: "button", onclick: () => { sync(); blocks.push({ image: "", caption_id: "", caption_en: "", products: [] }); draw() } }, icon("plus"), "Add photo"))
  }
  const sync = () => { for (const b of blocks) if (b._f) Object.assign(b, b._f.values()) }
  draw()
  return { node, values: () => { sync(); return { blocks: blocks.map(({ _f, ...b }) => b) } } }
}

// ---------------------------------------------------------------------------
// Homepage builder
// ---------------------------------------------------------------------------
const KINDS = {
  hero: "Big banner", sets: "Shop by set (couple / family / kids)", products: "Product row", collection: "Collection highlight",
  story: "Story (photo + text)", usp: "Why us (3 points)", categories: "Categories", lookbook: "Lookbook banner", reviews: "Family reviews",
}

async function homeEditor(card) {
  const [colls, cats, lbs] = await Promise.all([api("/c/collections"), api("/c/categories"), api("/c/lookbooks")])
  const list = el("div", { class: "card list" })
  const add = el("button", { class: "btn small primary", type: "button" }, icon("plus"), "Add section")
  add.onclick = () => {
    const s = sheet("Add a section")
    s.body.append(...Object.entries(KINDS).map(([k, l]) => el("button", { class: "list-item", type: "button", onclick: async () => {
      await api("/c/home", { method: "POST", json: { kind: k, data: {}, sort: items.length, active: true } }); s.close(); load()
    } }, el("span", { class: "li-main" }, el("b", { text: l })), icon("plus"))))
  }
  card.append(el("div", { class: "row between" }, el("h2", { style: { margin: 0 }, text: "Homepage sections" }), add),
    el("p", { class: "muted small", text: "Top to bottom, as on the homepage. Tap a section to edit its photo and text." }), list)
  let items = []
  const fieldsFor = (kind) => {
    const title = { key: "title", type: "bi", label: "Heading (optional)" }
    switch (kind) {
      case "hero": return [{ key: "image", type: "image", label: "Photo (wide)" }, { key: "eyebrow", type: "bi", label: "Small line above" }, { key: "title", type: "bi", label: "Headline" },
        { key: "text", type: "bi", label: "Text", rows: 2 }, { key: "cta", type: "bi", label: "Button text" }, { key: "link", label: "Button link", placeholder: "/shop" }]
      case "products": return [title, { key: "mode", type: "select", label: "Which products", options: [["featured", "Featured"], ["new", "Newest"], ["popular", "Best sellers"], ["sale", "On sale"], ["category", "A category"], ["collection", "A collection"]] },
        { key: "ref", type: "select", label: "Category / collection (if chosen above)", options: [["", "—"], ...cats.items.map((c) => [c.id, `Category: ${c.name_id}`]), ...colls.items.map((c) => [c.id, `Collection: ${c.name_id}`])] },
        { key: "limit", type: "number", label: "How many", min: 2, max: 16 }]
      case "collection": return [{ key: "collection", type: "select", label: "Collection", options: colls.items.map((c) => [c.id, c.name_id]).concat(colls.items.length ? [] : [["", "Create a collection first"]]) }]
      case "story": return [{ key: "image", type: "image", label: "Photo" }, title, { key: "text", type: "bimd", label: "Text", rows: 5 }, { key: "cta", type: "bi", label: "Link text" },
        { key: "link", label: "Link", placeholder: "/lookbook" }, { key: "align", type: "select", label: "Photo side", options: [["left", "Left"], ["right", "Right"]] }]
      case "lookbook": return [{ key: "lookbook", type: "select", label: "Lookbook", options: [["", "Newest"], ...lbs.items.map((l) => [l.id, l.title_id])] }]
      default: return [title]
    }
  }
  const summary = (s) => {
    const d = s.data || {}
    if (s.kind === "hero") return d.title_id || "Tagline from Settings"
    if (s.kind === "products") return `${d.mode || "featured"}${d.limit ? ` · ${d.limit}` : ""}`
    if (s.kind === "collection") return (colls.items.find((c) => c.id === d.collection) || {}).name_id || "choose a collection"
    if (s.kind === "story") return d.title_id || ""
    return d.title_id || ""
  }
  function edit(s) {
    const sh = sheet(KINDS[s.kind] || s.kind, { tall: true })
    const f = form(fieldsFor(s.kind), s.data || {})
    const active = form([{ key: "active", type: "check", label: "Shown on the homepage" }], s)
    const save = el("button", { class: "btn primary", type: "button", text: "Save" })
    save.onclick = () => busy(save, async () => { await api(`/c/home/${s.id}`, { method: "PATCH", json: { data: { ...(s.data || {}), ...f.values() }, active: active.values().active } }); toast("Saved"); sh.close(); load() })
    const del = armed(el("button", { class: "btn danger", type: "button", text: "Delete" }), "Tap again", async () => { await api(`/c/home/${s.id}`, { method: "DELETE" }); sh.close(); load() })
    sh.body.append(f.node, el("div", { style: { marginTop: "12px" } }, active.node), el("div", { class: "row between", style: { marginTop: "16px" } }, del, save))
  }
  async function move(i, dir) {
    const j = i + dir
    if (j < 0 || j >= items.length) return
    ;[items[i], items[j]] = [items[j], items[i]]
    await api("/c/home/order", { method: "POST", json: { ids: items.map((x) => x.id) } })
    draw()
  }
  function draw() {
    list.replaceChildren(...items.map((s, i) => el("div", { class: "section-row" },
      thumb((s.data || {}).image, "thumb"),
      el("span", { class: "li-main", onclick: () => edit(s) }, el("b", { text: KINDS[s.kind] || s.kind }), el("small", { text: summary(s) })),
      s.active ? null : el("span", { class: "pill", text: "hidden" }),
      el("button", { class: "icon-btn", type: "button", "aria-label": "Up", onclick: () => move(i, -1) }, icon("up")),
      el("button", { class: "icon-btn", type: "button", "aria-label": "Down", onclick: () => move(i, 1) }, icon("down")))))
    if (!items.length) list.replaceChildren(el("p", { class: "muted small", style: { padding: "12px 16px" }, text: "No sections: the shop shows a default layout. Add sections to design your own." }))
  }
  async function load() { items = (await api("/c/home")).items; draw() }
  await load()
}
