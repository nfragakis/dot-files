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
