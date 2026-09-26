"""Scenes for the Pichau Aurum V60: per-key pictures computed on the PC and
written through CustomLightning (protocol.Keyboard.push), plus overlays
that react to the system (Colemak-DH, game mode, Cave, typing heatmap).

Layers, bottom to top:
  base scene (the user's pick)  <  colemak / game / heat overlays  <  brightness

Brightness (0-10) is done here, by dimming every key's color: CustomLightning
ignores the keyboard's own BR byte. The state keeps the full colors (paint too);
only the keyboard gets the dimmed ones, so one change rewrites every lit key.

The per-key table most likely lives in flash (it survived a factory reset), so
nothing here animates: the keyboard is only rewritten on events (theme,
wallpaper, layout, Game Mode, screen mode, a click in the app), and push()
only sends the keys that change. Writes are counted in paths.WRITES.

State: paths.SCENES (~/.local/state/openaurum/scenes.json)
  active    scenes drive the keyboard (CustomLightning)
  base      scene name        paint  {key: color} for "paint" (my painting)
  overlays  [names] on now    prev   effect to go back to when nothing is shown
  auto      {wallpaper, colemak, game, screen}: which events may take over
  cave_prev {mode, static}: what Cave Mode replaced (see _cave)
  brightness 0-10 (10 = the colors as they are)

Cave Mode (screen mode "cave") doesn't go through the per-key table: it
switches to Static in one color CAVE_COLOR (dark by its own V: brightness
is ignored in one color), 1-2 mode writes, and puts
back Static's own settings and the previous mode afterwards. Events during Cave
only update the state. Night Mode leaves the keyboard as in normal mode (a warm
filter over the scenes looked wrong on the LEDs).
"""

import colorsys
import json
import math
import os
import re

from openaurum import integrations, paths
from openaurum import protocol as kb
from openaurum.integrations import screen_mode

STATE = paths.SCENES
HEAT = paths.HEAT
W, H = 15.0, 5.0
GEO = kb.geometry()

DEFAULT = {
    "active": False, "base": "theme-gradient", "paint": {}, "overlays": [], "prev": None,
    "cave_prev": None, "brightness": kb.MONO_STEPS,
    "auto": {"wallpaper": True, "colemak": True, "game": True, "screen": True},
}


# --- colors --------------------------------------------------------------------

def rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hexc(r, g, b):
    return "#%02x%02x%02x" % tuple(round(max(0, min(1, v)) * 255) for v in (r, g, b))


def hsv(h, s, v):
    return hexc(*colorsys.hsv_to_rgb(h % 1.0, s, v))


def mix(a, b, t):
    a, b = rgb(a), rgb(b)
    return hexc(*(x + (y - x) * t for x, y in zip(a, b)))


def scale(c, f):
    return hexc(*(v * f for v in rgb(c)))


