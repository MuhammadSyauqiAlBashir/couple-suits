/// <reference path="../pb_data/types.d.ts" />
// Couple Suits shop: collections prefixed `shop_`.
//
// Two machine logins, each with its own role (never the finance "service"
// role, so a shop bug can't reach household data):
//   shop_web   — the public storefront: reads the catalog, writes customer
//                data (orders, accounts, reviews, wishlists, stats).
//   shop_admin — the CMS: everything in the shop.
// People never talk to these collections directly; the shop services check
// who is asking first. The public pb.* site also blocks /api/collections/shop_*.
migrate((app) => {
  const users = app.findCollectionByNameOrId("users")
  const role = users.fields.getByName("role")
  for (const r of ["shop_web", "shop_admin"]) if (!role.values.includes(r)) role.values = [...role.values, r]
  app.save(users)

  const W = "@request.auth.role = 'shop_web'"
  const A = "@request.auth.role = 'shop_admin'"
  const WA = `${W} || ${A}`
  const catalog = { listRule: WA, viewRule: WA, createRule: A, updateRule: A, deleteRule: A }      // web reads
  const customer = { listRule: WA, viewRule: WA, createRule: WA, updateRule: WA, deleteRule: WA }  // web writes
  const adminOnly = { listRule: A, viewRule: A, createRule: A, updateRule: A, deleteRule: A }
  const append = { listRule: WA, viewRule: WA, createRule: WA, updateRule: A, deleteRule: A }      // web adds

  const created = () => ({ type: "autodate", name: "created", onCreate: true, onUpdate: false })
  const updated = () => ({ type: "autodate", name: "updated", onCreate: true, onUpdate: true })
  const text = (name, max = 500, extra = {}) => ({ type: "text", name, max, ...extra })
  const num = (name, extra = {}) => ({ type: "number", name, ...extra })
  const money = (name, extra = {}) => ({ type: "number", name, onlyInt: true, ...extra })
  const json = (name, maxSize = 200000) => ({ type: "json", name, maxSize })
  const bool = (name) => ({ type: "bool", name })
  const date = (name) => ({ type: "date", name })
  const select = (name, values, extra = {}) => ({ type: "select", name, values, maxSelect: 1, ...extra })
  const rel = (name, coll, extra = {}) => ({ type: "relation", name, collectionId: coll.id, maxSelect: 1, cascadeDelete: false, ...extra })
  const bi = (name, max = 300, extra = {}) => [text(`${name}_id`, max, extra), text(`${name}_en`, max)]

  const make = (name, rules, fields, indexes = [], type = "base", extra = {}) => {
    const c = new Collection({ type, name, ...rules, fields: [...fields, created(), updated()], indexes, ...extra })
    app.save(c)
    return c
  }

  make("shop_kv", catalog, [text("key", 100, { required: true }), json("value", 500000)],
    ["CREATE UNIQUE INDEX idx_shop_kv_key ON shop_kv (key)"])
  make("shop_admins", adminOnly, [rel("user", users, { required: true, cascadeDelete: true }), text("username", 64)],
    ["CREATE UNIQUE INDEX idx_shop_admins_user ON shop_admins (user)"])

  const categories = make("shop_categories", catalog, [
    text("slug", 80, { required: true }), ...bi("name", 120, { required: true }), ...bi("description", 2000),
    text("image", 40), num("sort", { onlyInt: true }), bool("active"),
  ], ["CREATE UNIQUE INDEX idx_shop_categories_slug ON shop_categories (slug)"])

  const collections = make("shop_collections", catalog, [
    text("slug", 80, { required: true }), ...bi("name", 120, { required: true }), ...bi("description", 2000),
    text("image", 40), num("sort", { onlyInt: true }), bool("active"), bool("featured"),
  ], ["CREATE UNIQUE INDEX idx_shop_collections_slug ON shop_collections (slug)"])

  // Images live on disk (/var/lib/couple-suits/media/<key>/<width>.webp); this is the index.
  make("shop_media", append, [
    text("key", 40, { required: true }), select("kind", ["product", "content", "review", "brand"], { required: true }),
    ...bi("alt", 300), num("width", { onlyInt: true }), num("height", { onlyInt: true }), json("sizes", 2000),
    text("color", 40), text("uploaded_by", 64),
  ], ["CREATE UNIQUE INDEX idx_shop_media_key ON shop_media (key)"])

  const CUTS = ["men", "women", "boys", "girls", "baby", "unisex_adult", "unisex_kids"]
  const charts = make("shop_size_charts", catalog, [
    text("name", 120, { required: true }), select("cut", CUTS, { required: true }), json("columns", 5000),
    json("rows", 50000), ...bi("notes", 2000),
  ])

  const products = make("shop_products", catalog, [
    text("slug", 120, { required: true }), ...bi("name", 200, { required: true }), ...bi("summary", 500),
    ...bi("description", 10000), ...bi("material", 1000), ...bi("care", 1000),
    rel("category", categories), rel("collections", collections, { maxSelect: 20 }), json("tags", 5000),
    select("status", ["draft", "live", "archived"], { required: true }),
    select("stock_mode", ["ready", "preorder"], { required: true }), num("preorder_days", { onlyInt: true, min: 0 }),
    json("cuts", 2000), json("cut_prices", 5000), json("colors", 10000), json("media", 10000), json("size_charts", 5000),
    num("sale_percent", { onlyInt: true, min: 0, max: 90 }), date("sale_start"), date("sale_end"),
    bool("featured"), num("sort", { onlyInt: true }), text("seo_title", 200), text("seo_description", 400),
    text("design_id", 40), bool("demo"),
  ], [
    "CREATE UNIQUE INDEX idx_shop_products_slug ON shop_products (slug)",
    "CREATE INDEX idx_shop_products_status ON shop_products (status)",
  ])

  // Web may update stock (orders reserve it); everything else about variants is admin-only in code.
  const variants = make("shop_variants", { ...catalog, updateRule: WA }, [
    rel("product", products, { required: true, cascadeDelete: true }), select("cut", CUTS, { required: true }),
    text("size", 20, { required: true }), text("color", 40), num("stock", { onlyInt: true }), text("sku", 60), bool("active"),
  ], ["CREATE UNIQUE INDEX idx_shop_variants_key ON shop_variants (product, cut, size, color)"])

  // manageRule lets the CMS set a new password for a customer (no reset emails yet).
  const customers = make("shop_customers", { ...customer, deleteRule: A, manageRule: A }, [
    text("name", 120), text("phone", 30), text("birthday", 10), text("anniversary", 10), text("lang", 5),
    bool("marketing_ok"), text("note", 1000),
  ], [], "auth", { passwordAuth: { enabled: true, identityFields: ["email"] } })

  make("shop_family_members", customer, [
    rel("customer", customers, { required: true, cascadeDelete: true }), text("name", 80), text("role", 40, { required: true }),
    select("cut", CUTS, { required: true }), text("size", 20), text("birthday", 10), num("sort", { onlyInt: true }),
  ], ["CREATE INDEX idx_shop_family_customer ON shop_family_members (customer)"])

  const orders = make("shop_orders", { listRule: WA, viewRule: WA, createRule: WA, updateRule: A, deleteRule: A }, [
    text("number", 30, { required: true }), text("token", 64, { required: true }), rel("customer", customers),
    text("contact_name", 120, { required: true }), text("phone", 30, { required: true }), text("email", 200),
    json("address", 5000), text("lang", 5),
    select("status", ["new", "confirmed", "awaiting_payment", "paid", "in_production", "shipped", "completed", "cancelled"], { required: true }),
    money("items_total"), money("discount_total"), money("shipping_cost"), bool("shipping_set"), money("total"),
    text("voucher_code", 40), json("discounts", 10000), text("customer_note", 2000), text("admin_note", 5000),
    json("timeline", 50000), text("shipping_courier", 60), text("tracking_number", 80), bool("notified"), bool("has_preorder"),
  ], [
    "CREATE UNIQUE INDEX idx_shop_orders_number ON shop_orders (number)",
    "CREATE INDEX idx_shop_orders_status ON shop_orders (status)",
    "CREATE INDEX idx_shop_orders_customer ON shop_orders (customer)",
  ])

  make("shop_order_items", { listRule: WA, viewRule: WA, createRule: WA, updateRule: A, deleteRule: A }, [
    rel("order", orders, { required: true, cascadeDelete: true }), rel("product", products), rel("variant", variants),
    text("product_name", 200), text("product_slug", 120), select("cut", CUTS), text("size", 20), text("color", 40),
    text("role", 40), text("member_name", 80), text("set_key", 40), money("unit_price"), money("price"), num("qty", { onlyInt: true, min: 1 }),
    money("line_total"), text("image", 40), bool("preorder"), num("preorder_days", { onlyInt: true }),
  ], ["CREATE INDEX idx_shop_order_items_order ON shop_order_items (order)"])

  make("shop_wishlist", customer, [
    rel("customer", customers, { required: true, cascadeDelete: true }), rel("product", products, { required: true, cascadeDelete: true }),
  ], ["CREATE UNIQUE INDEX idx_shop_wishlist ON shop_wishlist (customer, product)"])

  make("shop_views", customer, [
    rel("customer", customers, { required: true, cascadeDelete: true }), rel("product", products, { required: true, cascadeDelete: true }),
  ], ["CREATE UNIQUE INDEX idx_shop_views ON shop_views (customer, product)"])

  make("shop_reviews", { listRule: WA, viewRule: WA, createRule: WA, updateRule: A, deleteRule: A }, [
    rel("product", products, { required: true, cascadeDelete: true }), rel("customer", customers), rel("order", orders),
    text("name", 80), num("rating", { onlyInt: true, min: 1, max: 5 }), text("text", 3000), json("photos", 2000),
    text("family", 120), select("status", ["pending", "approved", "hidden"], { required: true }), text("reply", 2000),
  ], ["CREATE INDEX idx_shop_reviews_product ON shop_reviews (product, status)"])

  const vouchers = make("shop_vouchers", catalog, [
    text("code", 40, { required: true }), ...bi("label", 200), select("kind", ["percent", "amount"], { required: true }),
    money("value", { min: 0 }), money("min_spend", { min: 0 }), money("max_discount", { min: 0 }),
    date("starts"), date("ends"), num("usage_limit", { onlyInt: true, min: 0 }), num("per_customer_limit", { onlyInt: true, min: 0 }),
    bool("active"), select("special", ["birthday", "anniversary"]), rel("customer", customers, { cascadeDelete: true }),
  ], ["CREATE UNIQUE INDEX idx_shop_vouchers_code ON shop_vouchers (code)"])

  make("shop_voucher_uses", append, [
    rel("voucher", vouchers, { required: true, cascadeDelete: true }), rel("order", orders, { cascadeDelete: true }),
    rel("customer", customers), text("phone", 30),
  ], ["CREATE INDEX idx_shop_voucher_uses ON shop_voucher_uses (voucher)"])

  make("shop_set_discounts", catalog, [
    num("min_members", { onlyInt: true, min: 2, required: true }), num("percent", { onlyInt: true, min: 1, max: 50, required: true }),
    ...bi("label", 200), bool("active"),
  ])

  make("shop_pages", catalog, [
    text("slug", 80, { required: true }), ...bi("title", 200, { required: true }), ...bi("body", 50000),
    select("status", ["draft", "live"], { required: true }), bool("in_footer"), num("sort", { onlyInt: true }),
  ], ["CREATE UNIQUE INDEX idx_shop_pages_slug ON shop_pages (slug)"])

  make("shop_posts", catalog, [
    text("slug", 120, { required: true }), ...bi("title", 200, { required: true }), ...bi("excerpt", 500), ...bi("body", 100000),
    text("cover", 40), select("status", ["draft", "live"], { required: true }), date("published_at"), json("tags", 2000),
  ], ["CREATE UNIQUE INDEX idx_shop_posts_slug ON shop_posts (slug)"])

  make("shop_lookbooks", catalog, [
    text("slug", 120, { required: true }), ...bi("title", 200, { required: true }), ...bi("intro", 2000), text("cover", 40),
    json("blocks", 100000), select("status", ["draft", "live"], { required: true }), num("sort", { onlyInt: true }),
  ], ["CREATE UNIQUE INDEX idx_shop_lookbooks_slug ON shop_lookbooks (slug)"])

  make("shop_home_sections", catalog, [
    select("kind", ["hero", "sets", "categories", "collection", "products", "lookbook", "story", "usp", "reviews"], { required: true }),
    json("data", 50000), num("sort", { onlyInt: true }), bool("active"),
  ])

  // Daily counters (visits, product views, add-to-cart, orders, sources). Web increments.
  make("shop_stats", { listRule: WA, viewRule: WA, createRule: WA, updateRule: WA, deleteRule: A }, [
    text("day", 10, { required: true }), text("metric", 40, { required: true }), text("dim", 200), num("count", { onlyInt: true }),
  ], ["CREATE UNIQUE INDEX idx_shop_stats ON shop_stats (day, metric, dim)"])

  // AI design studio (admin only; images stored privately on disk).
  const designs = make("shop_designs", adminOnly, [
    text("title", 200, { required: true }), select("status", ["draft", "options", "chosen", "done"], { required: true }),
    json("roles", 5000), text("notes", 5000), json("brief", 50000), json("chosen", 5000), json("spec", 200000),
    text("engine", 60), text("product", 40), text("created_by", 64),
  ])
  make("shop_design_assets", adminOnly, [
    rel("design", designs, { required: true, cascadeDelete: true }),
    select("kind", ["sketch", "detail", "option", "flat", "role", "mockup"], { required: true }),
    text("path", 300, { required: true }), text("label", 200), num("round", { onlyInt: true }), json("meta", 20000), bool("favorite"),
  ], ["CREATE INDEX idx_shop_design_assets ON shop_design_assets (design, kind)"])

  make("shop_push_subs", adminOnly, [
    rel("user", users, { required: true, cascadeDelete: true }), text("endpoint", 1000, { required: true }),
    text("p256dh", 200, { required: true }), text("auth", 100, { required: true }), text("ua", 300),
  ], ["CREATE UNIQUE INDEX idx_shop_push_endpoint ON shop_push_subs (endpoint)"])
  make("shop_passkeys", adminOnly, [
    rel("user", users, { required: true, cascadeDelete: true }), text("cred_id", 1000, { required: true }),
    text("public_key", 2000, { required: true }), num("sign_count", { onlyInt: true, min: 0 }), text("name", 100),
  ], ["CREATE UNIQUE INDEX idx_shop_passkeys_cred ON shop_passkeys (cred_id)"])
  make("shop_events", adminOnly, [text("key", 200, { required: true })],
    ["CREATE UNIQUE INDEX idx_shop_events_key ON shop_events (key)"])
}, (app) => {
  const names = ["shop_events", "shop_passkeys", "shop_push_subs", "shop_design_assets", "shop_designs", "shop_stats",
    "shop_home_sections", "shop_lookbooks", "shop_posts", "shop_pages", "shop_set_discounts", "shop_voucher_uses",
    "shop_vouchers", "shop_reviews", "shop_views", "shop_wishlist", "shop_order_items", "shop_orders",
    "shop_family_members", "shop_customers", "shop_variants", "shop_products", "shop_size_charts", "shop_media",
    "shop_collections", "shop_categories", "shop_admins", "shop_kv"]
  for (const n of names) { try { app.delete(app.findCollectionByNameOrId(n)) } catch (_) {} }
})
