local theme = require("theme")

hl.config({
  general = {
    gaps_in = 5,
    gaps_out = 10,
    border_size = 2,
    col = {
      active_border = { colors = { theme.accent, theme.magenta }, angle = 45 },
      inactive_border = theme.muted,
    },
    layout = "dwindle",
    resize_on_border = false,
    allow_tearing = true,                -- games opt in via `immediate` rules
  },

  decoration = {
    rounding = 0,
    shadow = {
      enabled = true,
      range = 2,
      render_power = 3,
      color = theme.shadow,
    },
    blur = {
      enabled = true,
      size = 3,
      passes = 1,
    },
  },

  animations = { enabled = true },

  dwindle = {
    preserve_split = true,
    force_split = 2,
  },

  misc = {
    disable_hyprland_logo = true,
    disable_splash_rendering = true,
    focus_on_activate = true,
    vrr = 2,
  },
})

-- Appearance → Glass (glass_* and app_opacity from ~/.config/fw13/theme/hypr.lua; all off by default): the chosen
-- see-through layers get a strong, slightly vivid blur; App windows makes every window a little see-through
-- (fullscreen stays solid).
local glass = {}
if theme.glass_bar == true then table.insert(glass, "waybar") end
if theme.glass_menus == true then table.insert(glass, "launcher|notifications") end
if theme.glass_panels == true then table.insert(glass, "fw-.+") end
if #glass > 0 or theme.glass_apps == true then
  hl.config({ decoration = { blur = { size = 8, passes = 3, vibrancy = 0.3, noise = 0.015, popups = true } } })
end
if #glass > 0 then
  hl.layer_rule({
    name = "fw13-glass",
    match = { namespace = "^(" .. table.concat(glass, "|") .. ")$" },
    blur = true,
    ignore_alpha = 0.1,
  })
end
if theme.glass_apps == true and type(theme.app_opacity) == "number" and type(theme.app_opacity_inactive) == "number" then
  hl.config({ decoration = { active_opacity = theme.app_opacity, inactive_opacity = theme.app_opacity_inactive } })
  -- Terminals are see-through on their own (Appearance → Terminal → Opacity): don't stack the two.
  hl.window_rule({ name = "fw13-glass-terminals", match = { class = "^(kitty|com\\.mitchellh\\.ghostty)$" },
                   opacity = "1.0 override 1.0 override" })
end

hl.curve("easeOutQuint", { type = "bezier", points = { { 0.23, 1 }, { 0.32, 1 } } })
hl.animation({ leaf = "windows",    enabled = true, speed = 4.8, bezier = "easeOutQuint" })
hl.animation({ leaf = "fade",       enabled = true, speed = 3,   bezier = "easeOutQuint" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 2,   bezier = "easeOutQuint", style = "slide" })
