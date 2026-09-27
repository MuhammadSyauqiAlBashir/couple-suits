// AI design studio: sketches + detail crops → brief → options → flats → family → tech pack → product.
import { api, armed, busy, copyText, el, filePicker, fmtDate, icon, sheet, shrinkImage, toast, CUTS } from "./lib.js?v=__VERSION__"
import { go } from "./app.js?v=__VERSION__"

const ROLE_LIST = [["wife", "Wife"], ["husband", "Husband"], ["mom", "Mom"], ["dad", "Dad"], ["daughter", "Daughter"], ["son", "Son"],
  ["sister", "Sister"], ["brother", "Brother"], ["baby", "Baby"], ["grandma", "Grandma"], ["grandpa", "Grandpa"]]

export async function renderStudio(page) {
  const d = await api("/studio/designs")
  const add = el("button", { class: "btn primary", type: "button" }, icon("plus"), "New design")
  add.onclick = () => newDesign()
  page.append(el("div", { class: "page-head" }, el("h1", { text: "AI Studio" }), add),
    el("p", { class: "muted", text: "Turn hand sketches and detail photos into matching family designs, technical flats, a tech pack for the tailor, and a draft product." }),
    el("p", { class: "quota", text: `Images today: ${d.usage} of ~${d.free} free · ${d.flux ? "FLUX.2 connected" : "image AI not configured"} · ${d.gemini ? "Gemini connected" : "text AI not configured"}` }),
    d.designs.length ? el("div", { class: "prod-grid" }, d.designs.map((x) => el("a", { class: "prod-card", href: `#design/${x.id}` },
      x.cover ? el("img", { src: x.cover, alt: "", loading: "lazy" }) : el("span", { class: "ph" }),
      el("div", {}, el("b", { text: x.title }), el("small", { text: `${statusText(x.status)} · ${fmtDate(x.updated)}` })))))
      : el("div", { class: "card empty-state" }, el("h3", { text: "Start your first design" }), el("p", { text: "Upload a sketch (a phone photo is fine) and close-ups of details you like: collar, buttons, fabric." })))
}

const statusText = (s) => ({ draft: "Inputs", options: "Options", chosen: "Chosen", done: "Tech pack ready" }[s] || s)

function newDesign() {
  const s = sheet("New design")
  const title = el("input", { class: "inline", placeholder: "e.g. Lebaran ivory set" })
  const picked = new Set(["wife", "husband"])
  const chips = el("div", { class: "chips", style: { flexWrap: "wrap" } }, ROLE_LIST.map(([k, l]) => {
    const c = el("button", { class: `chip${picked.has(k) ? " on" : ""}`, type: "button", text: l })
    c.onclick = () => { picked.has(k) ? picked.delete(k) : picked.add(k); c.classList.toggle("on") }
    return c
  }))
  const notes = el("textarea", { class: "inline", rows: 3, placeholder: "Idea, occasion, fabric, colours…" })
  const create = el("button", { class: "btn primary wide", type: "button", text: "Create" })
  create.onclick = () => busy(create, async () => {
    const order = ROLE_LIST.map(([k]) => k).filter((k) => picked.has(k))
    const r = await api("/studio/designs", { method: "POST", json: { title: title.value.trim() || "Untitled design", roles: order, notes: notes.value } })
    s.close(); go(`design/${r.design.id}`)
  })
  s.body.append(el("div", { class: "form" }, el("label", { class: "field" }, el("span", { text: "Name" }), title),
    el("div", { class: "field" }, el("span", { text: "Who is it for? (first one is the main design)" }), chips),
    el("label", { class: "field" }, el("span", { text: "Notes" }), notes), create))
}

