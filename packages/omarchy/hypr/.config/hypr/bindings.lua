-- Keep only your personal keybinding overrides here. Add new bindings or
-- unbind defaults before replacing them.

-- See current bindings and descriptions:
--   omarchy menu keybindings --print

-- To disable every Omarchy default binding, set this in
-- ~/.config/hypr/hyprland.lua before require("default.hypr.omarchy"), then add
-- only the bindings you want below:
--   omarchy_default_bindings = false

-- To disable all preinstalled app/webapp bindings, set:
--   omarchy_preinstalled_bindings = false

-- Add a new binding.
-- o.bind("SUPER + SHIFT + R", "SSH", "alacritty -e ssh your-server")

-- Change an existing binding by unbinding it first, then binding the key again.
-- This example changes SUPER+SPACE from the launcher to the Omarchy root menu.
-- hl.unbind("SUPER + SPACE")
-- o.bind("SUPER + SPACE", "Omarchy menu", "omarchy-menu toggle root")

-- Disable a default binding without replacing it.
-- hl.unbind("SUPER + SHIFT + B")

-- Reserve SUPER+TAB for Hyprshell (Omarchy normally uses it for Next workspace).
-- To restore Omarchy's shortcut later, remove or comment out this line.
hl.unbind("SUPER + TAB")

-- 1Password Quick Access (Wayland requires a compositor-level shortcut).
o.bind("CTRL + SHIFT + SPACE", "1Password Quick Access", "1password --quick-access")

-- T3 Code snapshots use the app's global shortcut for window capture.
o.bind("CTRL + SHIFT + 2", "T3 Code capture window", hl.dsp.global("com.t3tools.T3Code:capture-window"))

-- Send the native Select All shortcut to the focused surface. Ghostty uses
-- Ctrl+Shift+A, while conventional GUI applications use Ctrl+A.
local function send_select_all(mods)
  hl.dispatch(hl.dsp.send_key_state({ mods = mods, key = "A", state = "down" }))

  hl.timer(function()
    hl.dispatch(hl.dsp.send_key_state({ mods = mods, key = "A", state = "up" }))
  end, { timeout = 50, type = "oneshot" })
end

local function active_window_is_terminal()
  local window = hl.get_active_window()

  for _, tag in ipairs(window and window.tags or {}) do
    if tag:gsub("%*$", "") == "terminal" then
      return true
    end
  end

  return false
end

-- Remove a future Omarchy default before preserving this personal binding.
hl.unbind("SUPER + A")
o.bind("SUPER + A", "Universal select all", function()
  send_select_all(active_window_is_terminal() and "CTRL + SHIFT" or "CTRL")
end)

-- Omarchy assigns raw Voxtype dictation to SUPER+CTRL+X and F9 by default.
-- Override them so the primary shortcuts use Groq cleanup.
hl.unbind("SUPER + CTRL + X")
hl.unbind("F9")
o.bind("SUPER + CTRL + X", "Toggle dictation with Groq cleanup", "voxtype record toggle --profile groq_cleanup")
o.bind("F9", "Start dictation with Groq cleanup (push-to-talk)", "voxtype record start --profile groq_cleanup")
o.bind("F9", "Stop dictation with Groq cleanup (push-to-talk)", "voxtype record stop", { release = true })

-- Keep raw dictation available on the secondary shortcuts.
o.bind("SUPER + CTRL + SHIFT + X", "Toggle raw dictation", "voxtype record toggle")
o.bind("F10", "Start raw dictation (push-to-talk)", "voxtype record start")
o.bind("F10", "Stop raw dictation (push-to-talk)", "voxtype record stop", { release = true })

-- Panels from the blizl.voxtype-osd Quickshell HUD.
o.bind("SUPER + E", "VoxType engine picker", "mkdir -p $XDG_RUNTIME_DIR/voxtype && touch $XDG_RUNTIME_DIR/voxtype/engine-picker.flag")
o.bind("SUPER + M", "VoxType meeting controls", "mkdir -p $XDG_RUNTIME_DIR/voxtype && touch $XDG_RUNTIME_DIR/voxtype/meeting-controls.flag")

-- Logitech MX Keys examples:
-- o.bind("SUPER + SHIFT + S", nil, "omarchy-capture-screenshot")
-- o.bind("SUPER + H", nil, "voxtype record toggle")
-- o.bind("SUPER + PERIOD", nil, "omarchy-shell shell toggle omarchy.emojis")

hl.unbind("SUPER + SHIFT + M") -- previously: Music
o.bind("SUPER + SHIFT + M", "OmaSpotify", "omarchy shell -q io.github.jeremylanger.omaspotify.player togglePlayer")
