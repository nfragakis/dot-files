-- Upstream is installed by install-tern-clipboard.py, outside this checkout.
dofile(os.getenv("HOME") .. "/src/forge/omarchy/hypr/tern-nav.lua")

-- Preserve the personal Screenshot fallback instead of upstream's Google Photos.
local tern_browser = tern_nav.binds["SUPER + SHIFT + P"]
local function browser_or_screenshot()
  if tern_nav.handles(hl.get_active_window()) then
    tern_browser()
  else
    hl.dispatch(hl.dsp.exec_cmd("omarchy-capture-screenshot"))
  end
end
hl.unbind("SUPER + SHIFT + P")
tern_nav.binds["SUPER + SHIFT + P"] = browser_or_screenshot
o.bind("SUPER + SHIFT + P", "New Tern browser, else Screenshot", browser_or_screenshot)
