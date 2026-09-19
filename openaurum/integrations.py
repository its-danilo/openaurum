"""Where OpenAurum meets the desktop: theme palette, wallpaper and screen mode.

Generic Linux: ~/.config/openaurum/config.conf (all keys optional)

  palette    = #ff3c00, #ff0080, #0080ff   # colors of the "Do tema" scenes, first = accent
  wallpaper  = ~/Imagens/wall.jpg           # picture of the "Wallpaper" scene
  mode       = Static                       # what `openaurum-cli theme` applies
  brightness = 10
  speed      = 1
  color      = #00aaff                      # or: rgb

calOS (the author's Hyprland dotfiles, detected by ~/.config/calos/current/theme):
the palette comes from the theme's waybar.css accent + alacritty colors, the
theme may carry a keyboard.conf with the keys above, and the wallpaper follows
the monitor under the mouse. Keys set in config.conf win over calOS.

Screen mode (Night / Cave) comes from `openaurum-cli screen normal|night|cave`
($XDG_RUNTIME_DIR/openaurum-screen); on calOS, from calos-screen-mode too.
"""

import os
import re
import subprocess

from openaurum import paths
from openaurum.protocol import hex_to_hsv, mode_number, vivid

CALOS_THEME = os.path.expanduser("~/.config/calos/current/theme")
DEFAULT_PALETTE = ["#ff3c00", "#ff0080", "#8000ff", "#0080ff", "#00ffc0", "#ffd000"]


def calos():
    return os.path.isdir(CALOS_THEME)


def _read(path):
    try:
        with open(os.path.expanduser(path)) as f:
            return f.read()
    except OSError:
        return ""


def read_conf(path):
    """key = value lines; '#' starts a comment unless it is a #rrggbb color."""
    conf = {}
    for line in _read(path).splitlines():
        line = re.sub(r"(^|\s)#(?![0-9a-fA-F]{6}\b).*", "", line)
        if "=" in line:
            k, v = (x.strip().strip("'\"") for x in line.split("=", 1))
            conf[k.lower()] = v
    return conf


def config():
    return read_conf(paths.CONFIG)


def _calos_palette():
    """[(name, '#rrggbb')]: waybar accent, then alacritty's normal colors."""
    out = []
    m = re.search(r"define-color\s+accent\s+#([0-9a-fA-F]{6})", _read(f"{CALOS_THEME}/waybar.css"))
    if m:
        out.append(("accent", "#" + m.group(1).lower()))
    section = None
    for line in _read(f"{CALOS_THEME}/alacritty.toml").splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.replace(" ", "")
        elif section == "[colors.normal]":
            m = re.match(r"(\w+)\s*=.*?(?:#|0x)([0-9a-fA-F]{6})", line)
            if m and m.group(1) in ("red", "green", "yellow", "blue", "magenta", "cyan"):
                out.append((m.group(1), "#" + m.group(2).lower()))
    return out


def theme_palette():
    """[(name, '#rrggbb')], accent first."""
    colors = re.findall(r"#[0-9a-fA-F]{6}", config().get("palette", ""))
    if not colors and calos():
        pal = _calos_palette()
        if pal:
            return pal
    colors = colors or DEFAULT_PALETTE
    return [("accent" if i == 0 else f"color{i}", c.lower()) for i, c in enumerate(colors)]


def theme_color():
    """The accent made vivid. A greyish accent (graphite...) has no hue to
    keep: then the most saturated color of the palette."""
    pal = theme_palette()
    name, color = pal[0]
    if name != "accent" or hex_to_hsv(color)[1] < 20:
        color = max(pal, key=lambda nc: hex_to_hsv(nc[1])[1])[1]
    return vivid(color)


def theme_settings():
    """What `openaurum-cli theme` applies: keyboard.conf of the calOS theme and/or
    config.conf (mode / brightness / speed / color = #rrggbb or rgb), with the
    color defaulting to theme_color(). An explicit color is used exactly as written."""
    conf = read_conf(f"{CALOS_THEME}/keyboard.conf") if calos() else {}
    conf.update({k: v for k, v in config().items()
                 if k in ("mode", "brightness", "speed", "color")})
    out = {}
    if "mode" in conf:
        out["mode"] = mode_number(conf["mode"])
    for k in ("brightness", "speed"):
        if k in conf:
            out[k] = int(conf[k])
    if conf.get("color", "").lower() == "rgb":
        out["rgb"] = True
    else:
        out["color"] = conf.get("color") or theme_color()
    return out


def wallpaper_path():
    """Picture for the "Wallpaper" scene, or None (the scene then falls back
    to the theme gradient)."""
    p = config().get("wallpaper")
    if p:
        p = os.path.expanduser(p)
        return p if os.path.exists(p) else None
    if not calos():
        return None
    try:  # calOS: the monitor under the mouse (the one SUPER+CTRL+B changes)
        name = subprocess.run(["calos-cursor-output"], capture_output=True, text=True,
                              timeout=2).stdout.strip()
        p = os.path.expanduser(f"~/.local/state/calos/background/{name}")
        if name and os.path.exists(p):
            return os.path.realpath(p)
    except Exception:
        pass
    p = os.path.expanduser("~/.config/calos/current/background")
    return os.path.realpath(p) if os.path.exists(p) else None


SCREEN_MODES = ("normal", "night", "cave")


def screen_mode():
    for p in (paths.SCREEN, os.path.join(paths.RUNTIME_DIR, "calos-screen-mode")):
        try:
            with open(p) as f:
                mode = f.read().strip()
            if mode in SCREEN_MODES:
                return mode
        except OSError:
            continue
    return "normal"


def set_screen_mode(mode):
    if mode not in SCREEN_MODES:
        raise ValueError(f"screen mode {mode!r} ({' / '.join(SCREEN_MODES)})")
    with open(paths.SCREEN, "w") as f:
        f.write(mode + "\n")
