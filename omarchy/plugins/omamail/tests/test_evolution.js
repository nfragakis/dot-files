const assert = require("assert")
const { load, deepEqual } = require("./load")

const evolution = load("providers/Evolution.js")

deepEqual(evolution.parseToken(""), {
  ok: false,
  error: "Evolution returned no Google session"
})
deepEqual(evolution.parseToken("not json"), {
  ok: false,
  error: "Evolution returned no Google session"
})
deepEqual(evolution.parseToken('{"expiresIn":120}'), {
  ok: false,
  error: "Evolution returned no Google access token"
})
deepEqual(evolution.parseToken('{"accessToken":"token","expiresIn":120,"scope":"mail"}'), {
  ok: true,
  error: "",
  accessToken: "token",
  expiresIn: 120,
  scope: "mail"
})
assert.strictEqual(
  evolution.parseToken('{"accessToken":"token","expiresIn":0}').expiresIn,
  3600
)

deepEqual(evolution.parseAccounts(""), [])
deepEqual(evolution.parseAccounts("not json"), [])
deepEqual(evolution.parseAccounts('{"accounts":[]}'), [])
deepEqual(evolution.parseAccounts('{"accounts":["you@gmail.com"]}'), ["you@gmail.com"])
// A Google collection is several sources sharing one address.
deepEqual(
  evolution.parseAccounts('{"accounts":["You@Gmail.com","you@gmail.com"]}'),
  ["you@gmail.com"]
)
// Anything without an address is a source, not a mailbox.
deepEqual(evolution.parseAccounts('{"accounts":["system-proxy",""]}'), [])

console.log("test_evolution.js ok")
