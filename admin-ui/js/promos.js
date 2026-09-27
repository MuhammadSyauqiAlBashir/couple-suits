import { el, rp } from "./lib.js?v=__VERSION__"
import { manager } from "./crud.js?v=__VERSION__"

export async function renderPromos(page) {
  page.append(el("h1", { text: "Promotions" }),
    el("p", { class: "muted", text: "Sale prices and countdowns are set per product (Products → Sale). Birthday and anniversary vouchers are created automatically for customers who allow offers (percentage in Settings)." }))
  const vouchers = el("div", { class: "card" })
  const sets = el("div", { class: "card" })
  page.append(sets, vouchers)
  await manager(sets, {
    name: "set_discounts", title: "Family-set discounts", single: "set discount", addLabel: "Add rule",
    note: "Applied automatically when a customer adds a family set with at least this many people. The biggest matching rule wins.",
    defaults: { min_members: 3, percent: 5, active: true },
    fields: [
      { key: "min_members", type: "number", label: "Minimum people in the set", min: 2, max: 20 },
      { key: "percent", type: "number", label: "Discount %", min: 1, max: 50 },
      { key: "label", type: "bi", label: "Label shown in the bag (optional)" },
      { key: "active", type: "check", label: "Active" },
    ],
    row: (r) => ({ title: `${r.min_members}+ people → ${r.percent}% off`, sub: r.label_id, side: el("span", { class: `pill ${r.active ? "ok" : ""}`, text: r.active ? "on" : "off" }) }),
  })
  await manager(vouchers, {
    name: "vouchers", title: "Voucher codes", single: "voucher", addLabel: "New voucher",
    defaults: { kind: "percent", value: 10, active: true, per_customer_limit: 1 },
    fields: [
      { key: "code", label: "Code", placeholder: "LEBARAN10", hint: "Letters and numbers; customers type it in the bag." },
      { key: "kind", type: "select", label: "Type", options: [["percent", "Percent off"], ["amount", "Rupiah off"]] },
      { key: "value", type: "number", label: "Value (percent or rupiah)", min: 0 },
      { key: "max_discount", type: "money", label: "Max discount for percent vouchers (0 = none)" },
      { key: "min_spend", type: "money", label: "Minimum spend (0 = none)" },
      { key: "starts", type: "datetime", label: "Starts (optional)" },
      { key: "ends", type: "datetime", label: "Ends (optional)" },
      { key: "usage_limit", type: "number", label: "Total uses allowed (0 = unlimited)", min: 0 },
      { key: "per_customer_limit", type: "number", label: "Uses per customer / phone (0 = unlimited)", min: 0 },
      { key: "label", type: "bi", label: "Label shown in the bag (optional)" },
      { key: "active", type: "check", label: "Active" },
    ],
    row: (v) => ({ title: v.code, sub: `${v.kind === "percent" ? `${v.value}% off` : `${rp(v.value)} off`}${v.min_spend ? ` · min ${rp(v.min_spend)}` : ""}${v.special ? ` · ${v.special} gift` : ""}${v.ends ? ` · until ${v.ends.slice(0, 10)}` : ""}`,
      side: el("span", { class: `pill ${v.active ? "ok" : ""}`, text: v.active ? "active" : "off" }) }),
  })
}
