.pragma library

// Evolution Data Server is a system OAuth broker. The helper process hands us
// one JSON line containing a live access token and its lifetime; all uncertain
// process output is decoded here before the rest of the auth manager sees it.

function parseToken(raw) {
  var value = null
  try { value = JSON.parse(String(raw || "")) } catch (e) { value = null }
  if (!value || typeof value !== "object")
    return { ok: false, error: "Evolution returned no Google session" }

  var token = String(value.accessToken || "").trim()
  if (token === "")
    return { ok: false, error: "Evolution returned no Google access token" }

  var expiresIn = Math.floor(Number(value.expiresIn))
  if (!isFinite(expiresIn) || expiresIn < 60) expiresIn = 3600

  return {
    ok: true,
    error: "",
    accessToken: token,
    expiresIn: expiresIn,
    scope: String(value.scope || "")
  }
}

// The account list is offered to a user who has not signed in to anything yet,
// so an unreadable line is an empty list rather than an error: Evolution not
// being installed is the ordinary case, and the page below still has the
// OAuth-client route to fall back to.
function parseAccounts(raw) {
  var value = null
  try { value = JSON.parse(String(raw || "")) } catch (e) { value = null }
  if (!value || typeof value !== "object") return []

  var listed = Array.isArray(value.accounts) ? value.accounts : []
  var accounts = []
  for (var i = 0; i < listed.length; i++) {
    var address = String(listed[i] || "").trim().toLowerCase()
    if (address.indexOf("@") < 0) continue
    if (accounts.indexOf(address) >= 0) continue
    accounts.push(address)
  }
  return accounts
}
