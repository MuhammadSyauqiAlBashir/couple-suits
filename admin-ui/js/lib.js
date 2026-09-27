// Shared helpers: API calls, formatting, DOM building, sheets, toasts, forms.
// (Started from the finance app's lib.js.)

export const $ = (sel, root = document) => root.querySelector(sel)
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)]
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ---------------------------------------------------------------------------
// DOM
// ---------------------------------------------------------------------------
// Views build child lists with optional parts (`cond ? node : null`); make
// append/replaceChildren skip those instead of printing "null".
for (const proto of [Element.prototype, DocumentFragment.prototype]) {
  for (const name of ["append", "replaceChildren"]) {
    const orig = proto[name]
    proto[name] = function (...nodes) {
      return orig.apply(this, nodes.flat().filter((n) => n !== null && n !== undefined && n !== false))
    }
  }
}

// el("div", {class: "x", onclick: fn}, child, "text", ...). Text is always set
// with textContent, never innerHTML, so data from emails can't inject markup.
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag)
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue
    if (k === "class") node.className = v
    else if (k === "text") node.textContent = v
    else if (k === "style" && typeof v === "object") Object.assign(node.style, v)
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v)
    else if (k === "value") node.value = v
    else if (k === "checked") node.checked = !!v
    else node.setAttribute(k, v === true ? "" : v)
  }
  for (const c of children.flat()) {
    if (c === undefined || c === null || c === false) continue
    node.append(c instanceof Node ? c : document.createTextNode(String(c)))
  }
  return node
}

export const SVGNS = "http://www.w3.org/2000/svg"
export function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVGNS, tag)
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, v)
  for (const c of children.flat()) if (c) node.append(c)
  return node
}

