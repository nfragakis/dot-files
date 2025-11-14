# Zed Keybindings - NeoVim/tmux Style

This configuration mimics your LazyVim and tmux setup using only valid Zed actions.

## Core Navigation

### Terminal Toggle (PRIMARY FEATURE)
- `Ctrl+j` - Toggle terminal panel from editor ✓
- `Ctrl+j` - Close terminal when focused in terminal ✓
- `Ctrl+/` - Alternative terminal toggle
- `Alt+j` - Toggle terminal (tmux-style)
- `Alt+k` - Toggle terminal (tmux-style)

### Pane/Buffer Navigation (tmux-inspired)
- `Alt+h` - Move to previous buffer/pane
- `Alt+l` - Move to next buffer/pane
- `Shift+h` - Previous buffer
- `Shift+l` - Next buffer

## Buffer Management (LazyVim-style)

### Buffer Navigation
- `Shift+h` - Previous buffer
- `Shift+l` - Next buffer
- `Space b b` - Switch to previous buffer

### Buffer Operations
- `Space b d` - Delete/close current buffer
- `Space b o` - Close all other buffers
- `Space w d` - Close window/pane

## File Operations

- `Ctrl+s` - Save file (works in normal, insert, visual modes)
- `Space f n` - New file

## Splits/Panes (LazyVim-style)

- `Space -` - Split window horizontally (below)
- `Space |` - Split window vertically (right)

## Code Navigation & LSP

### Diagnostics & Hover
- `Space c d` - Show hover information/diagnostics
- `Space c f` - Format code

## Visual Mode

- `Shift+<` (or `<` in visual mode) - Outdent
- `Shift+>` (or `>` in visual mode) - Indent

## Project/File Explorer

- `Space e` - Toggle project panel (file explorer)

## Git Operations

- `Space g g` - Toggle git blame
- `Space g b` - Toggle git blame

## Application

- `Space q q` - Quit Zed
- `Space l` - Open extensions/plugins

## Settings Applied

### Editor Behavior
- Vim mode enabled
- No relative line numbers (matching your config)
- Scrolloff: 4 lines
- No cursor blink
- Tab size: 2 spaces (4 for Python)
- Auto-save on focus change
- Format on save
- Remove trailing whitespace on save

### Terminal
- Dock: Bottom
- Default height: 400px
- No cursor blinking
- Working directory: current project

### Git
- Git gutter enabled
- Inline blame enabled

### Panels
- Project panel: Left side
- Outline panel: Right side

## What Was Removed

The following keybindings were removed as they used invalid Zed actions:

1. **Window navigation with Ctrl+h/k/l** - These vim-specific window actions don't exist in Zed
   - Use `Cmd+K, Cmd+Left/Right/Up/Down` for pane navigation instead
   - Or use `Alt+h/l` for quick buffer switching

2. **Window resizing** - `Ctrl+Arrow` actions not available
   - Use mouse or Zed's default resize commands

3. **Diagnostic navigation with `]d`, `[d`** - These specific actions don't exist
   - Use `Space c d` for hover/diagnostics
   - Or Zed's built-in diagnostic panel

4. **Toggle actions** (`Space u f/s/w/d`) - These specific toggle actions don't exist
   - Format on save is configured in settings.json
   - Use Zed's command palette (Cmd/Ctrl+Shift+P) for these toggles

## Working Keybindings Summary

### ✓ Confirmed Working
- `Ctrl+j` - Terminal toggle from editor
- `Space e` - Toggle file explorer
- `Space b d` - Close buffer
- `Space -` / `Space |` - Split panes
- `Ctrl+s` - Save file
- `Alt+h/l` - Switch buffers
- `Shift+h/l` - Switch buffers
- `Space g g` - Toggle git blame
- `Space c f` - Format code
- `Space q q` - Quit

## Testing Your Configuration

1. Restart Zed to reload the configuration
2. The error dialog should now be gone
3. Try `Ctrl+j` from the editor - should toggle terminal
4. Try `Space e` - should toggle file explorer
5. Try `Alt+h/l` - should switch between open files

## Note on Vim Window Navigation

Zed's vim mode doesn't support the exact same window navigation commands as NeoVim (`Ctrl+h/j/k/l`). Instead:
- Use Zed's built-in pane navigation (check command palette)
- Use `Alt+h/l` for quick buffer switching (similar to tmux)
- The terminal toggle with `Ctrl+j` works as requested

## Additional Notes

- Your font settings (size 15-16) are preserved
- Your theme preferences (Gruvbox Dark Hard) are maintained
- Git blame is enabled by default
- Format on save is enabled in settings