def ramp(stops, t):
    """Color at t (0-1) along evenly spaced stops."""
    if len(stops) == 1:
        return stops[0]
    t = max(0.0, min(1.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    return mix(stops[i], stops[i + 1], t - i)


def led(c, sat=1.35, floor=0.45):
    """Make a color read well on LEDs: more saturation, never dim."""
    h, s, v = colorsys.rgb_to_hsv(*rgb(c))
    return hsv(h, min(1, s * sat), max(floor, v))


def noise(key, seed=0):
    """Deterministic 0-1 per key: scenes look the same every time."""
    # own hash: Python's hash() changes every run (PYTHONHASHSEED)
    x = sum((i + 1) * ord(ch) for i, ch in enumerate(f"{key}{seed}")) * 2654435761 & 0xFFFFFFFF
    return (x % 1000) / 999


def theme_stops():
    """Theme palette made LED-friendly, accent first."""
    out = []
    for _, c in integrations.theme_palette():
        v = led(c, 1.6, 0.7)
        if v not in out:
            out.append(v)
    return out or ["#ff5500", "#00aaff"]


# --- base scenes -----------------------------------------------------------------
# each: fn() -> {key: color}; SCENES[name] = (title, group, fn)

def per_key(fn):
    return {k: fn(k, x / W, y / H) for k, (x, y) in GEO.items()}


def s_theme_gradient():
    stops = theme_stops()
    return per_key(lambda k, x, y: ramp(stops, x))


def s_theme_waves():
    stops = theme_stops()
    return per_key(lambda k, x, y: ramp(stops, 0.5 + 0.5 * math.sin(2 * math.pi * (x * 1.2 + y * 0.35))))


GROUPS = {
    "letters": [k for k in GEO if re.fullmatch(r"A[DCB]\d\d", k)],
    "numbers": [k for k in GEO if k.startswith("AE")],
    "special": ["ESC", "BKSP", "RTRN", "TAB", "CAPS"],
}


def s_theme_groups():
    stops = theme_stops()
    accent = stops[0]
    h, s, v = colorsys.rgb_to_hsv(*rgb(accent))
    comp = hsv(h + 0.5, s, v)
    other = stops[1] if len(stops) > 1 else mix(accent, "#ffffff", 0.5)
    out = {}
    for k in GEO:
        if k in GROUPS["letters"]:
            out[k] = accent
        elif k in GROUPS["numbers"]:
            out[k] = other
        elif k in GROUPS["special"]:
            out[k] = "#ffffff"
        else:
            out[k] = comp
    return out


def s_wallpaper():
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    path = integrations.wallpaper_path()
    if not path:
        return s_theme_gradient()
    pb = GdkPixbuf.Pixbuf.new_from_file(path)
    iw, ih = pb.get_width(), pb.get_height()
    # cover-crop the middle band to the board's 3:1
    cw, ch = (iw, iw / 3) if iw / ih < 3 else (ih * 3, ih)
    cx, cy = (iw - cw) / 2, (ih - ch) / 2
    gw, gh = 60, 20
    small = pb.new_subpixbuf(int(cx), int(cy), int(cw), int(ch)).scale_simple(
        gw, gh, GdkPixbuf.InterpType.BILINEAR)
    px, stride, n = small.get_pixels(), small.get_rowstride(), small.get_n_channels()

    def sample(x, y):
        gx, gy = min(gw - 1, int(x * gw)), min(gh - 1, int(y * gh))
        acc = [0, 0, 0]
        cnt = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xx, yy = min(gw - 1, max(0, gx + dx)), min(gh - 1, max(0, gy + dy))
                o = yy * stride + xx * n
                for i in range(3):
                    acc[i] += px[o + i]
                cnt += 1
        return hexc(*(a / cnt / 255 for a in acc))

    return per_key(lambda k, x, y: led(sample(x, y), 1.8, 0.55))


def s_aurora():
    def f(k, x, y):
        band = 0.5 + 0.5 * math.sin(2 * math.pi * (x * 1.1) + 1.3)
        glow = max(0.0, 1 - abs(y - (0.25 + 0.45 * band)) * 2.6)
        base = mix("#05051a", "#1a0a40", y)
        col = ramp(["#00ffa0", "#00e0ff", "#a040ff"], x)
        return mix(base, col, min(1, glow * 1.2))
    return per_key(f)


def s_sunset():
    def f(k, x, y):
        sky = ramp(["#3a0ca3", "#b5179e", "#ff4d6d", "#ff9e00"], y)
        d = math.hypot((x - 0.5) * 3, (y - 1.0) * 1.2)
        return mix(sky, "#ffd000", max(0, 1 - d * 1.4))
    return per_key(f)


def s_synthwave():
    def f(k, x, y):
        if y < 0.55:
            return ramp(["#ff00c8", "#ff5a00"], y / 0.55)
        return "#00f0ff" if (int(x * 15) % 3 == 0 or k in ("SPCE", "LCTL", "RCTL")) else "#2a0060"
    return per_key(f)


def s_ocean():
    def f(k, x, y):
        c = ramp(["#00ffe0", "#0090ff", "#0020a0", "#000840"], y)
        return mix(c, "#ffffff", 0.7) if y < 0.2 and noise(k, 3) > 0.6 else c
    return per_key(f)


def s_forest():
    def f(k, x, y):
        c = ramp(["#a0ff40", "#20c020", "#006020", "#3a2000"], y)
        return mix(c, "#ffe060", 0.8) if noise(k, 5) > 0.93 else c  # fireflies
    return per_key(f)


def s_ember():
    def f(k, x, y):
        n = noise(k, 7)
        return ramp(["#200000", "#a01000", "#ff4000", "#ffb000"], (y * 0.7 + n * 0.5))
    return per_key(f)


def s_matrix():
    def f(k, x, y):
        col = int(x * 15)
        drop = noise(f"col{col}", 11)
        d = y - drop
        if -0.05 < d < 0.12:
            return "#c0ffc0"
        if -0.5 < d <= -0.05:
            return scale("#00ff40", 1 + d * 1.6)
        return "#001a06"
    return per_key(f)


def s_brasil():
    def f(k, x, y):
        X, Y = x * W, y * H
        if math.hypot((X - 7.5) / 2.6, (Y - 2.5) / 1.35) < 1:
            return "#ffffff" if abs(Y - 2.3) < 0.45 and abs(X - 7.5) < 2.3 else "#002776"
        if abs(X - 7.5) / 6.6 + abs(Y - 2.5) / 2.6 < 1:
            return "#ffdf00"
        return "#009c3b"
    return per_key(f)


def s_paint():
    return dict(load().get("paint") or {})


SCENES = {
    "theme-gradient": ("Degradê do tema", "Tema", s_theme_gradient),
    "theme-waves": ("Ondas do tema", "Tema", s_theme_waves),
    "theme-groups": ("Grupos do tema", "Tema", s_theme_groups),
    "wallpaper": ("Wallpaper", "Tema", s_wallpaper),
    "aurora": ("Aurora", "Arte", s_aurora),
    "sunset": ("Pôr do sol", "Arte", s_sunset),
    "synthwave": ("Synthwave", "Arte", s_synthwave),
    "ocean": ("Oceano", "Arte", s_ocean),
    "forest": ("Floresta", "Arte", s_forest),
    "ember": ("Brasa", "Arte", s_ember),
    "matrix": ("Matrix", "Arte", s_matrix),
    "brasil": ("Brasil", "Arte", s_brasil),
    "paint": ("Minha pintura", "Minha", s_paint),
}
THEMED = {"theme-gradient", "theme-waves", "theme-groups", "wallpaper"}


# --- overlays ----------------------------------------------------------------------

# one pure LED color per finger, the same on both hands (pastels and orange vs
# yellow looked alike on the keyboard): pinky red, ring green, middle blue, index magenta
FINGER_COLORS = ["#ff0000", "#00ff00", "#0030ff", "#ff00ff"]
FINGERS = FINGER_COLORS + FINGER_COLORS[::-1]


def finger(key):
    """0-7 left pinky .. right pinky for Colemak-DH ISO (angle mod).
    The bottom row has the angle mod: left hand one key to the left, so the pinky
    takes \\ (z), ring AB01 (x), middle AB02 (c), index AB03-AB05 (d v \\)."""
    m = re.fullmatch(r"A([EDC])(\d\d)", key)
    if m:
        return [0, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 7, 7][min(12, int(m.group(2)))]
    m = re.fullmatch(r"AB(\d\d)", key)
    if m:
        return [None, 1, 2, 3, 3, 3, 4, 4, 5, 6, 7, 7][int(m.group(1))]
    return {"LSGT": 0, "ESC": 0, "TAB": 0, "CAPS": 0, "LFSH": 0, "LCTL": 0,
            "BKSP": 7, "RTRN": 7, "BKSL": 7, "RTSH": 7, "RCTL": 7, "FN": 7}.get(key)


def o_colemak(base):
    out = {}
    for k in GEO:
        f = finger(k)
        home = re.fullmatch(r"AC0[1-4]|AC0[7-9]|AC10", k)
        if f is None:
            out[k] = "#101010"
        else:
            out[k] = FINGERS[f] if home else scale(FINGERS[f], 0.3)
    out["SPCE"] = "#606060"
    return out


GAME_HOT = {"AD02", "AC01", "AC02", "AC03"}  # W A S D
GAME_WARM = {"AD01", "AD03", "AD04", "AC04", "SPCE", "LFSH", "LCTL", "TAB",
             "AB01", "AB02", "AB03", "AE01", "AE02", "AE03", "AE04", "AE05", "ESC"}


def o_game(base):
    out = {}
    for k in GEO:
        if k in GAME_HOT:
            out[k] = "#ff1010"
        elif k in GAME_WARM:
            out[k] = "#ff6000"
        else:
            out[k] = scale(ramp(["#300400", "#140200"], noise(k, 13)), 1)
    return out


def load_heat():
    try:
        with open(HEAT) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


HEAT_STEPS = ["#000814", "#0030ff", "#00c0ff", "#00ff40", "#ffff00", "#ff6000", "#ff0000"]


def heat_level(count, top):
    """0-6: few steps, so a new count rarely changes a key's color (flash)."""
    if not top or not count:
        return 0
    return 1 + min(5, int((count / top) ** 0.5 * 6))


def o_heat(base):
    heat = load_heat()
    top = max(heat.values(), default=0)
    return {k: HEAT_STEPS[heat_level(heat.get(k, 0), top)] for k in GEO}


OVERLAYS = {  # name: (title, fn); later in this dict = on top
    "colemak": ("Colemak que ensina", o_colemak),
    "game": ("Modo de jogo", o_game),
    "heat": ("Mapa de calor", o_heat),
}


def dim(colors, level):
    """Brightness level 0-10: same curve as the one-color modes (MONO_LEVELS[16])."""
    if level >= kb.MONO_STEPS:
        return colors
    f = kb.mono_levels(kb.CUSTOM)[level] / 255
    return {k: scale(c, f) for k, c in colors.items()}


def undim(colors, level):
    """Back to full colors, as far as 8 bits allow (the keyboard holds dimmed ones)."""
    f = kb.mono_levels(kb.CUSTOM)[level] / 255
    if level >= kb.MONO_STEPS or not f:
        return colors
    return {k: scale(c, 1 / f) for k, c in colors.items()}


def shown(s):
    """Full colors of what CustomLightning shows while scenes are idle: the
    last picture they left there was dimmed at the current brightness."""
    return undim(s.kb().key_colors(), s.st["brightness"])


# the same in every theme: theme hues this dark still hurt the user's eyes, red doesn't
CAVE_COLOR = "#100000"


# --- state + apply ---------------------------------------------------------------

def load():
    try:
        with open(STATE) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    out = json.loads(json.dumps(DEFAULT))
    out.update({k: v for k, v in st.items() if k in DEFAULT})
    out["auto"] = {**DEFAULT["auto"], **st.get("auto", {})}
    out["overlays"] = [o for o in out["overlays"] if o in OVERLAYS]  # e.g. the old "binds"
    return out


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".tmp", "w") as f:
        json.dump(st, f, indent=1)
    os.replace(STATE + ".tmp", STATE)


def render_scene(name):
    return SCENES.get(name, SCENES["theme-gradient"])[2]()


def render(st=None, dimmed=True):
    """Colors the keyboard should show now, or None when scenes are idle.
    dimmed=False: before the brightness (app preview)."""
    st = st or load()
    overlays = [o for o in OVERLAYS if o in st["overlays"]]
    if not st["active"] and not overlays:
        return None
    colors = render_scene(st["base"]) if st["active"] else {k: "#000000" for k in GEO}
    for o in overlays:
        colors = OVERLAYS[o][1](colors)
    return dim(colors, st["brightness"]) if dimmed else colors


class _Session:
    """Lock + state + keyboard for one change: hooks run in parallel (Game Mode
    also switches the layout), so load-modify-save-write happens under one lock."""

    def __init__(self, k=None):
        self.k, self.own = k, k is None

    def __enter__(self):
        kb.acquire()  # the keyboard's own lock: state and device change together
        self.st = load()
        return self

    def kb(self):
        if self.k is None:
            self.k = kb.Keyboard()
        return self.k

    def __exit__(self, *exc):
        if self.own and self.k is not None:
            self.k.__exit__()
        kb.release()


def _cave(s):
    """Cave Mode on/off. True while in Cave (nothing else may write)."""
    st, k = s.st, s.kb()
    want = st["auto"].get("screen") and screen_mode() == "cave"
    if want:
        if not st["cave_prev"]:
            mode = k.current_mode()
            st["cave_prev"] = {"mode": mode, "static": k.stored(1)}
            save(st)
        # full level: in one color the V is the brightness, and #100000 already is dark;
        # remember=False keeps the user's own Static level/color for afterwards
        k.apply(mode=1, brightness=kb.MONO_STEPS, color=CAVE_COLOR, remember=False)
        return True
    if st["cave_prev"]:
        prev = st["cave_prev"]
        k.restore(prev["static"])  # Static exactly as it was (this also selects Static)
        if prev["mode"] != 1:
            k.apply(mode=prev["mode"])
        st["cave_prev"] = None
        save(st)
    return False


def _refresh(s):
    """Bring the keyboard in line with s.st. Returns keys written."""
    st = s.st
    if _cave(s):
        return 0
    colors = render(st)
    k = s.kb()
    mode = k.current_mode()
    if colors is None:
        if mode == kb.CUSTOM and st.get("prev") is not None:
            k.apply(mode=st["prev"])
            st["prev"] = None
            save(st)
        return 0
    if mode != kb.CUSTOM:
        st["prev"] = mode
        save(st)
        k.apply(mode=kb.CUSTOM)
    return k.push(colors)


def refresh(k=None):
    with _Session(k) as s:
        return _refresh(s)


def set_scene(name, k=None):
    if name not in SCENES:
        raise ValueError(f"unknown scene {name!r}")
    with _Session(k) as s:
        if not s.st["paint"] and name != "paint":
            # first scene: keep what was painted by hand (app / Pichau) as "Minha pintura"
            s.st["paint"] = s.kb().key_colors()
        s.st["active"], s.st["base"] = True, name
        save(s.st)
        return _refresh(s)


def stop(k=None):
    with _Session(k) as s:
        s.st["active"], s.st["overlays"] = False, []
        save(s.st)
        return _refresh(s)


def overlay(name, on, k=None, auto=None):
    """Turn an overlay on/off. auto = the st['auto'] switch that must allow it
    (events from hooks), None for the user's own request."""
    if name not in OVERLAYS:
        raise ValueError(f"unknown overlay {name!r}")
    with _Session(k) as s:
        st = s.st
        if on and auto and not st["auto"].get(auto, True):
            return 0
        ov = [o for o in st["overlays"] if o != name] + ([name] if on else [])
        if ov == st["overlays"]:
            return 0
        st["overlays"] = ov
        save(st)
        return _refresh(s)


def event(what):
    """Hooks: theme, wallpaper, screen. Re-render only when it matters."""
    with _Session() as s:
        st = s.st
        if what == "heat" and "heat" not in st["overlays"]:
            return 0
        if what == "wallpaper" and not (st["active"] and st["base"] == "wallpaper"
                                        and st["auto"].get("wallpaper")):
            return 0
        if what == "theme" and not ((st["active"] and st["base"] in THEMED) or st["overlays"]):
            return 0
        cave = st["cave_prev"] or (st["auto"].get("screen") and screen_mode() == "cave")
        if what == "screen" and not cave:  # normal <-> night: nothing changes here
            return 0
        return _refresh(s)


def detach():
    """The user picked a built-in effect (or painted by hand): scenes let go,
    and Cave Mode too (Static gets its own settings back first)."""
    with _Session() as s:
        if s.st["cave_prev"]:
            s.kb().restore(s.st["cave_prev"]["static"])
        s.st.update(active=False, overlays=[], prev=None, cave_prev=None)
        save(s.st)


def set_brightness(level, k=None):
    """Scenes' brightness 0-10. With scenes idle in CustomLightning, what the
    keyboard shows becomes "Minha pintura" so there is something to dim; in
    another effect only the level is kept (for the next scene)."""
    if not 0 <= level <= kb.MONO_STEPS:
        raise ValueError(f"brightness {level} (0-{kb.MONO_STEPS})")
    with _Session(k) as s:
        st = s.st
        idle = not st["active"] and not st["overlays"]
        if idle and (st["cave_prev"] or s.kb().current_mode() != kb.CUSTOM):
            st["brightness"] = level  # nothing of ours on the keyboard: for next time
            save(st)
            return 0
        if idle:
            st.update(paint=shown(s), active=True, base="paint")
        st["brightness"] = level
        save(st)
        return _refresh(s)


def paint_keys(colors, k=None):
    """Hand painting (app): the painted keys over the current picture (full
    colors, no overlays) become "Minha pintura", drawn at the current brightness."""
    with _Session(k) as s:
        st = s.st
        full = render_scene(st["base"]) if st["active"] else shown(s)
        st.update(paint={**full, **colors}, base="paint", active=True)
        save(st)
        return _refresh(s)


def adopt_paint(colors):
    """Hand painting in the app becomes the "paint" scene, so later events
    (theme, screen mode...) redraw it instead of a scene."""
    with _Session() as s:
        s.st.update(paint=dict(colors), base="paint", active=True)
        save(s.st)


def set_auto(name, on):
    with _Session() as s:
        s.st["auto"][name] = bool(on)
        save(s.st)


def save_paint(colors):
    with _Session() as s:
        s.st["paint"] = dict(colors)
        save(s.st)


# more art (art.py), shown between "Arte" and "Minha pintura"
from openaurum import art  # noqa: E402

SCENES = {**{k: v for k, v in SCENES.items() if v[1] != "Minha"}, **art.SCENES,
          **{k: v for k, v in SCENES.items() if v[1] == "Minha"}}