// Small inline icons (stroke paths, 24x24).
const ICONS = {
  home: "M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  inbox: "M4 13h4l2 3h4l2-3h4M4 13l2-8h12l2 8v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z",
  wallet: "M3 7a2 2 0 0 1 2-2h13v4M3 7v11a2 2 0 0 0 2 2h15V9H5a2 2 0 0 1-2-2zm14 7h.01",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.3 7.3 0 0 0-2-1.2L14.5 3h-4l-.4 2.6a7.3 7.3 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.3 7.3 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7.3 7.3 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2z",
  plus: "M12 5v14M5 12h14",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  check: "M5 13l4 4L19 7",
  x: "M6 6l12 12M18 6L6 18",
  chevron: "M9 6l6 6-6 6",
  back: "M15 6l-6 6 6 6",
  alert: "M12 9v4m0 4h.01M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3",
  send: "M4 12l16-8-6 16-3-7z",
  lock: "M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4",
  face: "M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M9 10v1M15 10v1M12 10v4h-1M9.5 16.5c1.5 1 3.5 1 5 0",
  split: "M6 3v6a6 6 0 0 0 6 6h6M18 15l-3-3M18 15l-3 3M6 21v-6",
  move: "M7 7h13M17 4l3 3-3 3M17 17H4M7 14l-3 3 3 3",
  trash: "M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3",
  edit: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4",
  bell: "M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0",
  target: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-5a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm0-3a1 1 0 1 0 0-2 1 1 0 0 0 0 2z",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  mail: "M4 6h16v12H4zM4 7l8 6 8-6",
  image: "M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9h.01",
  bag: "M5 8h14l-1 12H6zM9 8V6a3 3 0 0 1 6 0v2",
  box: "M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2 20a7 7 0 0 1 14 0M16 4.5a3.5 3.5 0 0 1 0 6.5M18 13.5a6.5 6.5 0 0 1 4 6.5",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z",
  tag: "M3 12V4h8l10 10-8 8zM7.5 8.5h.01",
  layout: "M4 4h16v16H4zM4 10h16M10 10v10",
  ruler: "M3 16L16 3l5 5L8 21zM7 12l2 2M10 9l2 2M13 6l2 2",
  wa: "M4 20l1.3-4A8 8 0 1 1 8 18.7zM9 9c0 3 3 6 6 6l1-1.5-2-1-1 1c-1-.5-2-1.5-2.5-2.5l1-1-1-2z",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  copy: "M8 8h12v12H8zM4 16V4h12",
  up: "M12 19V5M6 11l6-6 6 6",
  down: "M12 5v14M6 13l6 6 6-6",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  search: "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4",
  store: "M4 9l1-5h14l1 5M4 9v11h16V9M4 9a3 3 0 0 0 5 0 3 3 0 0 0 6 0 3 3 0 0 0 5 0M10 20v-5h4v5",
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  link: "M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  truck: "M2 6h12v10H2zM14 10h4l4 4v2h-8zM6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  palette: "M12 21a9 9 0 1 1 9-9c0 2-1.5 3-3.5 3H15a2 2 0 0 0-1 3.7c.6.5.4 2.3-2 2.3zM7.5 11.5h.01M10.5 7.5h.01M15.5 7.5h.01",
  pen: "M4 20h4L19 9l-4-4L4 16zM14 6l4 4M13 20h7",
}
export function icon(name, cls = "") {
  return svg("svg", { viewBox: "0 0 24 24", class: `ico ${cls}`, "aria-hidden": "true" }, svg("path", { d: ICONS[name] || "" }))
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------
const nf = new Intl.NumberFormat("id-ID")
export const rp = (n) => (n < 0 ? "−Rp" : "Rp") + nf.format(Math.abs(Math.round(n || 0)))
export function rpShort(n) {
  const a = Math.abs(n || 0)
  const sign = n < 0 ? "−" : ""
  const trim = (x) => (Math.round(x * 10) / 10).toString().replace(".", ",")
  if (a >= 1e9) return `${sign}${trim(a / 1e9)}M`
  if (a >= 1e6) return `${sign}${trim(a / 1e6)}jt`
  if (a >= 1e3) return `${sign}${Math.round(a / 1e3)}rb`
  return `${sign}${Math.round(a)}`
}
export const pct = (n) => `${Math.round(n || 0)}%`
// Full amount when short, compact (Rp24jt, Rp325rb) when it wouldn't fit a small tile.
export const rpFit = (n, max = 8) => (rp(n).length <= max ? rp(n) : (n < 0 ? "−Rp" : "Rp") + rpShort(Math.abs(n)))

export function parseDate(s) {
  if (!s) return null
  if (s.length === 10) return new Date(s + "T00:00:00+07:00")
  return new Date(String(s).replace(" ", "T"))
}
const TZ = "Asia/Jakarta"
export const fmtDate = (s, opts = { day: "numeric", month: "short" }) =>
  s ? new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...opts }).format(parseDate(s)) : ""
