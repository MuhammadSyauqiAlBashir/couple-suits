import { api, armed, busy, el, form, icon, toast } from "./lib.js?v=__VERSION__"
import { enablePush, pushStatus, registerPasskey, state } from "./app.js?v=__VERSION__"

export async function renderSettings(page) {
  const d = await api("/settings")
  const s = d.settings
  const brand = form([
    { key: "brand_name", label: "Brand name" },
    { key: "tagline", type: "bi", label: "Tagline" },
    { key: "logo", type: "image", label: "Logo (optional, wide PNG/JPG on white)", kind: "brand" },
    { key: "accent", type: "color", label: "Button colour" },
    { key: "announcement", type: "bi", label: "Announcement bar (top of every page)" },
  ], s)
  const contact = form([
    { key: "whatsapp", label: "Shop WhatsApp number", hint: "Customers tap to chat; order messages open in your WhatsApp." },
    { key: "instagram", label: "Instagram username" },
    { key: "tiktok", label: "TikTok username" },
    { key: "email", label: "Contact email" },
    { key: "city", label: "City (footer)" },
  ], s)
  const orders = form([
    { key: "bank_info", type: "bi", label: "Payment details (sent in the WhatsApp confirmation)", rows: 3, placeholder: "BCA 123456789 a.n. …" },
    { key: "payment_info", type: "bi", label: "How payment works (shown to customers)", rows: 2 },
    { key: "shipping_note", type: "bi", label: "Shipping note (shown to customers)", rows: 2 },
    { key: "special_voucher_percent", type: "number", label: "Birthday / anniversary voucher % (0 = off)", min: 0, max: 50 },
    { key: "special_voucher_days", type: "number", label: "…valid for days", min: 1, max: 60 },
  ], s)
  const saveBtn = el("button", { class: "btn primary", type: "button", text: "Save settings" })
  saveBtn.onclick = () => busy(saveBtn, async () => {
    try { await api("/settings", { method: "PUT", json: { ...brand.values(), ...contact.values(), ...orders.values() } }); toast("Saved") } catch (e) { toast(e.message, "bad") }
  })

  // Admins
  const admins = el("div")
  const drawAdmins = (names) => {
    const input = el("input", { class: "inline", placeholder: "username (their lyrsync/finance login)" })
    const add = el("button", { class: "btn small", type: "button", text: "Add" })
    add.onclick = () => busy(add, async () => { try { const r = await api("/admins", { method: "POST", json: { username: input.value } }); drawAdmins(r.admin_usernames); toast("Added — they can log in now") } catch (e) { toast(e.message, "bad") } })
    admins.replaceChildren(
      el("p", { class: "small muted", text: "The owner (admin role) always has access. Add your wife's username to give her full access." }),
      ...names.map((n) => el("div", { class: "rank" }, el("span", { text: n }), n === state.me.username ? el("small", { class: "muted", text: "you" }) :
        armed(el("button", { class: "btn small danger", type: "button", text: "Remove" }), "Tap again", async () => { const r = await api(`/admins/${encodeURIComponent(n)}`, { method: "DELETE" }); drawAdmins(r.admin_usernames) }))),
      el("div", { class: "row gap", style: { marginTop: "8px" } }, el("span", { class: "grow" }, input), add),
      el("p", { class: "small muted", text: `Signed in so far: ${d.admins.map((a) => a.username).join(", ") || "—"}` }))
  }
  drawAdmins(d.admin_usernames)

  // This device
  const device = el("div")
  const drawDevice = async () => {
    const st = await pushStatus().catch(() => "unsupported")
    const keys = (await api("/passkeys")).passkeys
    const pushBtn = el("button", { class: "btn small", type: "button", text: st === "on" ? "Send a test notification" : "Turn on order notifications" })
    pushBtn.onclick = () => busy(pushBtn, async () => {
      try { if (st !== "on") await enablePush(); const r = await api("/push/test", { method: "POST" }); toast(r.sent ? "Test sent" : "Subscribed — test not delivered yet"); drawDevice() } catch (e) { toast(e.message, "bad") }
    })
    const faceBtn = el("button", { class: "btn small", type: "button" }, icon("face"), keys.length ? "Add Face ID on this device" : "Set up Face ID lock")
    faceBtn.onclick = () => busy(faceBtn, async () => { try { await registerPasskey(); toast("Face ID lock is on"); drawDevice() } catch (e) { toast(e.name === "NotAllowedError" ? "Cancelled" : e.message, "bad") } })
    device.replaceChildren(
      el("p", { class: "small", text: st === "on" ? "✓ Notifications are on for this device." : st === "unsupported" ? "Notifications need the Home Screen app (Safari → Share → Add to Home Screen)." : st === "blocked" ? "Notifications are blocked in the phone settings." : "Get a push for every new order." }),
      pushBtn,
      el("p", { class: "small", style: { marginTop: "14px" }, text: keys.length ? `✓ Face ID lock on (${keys.length} device${keys.length > 1 ? "s" : ""}). The app locks after 10 minutes away.` : "Lock the admin app with Face ID when you're away for 10 minutes." }),
      faceBtn,
      el("div", { style: { marginTop: "14px" } }, el("button", { class: "link-btn", type: "button", text: "Log out", onclick: async () => { await api("/logout", { method: "POST" }); location.reload() } })))
  }
  await drawDevice()

  const demo = d.demo ? el("div", { class: "card" }, el("h2", { text: "Demo catalog" }),
    el("p", { class: "small muted", text: "The shop has 8 demo products with AI-generated photos. Remove them when your real products are ready (orders are kept)." }),
    armed(el("button", { class: "btn danger", type: "button", text: "Remove demo catalog" }), "Tap again to remove", async () => {
      const r = await api("/demo", { method: "DELETE" }); toast(`Removed ${r.removed} demo products`); location.hash = "#products"
    })) : null

  page.append(el("h1", { text: "Settings" }),
    el("div", { class: "card" }, el("h2", { text: "This device" }), device),
    el("div", { class: "card" }, el("h2", { text: "Brand" }), brand.node),
    el("div", { class: "card" }, el("h2", { text: "Contact" }), contact.node),
    el("div", { class: "card" }, el("h2", { text: "Orders & payment" }), orders.node),
    el("div", { class: "card" }, el("h2", { text: "Admins" }), admins),
    demo,
    el("div", { class: "card" }, el("h2", { text: "AI services" }), el("p", { class: "small", text: `Image generation (Cloudflare FLUX.2): ${d.flux ? "connected" : "not configured"} · Text AI (Gemini): ${d.gemini ? "connected" : "not configured"}` })),
    el("div", { class: "sticky-save" }, saveBtn))
}
