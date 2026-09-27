/// <reference path="../pb_data/types.d.ts" />
// CLI: pocketbase shop-service <credentials-file> <shop_web|shop_admin>
// The file holds two lines: username, then password (32+ chars). Creates or
// resets a Couple Suits machine login with that role. Delete the file afterwards.
$app.rootCmd.addCommand(new Command({
  use: "shop-service",
  short: "create or reset a Couple Suits machine login (shop_web or shop_admin)",
  run: (cmd, args) => {
    if (args.length !== 2 || !["shop_web", "shop_admin"].includes(args[1])) {
      throw new Error("usage: shop-service <credentials-file> <shop_web|shop_admin>")
    }
    const raw = $os.readFile(args[0])
    const text = typeof raw === "string" ? raw : String.fromCharCode(...raw)
    const [username, password] = text.split("\n").map((s) => s.trim())
    if (!/^[a-z0-9_]{3,32}$/.test(username || "")) throw new Error("bad username")
    if (!password || password.length < 32) throw new Error("password must be at least 32 characters")
    const users = $app.findCollectionByNameOrId("users")
    let record
    try {
      record = $app.findFirstRecordByData(users, "username", username)
    } catch (_) {
      record = new Record(users)
      record.set("username", username)
      record.set("email", username + "@service.couple-suits.local")
    }
    record.set("approved", true)
    record.set("role", args[1])
    record.setPassword(password)
    $app.save(record)
    console.log("couple-suits login '" + username + "' saved (" + args[1] + ")")
  },
}))
