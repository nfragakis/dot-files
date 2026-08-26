# Tab Page Down

A small Chromium extension that makes `Tab` scroll down and `Shift+Tab` scroll
up by 80% of the viewport on normal webpage content. The remaining 20% overlap
helps preserve the reader's place. Both retain their usual focus-navigation
behavior in text fields, selects, and editable content. Links and other page
controls do not retain normal Tab navigation. Modified shortcuts such as
`Ctrl+Tab` and `Alt+Tab` are unchanged.

## Install

1. Open `chrome://extensions` in Chromium.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select this `chromium/tab-page-down` directory.

Chromium does not allow extensions to run on protected browser pages such as
`chrome://settings`. Some browser-managed pages, including the built-in PDF
viewer and extension store, may also keep their native Tab behavior.