export const fmtTime = (s) => s ? new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }).format(parseDate(s)) : ""
export const fmtDay = (s) => fmtDate(s, { weekday: "short", day: "numeric", month: "short" })
export function localDateKey(s) {
  const d = parseDate(s)
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(d) // YYYY-MM-DD
}
export const todayKey = () => new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date())
export function nowLocalInput() {
  const d = new Date()
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d)
  const g = (t) => parts.find((p) => p.type === t).value
  return `${g("year")}-${g("month")}-${g("day")}T${g("hour") === "24" ? "00" : g("hour")}:${g("minute")}`
}
export function relTime(s) {
  const d = parseDate(s)
  const sec = (Date.now() - d.getTime()) / 1000
  if (sec < 60) return "just now"
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`
  return fmtDate(s)
}
export const greeting = () => {
  const h = Number(new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "numeric", hour12: false }).format(new Date()))
  return h < 11 ? "Good morning" : h < 15 ? "Good afternoon" : h < 19 ? "Good evening" : "Good night"
}

// Money input: shows 1.250.000 while typing, value() gives the integer.
export function moneyInput(value = 0, props = {}) {
  const input = el("input", { inputmode: "numeric", autocomplete: "off", class: "money-input", ...props })
  const set = (n) => { input.value = n ? nf.format(n) : "" }
  input.addEventListener("input", () => {
    const n = Number(input.value.replace(/\D/g, "")) || 0
    const pos = input.value.length - input.selectionStart
    set(n)
    const p = Math.max(0, input.value.length - pos)
    try { input.setSelectionRange(p, p) } catch (_) {}
  })
  set(value)
  input.money = () => Number(input.value.replace(/\D/g, "")) || 0
  input.setMoney = set
  return input
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------
export class ApiError extends Error {
  constructor(status, message, data) {
    super(message)
    this.status = status
    this.data = data
  }
}

let onAuthProblem = () => {}
export const setAuthHandler = (fn) => { onAuthProblem = fn }

// After the app has been asleep a long time, iOS often reuses a connection the
// server already closed, so the first request fails. Retry quickly before
// reporting "no connection".
export async function fetchRetry(url, opts = {}, tries = 3) {
  for (let i = 0; ; i++) {
    try {
      return await fetch(url, opts)
    } catch (err) {
      if (i >= tries - 1) throw new ApiError(0, "No connection. Check your internet.")
      await sleep(600 * (i + 1))
    }
  }
}

export async function api(path, { method = "GET", json, body, quiet = false } = {}) {
  const opts = { method, credentials: "same-origin", headers: { "X-CSA": "1" } }
  if (json !== undefined) {
    opts.headers["Content-Type"] = "application/json"
    opts.body = JSON.stringify(json)
  } else if (body !== undefined) {
    opts.body = body
  }
  const res = await fetchRetry("/api" + path, opts, method === "GET" ? 3 : 1)  // never repeat a save
  let data = {}
  try { data = await res.json() } catch (_) {}
  if ((res.status === 401 || res.status === 423 || res.status === 403) && !quiet) onAuthProblem(res.status, data)
  if (!res.ok) throw new ApiError(res.status, data.error || `Something went wrong (${res.status}).`, data)
  return data
}

// ---------------------------------------------------------------------------
// Toast, sheets, confirm
// ---------------------------------------------------------------------------
let toastTimer
export function toast(msg, kind = "") {
  const t = $("#toast")
  t.textContent = msg
  t.className = `toast ${kind}`
  t.hidden = false
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (t.hidden = true), 2800)
}

// A bottom sheet built on <dialog>. Returns {dialog, body, close}.
export function sheet(title, { tall = false, onClose } = {}) {
  const body = el("div", { class: "sheet-body" })
  const closeBtn = el("button", { class: "icon-btn", type: "button", "aria-label": "Close" }, icon("x"))
  const dialog = el("dialog", { class: `sheet${tall ? " tall" : ""}` },
    el("div", { class: "sheet-grab" }),
    el("div", { class: "sheet-head" }, el("h2", { text: title }), closeBtn), body)
  const close = () => { if (dialog.open) dialog.close() }
  closeBtn.onclick = close
  dialog.addEventListener("click", (e) => { if (e.target === dialog) close() })
  dialog.addEventListener("close", () => { dialog.remove(); onClose && onClose() })
  document.body.append(dialog)
  dialog.setAttribute("tabindex", "-1")
  dialog.showModal()
  dialog.focus() // not the close button (avoids a focus ring on open)
  return { dialog, body, close, setTitle: (t) => { $("h2", dialog).textContent = t } }
}

// Two-tap confirm on a button (no browser dialogs).
export function armed(button, label, action) {
  let armedAt = 0
  const original = button.textContent
  button.addEventListener("click", async () => {
    if (Date.now() - armedAt > 3000) {
      armedAt = Date.now()
      button.textContent = label
      button.classList.add("armed")
      setTimeout(() => { if (Date.now() - armedAt >= 3000) { button.textContent = original; button.classList.remove("armed") } }, 3100)
      return
    }
    armedAt = 0
    button.classList.remove("armed")
    button.textContent = original
    await action()
  })
  return button
}

export async function busy(button, fn) {
  const was = button.disabled
  button.disabled = true
  button.classList.add("loading")
  try { return await fn() } finally { button.disabled = was; button.classList.remove("loading") }
}

// Very small, safe markdown for AI text: headings, bullets, bold, paragraphs.
export function markdown(text) {
  const root = el("div", { class: "md" })
  let list = null
  const inline = (s) => {
    const frag = document.createDocumentFragment()
    const parts = String(s).split(/(\*\*[^*]+\*\*)/g)
    for (const p of parts) {
      if (p.startsWith("**") && p.endsWith("**")) frag.append(el("strong", { text: p.slice(2, -2) }))
      else frag.append(document.createTextNode(p.replace(/\*([^*]+)\*/g, "$1")))
    }
    return frag
  }
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trimEnd()
    if (/^\s*[-*•]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      if (!list) { list = el("ul"); root.append(list) }
      list.append(el("li", {}, inline(line.replace(/^\s*([-*•]|\d+\.)\s+/, ""))))
      continue
    }
    list = null
    if (!line.trim()) continue
    const h = line.match(/^(#{1,4})\s+(.*)$/)
    if (h) root.append(el(h[1].length <= 2 ? "h3" : "h4", {}, inline(h[2])))
    else if (/^\|/.test(line)) {
      if (/^\|[\s:|-]+\|$/.test(line)) continue
      const cells = line.split("|").slice(1, -1).map((c) => c.trim())
      let table = root.lastChild && root.lastChild.tagName === "DIV" && root.lastChild.classList.contains("md-table") ? root.lastChild.firstChild : null
      if (!table) { table = el("table"); root.append(el("div", { class: "md-table" }, table)) }
      table.append(el("tr", {}, cells.map((c) => el(table.children.length ? "td" : "th", {}, inline(c)))))
    } else root.append(el("p", {}, inline(line)))
  }
  return root
}

// Resize a photo in the browser before upload (max 1600px, JPEG ~0.82).
export async function shrinkImage(file, max = 1600) {
  if (!file.type.startsWith("image/")) throw new Error("Please choose a photo.")
  const url = URL.createObjectURL(file)
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image()
      i.onload = () => resolve(i)
      i.onerror = () => reject(new Error("Couldn't open that photo."))
      i.src = url
    })
    const scale = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight))
    const canvas = document.createElement("canvas")
    canvas.width = Math.round(img.naturalWidth * scale)
    canvas.height = Math.round(img.naturalHeight * scale)
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height)
    return await new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", 0.82))
  } finally {
    URL.revokeObjectURL(url)
  }
}

// Store per-device conveniences (never important data).
export const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v) } catch (_) { return d } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)) } catch (_) {} },
}

// ---------------------------------------------------------------------------
// Shop helpers
// ---------------------------------------------------------------------------
export const mediaUrl = (key, w = 400) => key ? `/media/${key}/${w}.webp` : ""
export const thumb = (key, cls = "thumb", w = 400) => key
  ? el("img", { src: mediaUrl(key, w), alt: "", loading: "lazy", class: cls })
  : el("span", { class: `${cls} ph` })

export const CUTS = {
  men: "Men", women: "Women", unisex_adult: "Adult (unisex)", boys: "Boys", girls: "Girls",
  unisex_kids: "Kids (unisex)", baby: "Baby",
}
export const SIZES = {
  adult: ["S", "M", "L", "XL", "XXL", "XXXL"], kids: ["1-2Y", "3-4Y", "5-6Y", "7-8Y", "9-10Y", "11-12Y"],
  baby: ["0-6M", "6-12M", "12-18M", "18-24M"],
}
export const cutGroup = (c) => (c === "baby" ? "baby" : ["boys", "girls", "unisex_kids"].includes(c) ? "kids" : "adult")
export const sizesFor = (c) => SIZES[cutGroup(c)]
export const STATUS = {
  new: "New", confirmed: "Confirmed", awaiting_payment: "Awaiting payment", paid: "Paid",
  in_production: "In production", shipped: "Shipped", completed: "Completed", cancelled: "Cancelled",
}
export const statusPill = (s) => el("span", { class: `pill st-${s}`, text: STATUS[s] || s })

// Upload one image file; returns the media record ({key, ...}).
export async function uploadImage(file, kind = "product") {
  const blob = await shrinkImage(file, 2400)
  const fd = new FormData()
  fd.append("file", blob, "photo.jpg")
  fd.append("kind", kind)
  return (await api("/media", { method: "POST", body: fd })).media
}

export function filePicker({ multiple = false, accept = "image/*" } = {}) {
  return new Promise((resolve) => {
    const input = el("input", { type: "file", accept, multiple })
    input.onchange = () => resolve([...input.files])
    input.click()
  })
}

// Pick from recent uploads or upload new. Resolves to a key (or null).
export function pickMedia({ kind = "" } = {}) {
  return new Promise((resolve) => {
    let done = false
    const s = sheet("Choose a photo", { tall: true, onClose: () => { if (!done) resolve(null) } })
    const grid = el("div", { class: "media-grid" })
    const choose = (key) => { done = true; resolve(key); s.close() }
    const up = el("button", { class: "btn primary", type: "button" }, icon("plus"), "Upload new")
    up.onclick = async () => {
      const files = await filePicker()
      if (!files.length) return
      await busy(up, async () => { try { const m = await uploadImage(files[0], kind || "content"); choose(m.key) } catch (e) { toast(e.message, "bad") } })
    }
    s.body.append(el("div", { class: "row gap" }, up), grid)
    api(`/media${kind ? `?kind=${kind}` : ""}`).then((d) => {
      grid.replaceChildren(...d.media.map((m) => el("button", { class: "media-tile", type: "button", onclick: () => choose(m.key) }, thumb(m.key))))
      if (!d.media.length) grid.append(el("p", { class: "muted", text: "No photos yet. Upload one." }))
    })
  })
}

// ---------------------------------------------------------------------------
// Forms: form(fields, values) → { node, values(), set(k, v) }
// field: { key, label, type, options, hint, lang (bilingual base name), rows, min, max, placeholder }
// types: text, textarea, markdown, number, money, select, check, date, datetime, color, image, images, tags, bi, bimd
// ---------------------------------------------------------------------------
async function translate(text, to) {
  const d = await api("/ai/translate", { method: "POST", json: { text, to } })
  return d.text
}

export function form(fields, values = {}) {
  const getters = {}
  const setters = {}
  const node = el("div", { class: "form" })
  for (const f of fields) {
    if (f.type === "section") { node.append(el("h3", { class: "form-section", text: f.label })); continue }
    if (f.type === "bi" || f.type === "bimd") {
      const mk = (lang) => {
        const v = values[`${f.key}_${lang}`] || ""
        const input = f.type === "bimd" || f.rows ? el("textarea", { rows: f.rows || 6, value: v, placeholder: f.placeholder || "" })
          : el("input", { value: v, placeholder: f.placeholder || "" })
        getters[`${f.key}_${lang}`] = () => input.value.trim()
        setters[`${f.key}_${lang}`] = (x) => { input.value = x || "" }
        return input
      }
      const idIn = mk("id"), enIn = mk("en")
      const tr = el("button", { class: "link-btn small", type: "button", title: "Translate with AI" }, icon("spark"), "Translate")
      tr.onclick = () => busy(tr, async () => {
        try {
          if (idIn.value.trim() && !enIn.value.trim()) enIn.value = await translate(idIn.value, "en")
          else if (enIn.value.trim() && !idIn.value.trim()) idIn.value = await translate(enIn.value, "id")
          else if (idIn.value.trim()) enIn.value = await translate(idIn.value, "en")
        } catch (e) { toast(e.message, "bad") }
      })
      node.append(el("div", { class: "field bi" },
        el("div", { class: "field-head" }, el("span", { text: f.label }), tr),
        el("label", { class: "lang" }, el("b", { text: "ID" }), idIn),
        el("label", { class: "lang" }, el("b", { text: "EN" }), enIn),
        f.hint ? el("p", { class: "hint", text: f.hint }) : null))
      continue
    }
    let input
    const v = values[f.key]
    switch (f.type) {
      case "textarea": case "markdown":
        input = el("textarea", { rows: f.rows || (f.type === "markdown" ? 10 : 3), value: v || "", placeholder: f.placeholder || "" })
        getters[f.key] = () => input.value.trim(); setters[f.key] = (x) => { input.value = x || "" }
        break
      case "number":
        input = el("input", { type: "number", inputmode: "numeric", value: v ?? "", min: f.min, max: f.max, step: f.step || 1 })
        getters[f.key] = () => (input.value === "" ? 0 : Number(input.value)); setters[f.key] = (x) => { input.value = x ?? "" }
        break
      case "money":
        input = moneyInput(v || 0)
        getters[f.key] = () => input.money(); setters[f.key] = (x) => input.setMoney(x)
        break
      case "select":
        input = el("select", {}, f.options.map(([val, lab]) => el("option", { value: val, text: lab })))
        input.value = v ?? f.options[0][0]
        getters[f.key] = () => input.value; setters[f.key] = (x) => { input.value = x }
        break
      case "check": {
        const box = el("input", { type: "checkbox", checked: !!v })
        getters[f.key] = () => box.checked; setters[f.key] = (x) => { box.checked = !!x }
        node.append(el("label", { class: "check" }, box, el("span", { text: f.label }), f.hint ? el("small", { class: "hint", text: f.hint }) : null))
        continue
      }
      case "date":
        input = el("input", { type: "date", value: (v || "").slice(0, 10) })
        getters[f.key] = () => input.value; setters[f.key] = (x) => { input.value = (x || "").slice(0, 10) }
        break
      case "datetime": {
        const toLocal = (x) => {
          if (!x) return ""
          const d = new Date(String(x).replace(" ", "T"))
          const p = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Jakarta", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).formatToParts(d)
          const g = (t) => p.find((q) => q.type === t).value
          return `${g("year")}-${g("month")}-${g("day")}T${g("hour") === "24" ? "00" : g("hour")}:${g("minute")}`
        }
        input = el("input", { type: "datetime-local", value: toLocal(v) })
        getters[f.key] = () => input.value ? new Date(input.value + ":00+07:00").toISOString().replace("T", " ") : ""
        setters[f.key] = (x) => { input.value = toLocal(x) }
        break
      }
      case "color":
        input = el("input", { type: "color", value: v || "#1c1b19" })
        getters[f.key] = () => input.value; setters[f.key] = (x) => { input.value = x }
        break
      case "tags":
        input = el("input", { value: (v || []).join(", "), placeholder: "comma, separated" })
        getters[f.key] = () => input.value.split(",").map((x) => x.trim()).filter(Boolean); setters[f.key] = (x) => { input.value = (x || []).join(", ") }
        break
      case "image": {
        let key = v || ""
        const box = el("div", { class: "image-field" })
        const draw = () => box.replaceChildren(key ? thumb(key, "thumb big", 800) : el("span", { class: "thumb big ph" }),
          el("div", { class: "col" },
            el("button", { class: "btn small", type: "button", text: key ? "Change" : "Choose photo", onclick: async () => { const k = await pickMedia({ kind: f.kind || "content" }); if (k) { key = k; draw() } } }),
            key ? el("button", { class: "link-btn small", type: "button", text: "Remove", onclick: () => { key = ""; draw() } }) : null))
        draw()
        input = box
        getters[f.key] = () => key; setters[f.key] = (x) => { key = x || ""; draw() }
        break
      }
      default:
        input = el("input", { value: v ?? "", placeholder: f.placeholder || "", maxlength: f.max || 500 })
        getters[f.key] = () => input.value.trim(); setters[f.key] = (x) => { input.value = x ?? "" }
    }
    node.append(el("label", { class: "field" }, el("span", { text: f.label }), input, f.hint ? el("small", { class: "hint", text: f.hint }) : null))
  }
  return {
    node,
    values() { const o = {}; for (const [k, g] of Object.entries(getters)) o[k] = g(); return o },
    set(k, v) { setters[k] && setters[k](v) },
  }
}

// Simple SVG bar chart (daily values).
export function bars(values, { height = 120, labels = [], fmt = (n) => n } = {}) {
  const max = Math.max(1, ...values)
  const w = 100 / Math.max(1, values.length)
  const g = svg("svg", { viewBox: `0 0 100 ${height}`, preserveAspectRatio: "none", class: "bars", role: "img" })
  values.forEach((v, i) => {
    const h = (v / max) * (height - 4)
    const r = svg("rect", { x: i * w + w * 0.15, y: height - h, width: w * 0.7, height: Math.max(h, v ? 1 : 0), rx: 0.6 })
    const t = svg("title"); t.textContent = `${labels[i] || ""}: ${fmt(v)}`
    r.append(t)
    g.append(r)
  })
  return g
}

export const copyText = async (text) => {
  try { await navigator.clipboard.writeText(text); toast("Copied") } catch (_) { toast("Couldn't copy", "bad") }
}