// ---------------------------------------------------------------------------
// One design
// ---------------------------------------------------------------------------
export async function renderDesign(page, id) {
  let data = await api(`/studio/designs/${id}`)
  const root = el("div")
  page.append(el("a", { class: "back", href: "#studio" }, icon("back"), "Studio"), root)
  const reload = async () => { data = await api(`/studio/designs/${id}`); draw() }

  function tile(a, { onclick, chosen } = {}) {
    return el("button", { class: `gen${chosen ? " on" : ""}`, type: "button", onclick: onclick || (() => viewAsset(a)) },
      el("img", { src: a.url, alt: a.label, loading: "lazy" }), a.favorite ? el("span", { class: "fav" }, icon("star")) : null,
      el("span", { class: "lbl", text: chosen ? `✓ ${a.label || a.kind}` : a.label || a.kind }))
  }
  function pendingTile(text = "Generating…") { return el("div", { class: "gen pending", text }) }

  function viewAsset(a) {
    const s = sheet(a.label || a.kind, { tall: true })
    const d = data.design
    const isChosen = (d.chosen || {}).asset === a.id
    s.body.append(el("img", { src: a.url, alt: "", style: { borderRadius: "10px", margin: "0 auto 12px", maxHeight: "60vh" } }),
      a.meta && a.meta.feedback ? el("p", { class: "small muted", text: `Change asked: ${a.meta.feedback}` }) : null,
      el("div", { class: "row gap" },
        a.kind === "option" ? el("button", { class: "btn primary", type: "button", disabled: isChosen, text: isChosen ? "Chosen" : "Choose this design",
          onclick: async (e) => busy(e.currentTarget, async () => { await api(`/studio/designs/${id}/choose`, { method: "POST", json: { asset: a.id } }); s.close(); await reload(); toast("Chosen — now make the flats") }) }) : null,
        el("button", { class: "btn", type: "button", onclick: async () => { await api(`/studio/assets/${a.id}`, { method: "PATCH", json: { favorite: !a.favorite } }); s.close(); reload() } }, icon("star"), a.favorite ? "Unfavourite" : "Favourite"),
        el("a", { class: "btn", href: a.url, download: `${a.label || a.kind}.jpg` }, "Download"),
        armed(el("button", { class: "btn danger", type: "button", text: "Delete" }), "Tap again", async () => { await api(`/studio/assets/${a.id}`, { method: "DELETE" }); s.close(); reload() })))
  }

  async function upload(kind, label = "") {
    const files = await filePicker({ multiple: kind === "sketch" })
    for (const f of files) {
      if (kind === "detail") return cropTool(f)
      const blob = await shrinkImage(f, 1600)
      const fd = new FormData()
      fd.append("file", blob, "input.jpg"); fd.append("kind", kind); fd.append("label", label)
      await api(`/studio/designs/${id}/inputs`, { method: "POST", body: fd })
    }
    reload()
  }

  // Detail crop: drag a box over the part you like (collar, button, fabric…)
  async function cropTool(file) {
    const blob = await shrinkImage(file, 1600)
    const url = URL.createObjectURL(blob)
    const img = await new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.src = url })
    const s = sheet("Crop the detail", { tall: true, onClose: () => URL.revokeObjectURL(url) })
    const canvas = el("canvas", { style: { width: "100%", touchAction: "none", borderRadius: "8px", background: "#000" } })
    const scale = Math.min(1, 900 / img.width)
    canvas.width = img.width * scale; canvas.height = img.height * scale
    const ctx = canvas.getContext("2d")
    let box = { x: canvas.width * 0.25, y: canvas.height * 0.25, w: canvas.width * 0.5, h: canvas.height * 0.5 }
    const paint = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      ctx.fillStyle = "rgba(0,0,0,.5)"
      ctx.fillRect(0, 0, canvas.width, box.y); ctx.fillRect(0, box.y + box.h, canvas.width, canvas.height - box.y - box.h)
      ctx.fillRect(0, box.y, box.x, box.h); ctx.fillRect(box.x + box.w, box.y, canvas.width - box.x - box.w, box.h)
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.strokeRect(box.x, box.y, box.w, box.h)
    }
    let start = null
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return { x: (e.clientX - r.left) * canvas.width / r.width, y: (e.clientY - r.top) * canvas.height / r.height } }
    canvas.addEventListener("pointerdown", (e) => { start = pos(e); canvas.setPointerCapture(e.pointerId) })
    canvas.addEventListener("pointermove", (e) => {
      if (!start) return
      const p = pos(e)
      box = { x: Math.min(start.x, p.x), y: Math.min(start.y, p.y), w: Math.abs(p.x - start.x), h: Math.abs(p.y - start.y) }
      paint()
    })
    canvas.addEventListener("pointerup", () => { start = null })
    paint()
    const label = el("input", { class: "inline", placeholder: "What is it? e.g. collar, buttons, fabric" })
    const use = el("button", { class: "btn primary", type: "button", text: "Use this crop" })
    use.onclick = () => busy(use, async () => {
      if (box.w < 20 || box.h < 20) { toast("Drag a bigger box", "bad"); return }
      const out = document.createElement("canvas")
      out.width = Math.round(box.w / scale); out.height = Math.round(box.h / scale)
      out.getContext("2d").drawImage(img, box.x / scale, box.y / scale, box.w / scale, box.h / scale, 0, 0, out.width, out.height)
      const cropped = await new Promise((r) => out.toBlob(r, "image/jpeg", 0.9))
      const fd = new FormData()
      fd.append("file", cropped, "detail.jpg"); fd.append("kind", "detail"); fd.append("label", label.value)
      await api(`/studio/designs/${id}/inputs`, { method: "POST", body: fd })
      s.close(); reload()
    })
    const whole = el("button", { class: "btn", type: "button", text: "Use whole photo", onclick: () => { box = { x: 0, y: 0, w: canvas.width, h: canvas.height }; paint() } })
    s.body.append(el("p", { class: "small muted", text: "Drag over the detail you want the design to use." }), canvas, el("div", { class: "form", style: { marginTop: "10px" } }, label, el("div", { class: "row gap" }, whole, use)))
  }

  let hq = false
  async function generateMany(kind, n, grid, extra = {}) {
    const pend = []
    for (let i = 0; i < n; i++) { const t = pendingTile(); pend.push(t); grid.prepend(t) }
    let ok = 0
    for (const t of pend) {
      try {
        const r = await api(`/studio/designs/${id}/generate`, { method: "POST", json: { kind, hq, ...extra } })
        t.replaceWith(tile(r.asset)); ok++
      } catch (e) { t.textContent = e.message.slice(0, 120); t.classList.remove("pending"); toast(e.message, "bad"); break }
    }
    if (ok) await reload()
  }

  function draw() {
    const d = data.design, assets = data.assets, brief = d.brief || {}, spec = d.spec || {}
    const of = (k) => assets.filter((a) => a.kind === k)
    const chosenId = (d.chosen || {}).asset
    const hasBrief = !!brief.garment_type
    const flats = of("flat")
    const front = [...flats].reverse().find((a) => a.meta.side === "front")
    const back = [...flats].reverse().find((a) => a.meta.side === "back")
    const roleImgs = of("role")
    const stepsDone = [of("sketch").length + of("detail").length > 0, hasBrief, of("option").length > 0, !!chosenId && !!front, roleImgs.length > 0, !!spec.name_id]
    const names = ["Inputs", "Brief", "Options", "Flats", "Family", "Tech pack"]
    const current = stepsDone.indexOf(false)

    const title = el("input", { class: "inline", value: d.title, style: { fontSize: "20px", fontWeight: "700" }, onchange: (e) => api(`/studio/designs/${id}`, { method: "PATCH", json: { title: e.target.value } }) })
    const inputsGrid = el("div", { class: "studio-grid" }, [...of("sketch"), ...of("detail")].map((a) => tile(a)))
    const notes = el("textarea", { class: "inline", rows: 2, value: d.notes || "", placeholder: "Notes: occasion, fabric, colours…", onchange: (e) => api(`/studio/designs/${id}`, { method: "PATCH", json: { notes: e.target.value } }) })

    // Brief
    const analyse = el("button", { class: "btn primary", type: "button" }, icon("spark"), hasBrief ? "Analyse again" : "Analyse with AI")
    analyse.onclick = () => busy(analyse, async () => { try { data = await api(`/studio/designs/${id}/analyze`, { method: "POST" }); draw(); toast("Brief ready") } catch (e) { toast(e.message, "bad") } })
    const promptBox = el("textarea", { class: "inline", rows: 4, value: brief.prompt_primary || "" })
    const flatBox = el("textarea", { class: "inline", rows: 3, value: brief.flat_description || "" })
    const savePrompt = el("button", { class: "btn small", type: "button", text: "Save prompts" })
    savePrompt.onclick = () => busy(savePrompt, async () => { await api(`/studio/designs/${id}`, { method: "PATCH", json: { brief: { ...brief, prompt_primary: promptBox.value, flat_description: flatBox.value } } }); toast("Saved") })
    const briefView = hasBrief ? el("div", {},
      el("p", { text: brief.summary_id }),
      el("dl", { class: "brief" },
        el("dt", { text: "Garment" }), el("dd", { text: `${brief.garment_type} — ${brief.silhouette}` }),
        el("dt", { text: "Details" }), el("dd", { text: (brief.details || []).join(" · ") }),
        el("dt", { text: "Fabric" }), el("dd", { text: brief.fabric }),
        el("dt", { text: "Colours" }), el("dd", {}, (brief.colors || []).map((c) => el("span", { class: "pill", style: { marginRight: "4px" } }, el("i", { style: { display: "inline-block", width: "10px", height: "10px", borderRadius: "50%", background: c.hex } }), c.name))),
        el("dt", { text: "Family" }), el("dd", {}, (brief.roles || []).map((r) => el("div", { text: `${r.role}: ${r.garment}` }))),
        (brief.questions || []).length ? [el("dt", { text: "Questions from the AI" }), el("dd", {}, (brief.questions || []).map((qq) => el("div", { text: `• ${qq}` })), el("small", { class: "muted", text: "Answer in the notes above, then Analyse again." }))] : null),
      el("details", {}, el("summary", { text: "Image prompts (advanced)" }), el("label", { class: "field" }, el("span", { text: "Main design" }), promptBox), el("label", { class: "field" }, el("span", { text: "Flat sketch" }), flatBox), savePrompt)) : null

    // Options
    const optGrid = el("div", { class: "studio-grid" }, [...of("option")].reverse().map((a) => tile(a, { chosen: a.id === chosenId })))
    const feedback = el("input", { class: "inline", placeholder: "Change something: rounder collar, shorter sleeves…" })
    const gen4 = el("button", { class: "btn primary", type: "button", disabled: !hasBrief }, icon("spark"), of("option").length ? "4 more" : "Generate 4 options")
    gen4.onclick = () => busy(gen4, () => generateMany("option", 4, optGrid))
    const gen2 = el("button", { class: "btn", type: "button", disabled: !hasBrief, text: "Apply change (2 new)" })
    gen2.onclick = () => { if (!feedback.value.trim()) return toast("Type the change first", "bad"); busy(gen2, () => generateMany("option", 2, optGrid, { feedback: feedback.value.trim() })) }
    const hqBox = el("label", { class: "check small" }, el("input", { type: "checkbox", checked: hq, onchange: (e) => { hq = e.target.checked } }), el("span", { text: "High quality (uses ~12× the free quota)" }))
    const gemini = el("button", { class: "link-btn small", type: "button", disabled: !hasBrief, text: "Use the Gemini app instead" })
    gemini.onclick = async () => {
      const r = await api(`/studio/designs/${id}/gemini-prompt`)
      const s = sheet("Gemini app (manual)")
      s.body.append(el("p", { class: "small", text: "1. Open the Gemini app, attach your sketch and detail photos. 2. Paste this prompt. 3. Save the result and upload it here as an option." }),
        el("textarea", { class: "inline", rows: 8, value: r.prompt }), el("div", { class: "row gap", style: { marginTop: "8px" } },
          el("button", { class: "btn", type: "button", onclick: () => copyText(r.prompt) }, icon("copy"), "Copy prompt"),
          el("button", { class: "btn primary", type: "button", onclick: async () => { s.close(); await upload("option", "Gemini") } }, "Upload result")))
    }

    // Flats
    const flatBtn = (side) => {
      const b = el("button", { class: "btn small", type: "button", disabled: !chosenId }, icon("pen"), side === "front" ? (front ? "Redo front" : "Front flat") : (back ? "Redo back" : "Back flat"))
      b.onclick = () => busy(b, async () => { try { await api(`/studio/designs/${id}/generate`, { method: "POST", json: { kind: `flat_${side}`, hq } }); await reload() } catch (e) { toast(e.message, "bad") } })
      return b
    }

    // Family
    const others = (d.roles || []).slice(1)
    const familyGrid = el("div", { class: "studio-grid" }, roleImgs.map((a) => tile(a)))
    const roleBtns = others.map((r) => {
      const b = el("button", { class: "btn small", type: "button", disabled: !front, text: data.roles[r] || r })
      b.onclick = () => busy(b, () => generateMany("role", 1, familyGrid, { role: r }))
      return b
    })
    const mock = el("button", { class: "btn small", type: "button", disabled: !roleImgs.length }, icon("users"), "Make family board")
    mock.onclick = () => busy(mock, async () => { try { await api(`/studio/designs/${id}/mockup`, { method: "POST" }); await reload() } catch (e) { toast(e.message, "bad") } })
    const mockImg = [...of("mockup")].reverse()[0]

    // Tech pack
    const tp = el("button", { class: "btn primary", type: "button", disabled: !chosenId }, icon("spark"), spec.name_id ? "Write again" : "Write tech pack & size charts")
    tp.onclick = () => busy(tp, async () => { try { data = await api(`/studio/designs/${id}/techpack`, { method: "POST" }); draw(); toast("Tech pack ready") } catch (e) { toast(e.message, "bad") } })
    const prod = el("button", { class: "btn primary", type: "button", disabled: !spec.name_id }, icon("box"), d.product ? "Create another product" : "Turn into product")
    prod.onclick = () => busy(prod, async () => { const r = await api(`/studio/designs/${id}/product`, { method: "POST" }); toast("Draft product created — add prices and publish"); go(`product/${r.product.id}`) })
    const specView = spec.name_id ? el("div", { class: "md" },
      el("h3", { text: `${spec.name_id} / ${spec.name_en}` }), el("p", { text: spec.summary_id }),
      el("h4", { text: "Fabric" }), el("ul", {}, (spec.fabrics || []).map((f) => el("li", { text: `${f.name} — ${f.weight}. ${f.notes || ""}` }))),
      el("h4", { text: "Trims" }), el("ul", {}, (spec.trims || []).map((t) => el("li", { text: `${t.item}: ${t.spec} (${t.qty})` }))),
      el("h4", { text: "Construction" }), el("ul", {}, (spec.construction || []).map((c) => el("li", { text: c }))),
      el("h4", { text: "Cuts" }), el("ul", {}, (spec.cuts || []).map((c) => el("li", { text: `${CUTS[c.cut] || c.cut}: ${c.garment} (${c.fit}, length ${c.length_adjust_cm} cm)` }))),
      el("h4", { text: "Size charts" }), (spec.size_charts || []).map((ch) => el("div", { class: "md-table" }, el("p", { class: "small", text: ch.name }),
        el("table", {}, el("tr", {}, el("th", { text: "Size" }), ch.columns.map((c) => el("th", { text: c.en }))),
          ch.rows.map((r) => el("tr", {}, el("td", { text: r.size }), ch.columns.map((c) => el("td", { text: r.values[c.key] || "" }))))))),
      el("p", { class: "small muted", text: "Draft: a pattern maker must check it against a real sample. You can edit the size charts after “Turn into product” (Categories & sizes)." })) : null

    root.replaceChildren(
      title,
      el("div", { class: "steps-bar", style: { marginTop: "10px" } }, names.map((n, i) => el("span", { class: stepsDone[i] ? "done" : i === current ? "on" : "", text: `${stepsDone[i] ? "✓ " : ""}${n}` }))),
      el("p", { class: "quota", text: `Images today: ${data.usage} of ~${data.free} free` }),
      el("div", { class: "card" }, el("h2", { text: "1 · Sketches & details" }),
        el("p", { class: "small muted", text: "A sketch (paper photo is fine) and close-up crops of details: collar, buttons, waist, fabric. Photos of people are fine as inspiration here." }),
        inputsGrid, el("div", { class: "row gap", style: { marginTop: "10px" } },
          el("button", { class: "btn small", type: "button", onclick: () => upload("sketch") }, icon("image"), "Add sketch"),
          el("button", { class: "btn small", type: "button", onclick: () => upload("detail") }, icon("plus"), "Add detail (crop)")),
        el("div", { style: { marginTop: "10px" } }, notes),
        el("p", { class: "small muted", text: `For: ${(d.roles || []).map((r) => data.roles[r] || r).join(", ")} (first is the main design)` })),
      el("div", { class: "card" }, el("h2", { text: "2 · Design brief" }), briefView || el("p", { class: "small muted", text: "The AI reads your sketch and details and writes a brief for every family member." }), analyse),
      el("div", { class: "card" }, el("h2", { text: "3 · Options" }), el("p", { class: "small muted", text: "Tap an option to view it and choose. Each image takes about 10 seconds." }),
        optGrid, el("div", { class: "form", style: { marginTop: "10px" } }, el("div", { class: "row gap" }, gen4), feedback, el("div", { class: "row gap" }, gen2), hqBox, gemini)),
      el("div", { class: "card" }, el("h2", { text: "4 · Technical flats" }), el("p", { class: "small muted", text: "Black-and-white drawings for the tailor, made from the chosen option." }),
        el("div", { class: "studio-grid" }, front ? tile(front) : null, back ? tile(back) : null), el("div", { class: "row gap", style: { marginTop: "10px" } }, flatBtn("front"), flatBtn("back"))),
      el("div", { class: "card" }, el("h2", { text: "5 · The whole family" }),
        el("p", { class: "small muted", text: others.length ? "Each member is drawn from the flat sketch and fabric details, so the set matches." : "Only one role in this design. Add more roles to make a family set." }),
        familyGrid, el("div", { class: "row gap", style: { marginTop: "10px" } }, roleBtns, mock),
        mockImg ? el("img", { src: mockImg.url, alt: "Family board", style: { marginTop: "12px", borderRadius: "8px" } }) : null),
      el("div", { class: "card" }, el("h2", { text: "6 · Tech pack & product" }), specView,
        el("div", { class: "row gap", style: { marginTop: "10px" } }, tp,
          spec.name_id ? el("a", { class: "btn", href: `/api/studio/designs/${id}/pdf` }, icon("receipt"), "Download PDF") : null, prod),
        d.product ? el("a", { class: "link-btn", href: `#product/${d.product}`, style: { marginTop: "8px" }, text: "Open the product made from this design" }) : null),
      el("div", { class: "row", style: { justifyContent: "flex-end" } }, armed(el("button", { class: "btn small danger", type: "button", text: "Delete design" }), "Tap again", async () => { await api(`/studio/designs/${id}`, { method: "DELETE" }); go("studio") })))
  }
  draw()
}
