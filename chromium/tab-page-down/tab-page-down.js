const interactiveSelector = [
  "input",
  "select",
  "textarea",
  "[contenteditable]:not([contenteditable='false'])",
  "[role='combobox']",
  "[role='spinbutton']",
  "[role='textbox']",
].join(",");

function isInteractive(node) {
  return node instanceof Element && node.matches(interactiveSelector);
}

document.addEventListener(
  "keydown",
  (event) => {
    if (
      event.key !== "Tab" ||
      event.ctrlKey ||
      event.altKey ||
      event.metaKey ||
      event.isComposing ||
      event.defaultPrevented
    ) {
      return;
    }

    // Keep normal keyboard navigation whenever focus is in an editable
    // field. Elsewhere, including on links, Tab behaves like Page Down and
    // Shift+Tab behaves like Page Up.
    if (event.composedPath().some(isInteractive)) {
      return;
    }

    const activeElement = document.activeElement;
    if (
      activeElement &&
      activeElement !== document.body &&
      activeElement !== document.documentElement &&
      isInteractive(activeElement)
    ) {
      return;
    }

    event.preventDefault();
    const direction = event.shiftKey ? -1 : 1;
    window.scrollBy({
      top: direction * Math.max(1, window.innerHeight * 0.8),
      left: 0,
      behavior: "auto",
    });
  },
  true,
);
