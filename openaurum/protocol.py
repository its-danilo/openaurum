"""Pichau Aurum V60 (36ae:fe9c, SDCINNOVATION) lighting protocol, shared by
openaurum-cli and the openaurum app. docs/PROTOCOL.md has the long version.

Recorded from the official Pichau app with usbmon on 2026-09-18. Only the
commands the app itself sends are used, with values inside the ranges it sends:

  06 0a                         -> current mode at byte 7 (reply aa 0a ...; the
                                   reply is sometimes one byte shorter, so the
                                   settings come from 06 16)
  06 16 00 00 00 01 00 MM       -> stored settings of mode MM (reply aa 16 0b ...)
  06 0b 0b 00 00 01 00 MM BR SP X1 MO XX HH SS VV
                                -> switch to mode MM with these settings; the
                                   keyboard echoes them (aa 0b 01 ...)
     MM mode 0-16 (MODES)       BR brightness 0-4     SP speed 0-2 (0 = slowest)
     X1 01 once the app changed something (03 in factory settings)
     MO 1 = one color, 0 = RGB  XX 00 whenever the app sets a color
     HH SS VV color as HSV, each 0-255 (green = 55 ff ff)
     In one-color mode the firmware IGNORES BR (so did the Pichau app's slider)
     and lights the color at its V; with RGB BR works (0 = off). apply() turns
     a brightness level 0-10 into V (MONO_LEVELS, per mode).
     With MO=0 the HSV fields are ignored: the last one-color color stays stored.
     CustomLightning (16) ignores BR too (tested 2026-09-19, 4 -> 0: no change):
     openaurum.scenes dims the per-key colors on the PC instead (MONO_LEVELS[16]).
  06 13 3a LL HH                -> per-key colors, 0x38 bytes from address HHLL
                                   (reply aa 13 3a LL HH 00 00 00 + data); the app
                                   reads 0x000-0x150
  06 14 03 LL HH 00 00 00 RR GG BB
                                -> color of one key (CustomLightning), address
                                   = 3 * matrix index, plain RGB; echoed aa 14 01 ...
  06 08 3a LL HH                -> keymap (4 bytes per matrix index: 20 00 <HID
                                   usage> 00); KEY_INDEX below was read from it
  06 0f ff = factory reset, and firmware update: never sent from here

Talks to the vendor interface (input 2) through /dev/hidraw*, which the udev
rule /etc/udev/rules.d/70-openaurum.rules opens to the logged-in user. The
keyboard keeps its settings when unplugged.
"""

import colorsys
import glob
import os
import re
import select

from openaurum import paths

HID_ID = "0003:000036AE:0000FE9C"
REPORT = 64

MODES = [
    "LightOff", "Static", "Breath", "Spin", "ColorLoop", "Stream", "Bloom", "UDWave",
    "Cross", "Rain", "Meteor", "TrigSpread", "TrigSpread Reverse", "TrigSingle",
    "Sudoku", "Tide", "CustomLightning",
]
CUSTOM = 16  # per-key colors (set_key)
NO_MONO = {3, 4}  # Spin, ColorLoop: always RGB, the app has no one-color option
MAX_BRIGHTNESS, MAX_SPEED = 4, 2
# One-color brightness: 11 levels, 0 = off. The firmware ignores the BR byte in
# one color, so a level is the color's V (as a fraction of the picked color's V).
# LEDs are far from linear: calibrated by eye with the user on 2026-09-19 (red,
# full speed), lowest V that shows at all per mode: Static/Rain/TrigSingle/Sudoku
# 12, Bloom 12-16, UDWave/Cross/TrigSpread(+Reverse) 16, Breath/Stream/Meteor/Tide
# 35. Level 1 = that minimum, geometric up to 255 at level 10 (even steps to the eye).
# CustomLightning (16): the scenes' brightness, the brightest channel of a full key
# (rainbow scene, 2026-09-19: still lit and "bem baixinho" at 5).
MONO_STEPS = 10
MONO_MIN = {1: 12, 2: 35, 5: 35, 6: 16, 7: 16, 8: 16, 9: 12, 10: 35, 11: 16, 12: 16,
            13: 12, 14: 12, 15: 35, 16: 5}
MONO_LEVELS = {m: [0] + [round(v1 * (255 / v1) ** ((k - 1) / (MONO_STEPS - 1)))
                          for k in range(1, MONO_STEPS + 1)]
               for m, v1 in MONO_MIN.items()}
# RGB uses the keyboard's own brightness byte (0-4); in Stream its level 1 is off
RGB_OFF_AT_1 = {5}
# the level and picked color per mode (the keyboard only stores the dimmed V)
LEVELS_FILE = paths.LEVELS


def mono_levels(mode):
    return MONO_LEVELS.get(mode, MONO_LEVELS[1])


def is_mono(st):
    return bool(st["mono"]) and st["mode"] not in NO_MONO


def hw_brightness(level):
    """One-color level 0-10 -> the BR byte (kept meaningful for a switch to RGB)."""
    return 0 if level == 0 else max(1, round(level * MAX_BRIGHTNESS / MONO_STEPS))


def _levels_load():
    import json
    try:
        with open(LEVELS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _levels_save(mode, level, base, lit):
    import json
    d = _levels_load()
    d[str(mode)] = {"level": level, "base": list(base), "lit": list(lit)}
    os.makedirs(os.path.dirname(LEVELS_FILE), exist_ok=True)
    with open(LEVELS_FILE + ".tmp", "w") as f:
        json.dump(d, f)
    os.replace(LEVELS_FILE + ".tmp", LEVELS_FILE)


def level_info(st):
    """(level, picked color HSV) of stored settings. One color: level 0-10, from
    the levels file when it still matches what the keyboard holds, else a best
    guess (color at full V, nearest level); RGB: the BR byte 0-4."""
    if not is_mono(st):
        return st["br"], (st["h"], st["s"], st["v"])
    lit = [st["h"], st["s"], st["v"]]
    e = _levels_load().get(str(st["mode"]))
    if e and e.get("lit") == lit:
        return e["level"], tuple(e["base"])
    table = mono_levels(st["mode"])
    if st["v"] == 0:
        return 0, (st["h"], st["s"], 255)
    level = min(range(1, MONO_STEPS + 1), key=lambda k: abs(table[k] - st["v"]))
    return level, (st["h"], st["s"], min(255, round(st["v"] * 255 / table[level])))

# Aurum V60 (60% ABNT2 ISO), row by row: (xkb key, width in units), from
# colemak-layout. RTRN appears twice: ISO Enter spans two rows.
BOARD = [
    [("ESC", 1)] + [(f"AE{i:02}", 1) for i in range(1, 13)] + [("BKSP", 2)],
    [("TAB", 1.5)] + [(f"AD{i:02}", 1) for i in range(1, 13)] + [("RTRN", 1.5)],
    [("CAPS", 1.75)] + [(f"AC{i:02}", 1) for i in range(1, 12)] + [("BKSL", 1), ("RTRN", 1.25)],
    [("LFSH", 1.25), ("LSGT", 1)] + [(f"AB{i:02}", 1) for i in range(1, 12)] + [("RTSH", 1.75)],
    [("LCTL", 1.25), ("LWIN", 1.25), ("LALT", 1.25), ("SPCE", 6.25),
     ("RALT", 1.25), ("COMP", 1.25), ("RCTL", 1.25), ("FN", 1.25)],
]
# what is printed on the keycaps (ABNT2)
LABELS = dict(
    zip([f"AE{i:02}" for i in range(1, 13)], "1 2 3 4 5 6 7 8 9 0 - =".split()),
    **dict(zip([f"AD{i:02}" for i in range(1, 13)], "Q W E R T Y U I O P ´ [".split())),
    **dict(zip([f"AC{i:02}" for i in range(1, 12)], "A S D F G H J K L Ç ~".split())),
    **dict(zip([f"AB{i:02}" for i in range(1, 12)], "Z X C V B N M , . ; /".split())),
    ESC="Esc", BKSP="Bksp", TAB="Tab", CAPS="Caps", RTRN="Enter", BKSL="]", LFSH="Shift",
    LSGT="\\", RTSH="Shift", LCTL="Ctrl", LWIN="Super", LALT="Alt", SPCE="", RALT="AltGr",
    COMP="Menu", RCTL="Ctrl", FN="Fn",
)


# matrix index of each key (6 rows x 21 columns; the top row is the F-row a
# 60% doesn't have), from the keymap the keyboard reports (06 08) on
# 2026-09-18. Recorded writes confirmed ESC 21, AD01 43, AC01 64, SPCE 111.
KEY_INDEX = {
    "ESC": 21, **{f"AE{i:02}": 21 + i for i in range(1, 13)}, "BKSP": 34,
    "TAB": 42, **{f"AD{i:02}": 42 + i for i in range(1, 13)},
    "CAPS": 63, **{f"AC{i:02}": 63 + i for i in range(1, 12)}, "BKSL": 75, "RTRN": 76,
    "LFSH": 84, "LSGT": 85, **{f"AB{i:02}": 85 + i for i in range(1, 12)}, "RTSH": 97,
    "LCTL": 105, "LWIN": 106, "LALT": 107, "SPCE": 111,
    "RALT": 115, "COMP": 116, "RCTL": 117, "FN": 118,
}
COLOR_TABLE = range(0, 0x188, 0x38)  # the reads the app makes


class NotFound(Exception):
    pass


class ProtocolError(Exception):
    pass


def find_hidraw():
    for dev in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(f"{dev}/device/uevent") as f:
                uevent = dict(l.strip().split("=", 1) for l in f if "=" in l)
        except OSError:
            continue
        if uevent.get("HID_ID") == HID_ID and uevent.get("HID_PHYS", "").endswith("/input2"):
            return "/dev/" + os.path.basename(dev)
    return None


# One talker at a time. With two processes sending commands together (the app's
# 2 s poll + a wallpaper hook, say) the keyboard drops commands: a stress test
# lost ~25% of them, and a scene written halfway kept old colors. Every opener
# (app, CLI, hooks, heatmap) takes this lock; reentrant within a process.
LOCKFILE = paths.LOCK
_lock = {"file": None, "depth": 0}


def acquire():
    import fcntl
    if _lock["depth"] == 0:
        f = open(LOCKFILE, "w")
        fcntl.flock(f, fcntl.LOCK_EX)
        _lock["file"] = f
    _lock["depth"] += 1


def release():
    _lock["depth"] -= 1
    if _lock["depth"] == 0:
        _lock["file"].close()
        _lock["file"] = None


class Keyboard:
    """Open only while talking to the keyboard: `with Keyboard() as kb: ...`"""

    def __init__(self, path=None):
        acquire()
        self.fd = None
        try:
            path = path or find_hidraw()
            if not path:
                raise NotFound("Aurum V60 not found")
            self.path = path
            self.fd = os.open(path, os.O_RDWR)  # PermissionError: udev rule missing
        except BaseException:
            release()
            raise
        self.drain()

    def drain(self):
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, REPORT)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
            release()

    def cmd(self, data, expect, tries=3):
        # no report IDs on this interface: hidraw wants a leading 0
        for _ in range(tries):  # every command here is safe to repeat
            os.write(self.fd, b"\x00" + bytes(data) + bytes(REPORT - len(data)))
            for _ in range(8):
                if not select.select([self.fd], [], [], 0.5)[0]:
                    break
                reply = os.read(self.fd, REPORT)
                if reply[:2] == bytes([0xAA, expect]) and (expect != 0x14 or reply[3:5] == bytes(data[3:5])):
                    return reply
            self.drain()
        raise ProtocolError(f"no reply from the keyboard to {data[1]:02x}")

    def current_mode(self):
        return self.cmd([0x06, 0x0A], 0x0A)[7]

    def stored(self, mode):
        r = self.cmd([0x06, 0x16, 0, 0, 0, 1, 0, mode], 0x16)
        mode, br, sp, x1, mono, xx, h, s, v = r[7:16]
        return dict(mode=mode, br=br, sp=sp, x1=x1, mono=mono, xx=xx, h=h, s=s, v=v)

    def write(self, st):
        data = [0x06, 0x0B, 0x0B, 0, 0, 1, 0] + [
            st[k] for k in ("mode", "br", "sp", "x1", "mono", "xx", "h", "s", "v")]
        reply = self.cmd(data, 0x0B)
        if list(reply[7:16]) != data[7:16]:
            raise ProtocolError("the keyboard did not accept the settings")

    def key_colors(self):
        """{key: '#rrggbb'} as stored in the keyboard (CustomLightning)."""
        table = b""
        for a in COLOR_TABLE:
            r = self.cmd([0x06, 0x13, 0x3A, a & 0xFF, a >> 8], 0x13)
            if r[3] != a & 0xFF or r[4] != a >> 8:
                raise ProtocolError("color table reply out of order")
            table += bytes(r[8:8 + 0x38])
        return {k: "#" + table[3 * i:3 * i + 3].hex() for k, i in KEY_INDEX.items()}

    def set_key(self, key, color):
        addr = 3 * KEY_INDEX[key]
        c = color.strip().lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
            raise ValueError(f"bad color {color!r} (use #rrggbb)")
        data = [0x06, 0x14, 0x03, addr & 0xFF, addr >> 8, 0, 0, 0] + list(bytes.fromhex(c))
        reply = self.cmd(data, 0x14)
        if list(reply[3:11]) != data[3:11]:
            raise ProtocolError(f"the keyboard did not accept the color of {key}")

    def push(self, colors):
        """Write only the keys whose color differs from what the keyboard holds,
        and count the writes (WRITES). The per-key table most likely lives in
        flash (it survived a factory reset): keep this for events, not animation."""
        want = {k: c.lower() for k, c in colors.items() if k in KEY_INDEX}
        written = 0
        for _ in range(3):  # write, read back, rewrite what didn't take
            have = self.key_colors()
            todo = {k: c for k, c in want.items() if have.get(k) != c}
            if not todo:
                break
            for key, c in todo.items():
                self.set_key(key, c)
            written += len(todo)
        count_writes(written)
        return written

    def restore(self, st):
        """Write settings read by stored() back exactly. With MO=0 the HSV
        fields are ignored, so put the one-color color back first."""
        if not st["mono"]:
            self.write({**st, "mono": 1, "xx": 0})
        self.write(st)

    def state(self):
        st = self.stored(self.current_mode())
        lv, base = level_info(st)
        return dict(st, level=lv, base=base)

    def apply(self, mode=None, brightness=None, speed=None, color=None, rgb=False,
              remember=True):
        """Switch to `mode` (default: the current one), changing only what is
        given. color = '#rrggbb' or (h, s, v) 0-255; rgb = multicolor.
        brightness: 0-10 in one color (the color's V, see MONO_LEVELS), 0-4 in
        RGB (the keyboard's BR). remember=False: don't record the level (Cave).
        Returns the settings written, plus "level" and "base"."""
        if mode is None:
            mode = self.current_mode()
        if not 0 <= mode <= 16:
            raise ValueError(f"mode {mode}")
        st = self.stored(mode)
        was_mono = is_mono(st)
        level, base = level_info(st)
        if not was_mono:
            level = round(st["br"] * MONO_STEPS / MAX_BRIGHTNESS)  # RGB -> one color
        changed = False
        if rgb:
            st["mono"], changed = 0, True
            st["br"] = hw_brightness(level) if was_mono else st["br"]
        elif color is not None:
            if mode in NO_MONO:
                raise ValueError(f"{MODES[mode]} has no one-color option")
            base = hex_to_hsv(color) if isinstance(color, str) else tuple(color)
            st.update(mono=1, xx=0)
            changed = True
        mono = is_mono(st)
        if brightness is not None:
            top = MONO_STEPS if mono else MAX_BRIGHTNESS
            if not 0 <= brightness <= top:
                raise ValueError(f"brightness {brightness} (0-{top} in {'one color' if mono else 'RGB'})")
            if mono:
                level = brightness
            else:
                st["br"] = brightness
            changed = True
        if speed is not None:
            if not 0 <= speed <= MAX_SPEED:
                raise ValueError(f"speed {speed}")
            st["sp"], changed = speed, True
        if mono and (brightness is not None or color is not None):
            h, s_, v = base
            st.update(h=h, s=s_, v=round(v * mono_levels(mode)[level] / 255),
                      br=hw_brightness(level))
        if changed and mode in (0, CUSTOM):
            raise ValueError(f"{MODES[mode]}: settings not supported")
        if changed:
            st["x1"] = 1  # as the app does once anything changed
        # the app never goes past these; a stored value outside them is not ours to write
        if st["br"] > MAX_BRIGHTNESS or st["sp"] > MAX_SPEED or st["mono"] > 1:
            raise ProtocolError(f"unexpected stored settings for mode {mode}: {st}")
        self.write(st)  # mode 0 (LightOff): the stored settings as they are, like the app
        if mono and remember and (brightness is not None or color is not None):
            _levels_save(mode, level, base, (st["h"], st["s"], st["v"]))
        lv, bs = level_info(st)
        return dict(st, level=lv, base=bs)


WRITES = paths.WRITES


def count_writes(n):
    import datetime
    import json
    try:
        with open(WRITES) as f:
            w = json.load(f)
    except (OSError, ValueError):
        w = {}
    today = datetime.date.today().isoformat()
    if w.get("day") != today:
        w["day"], w["today"] = today, 0
    w["today"] = w.get("today", 0) + n
    w["total"] = w.get("total", 0) + n
    os.makedirs(os.path.dirname(WRITES), exist_ok=True)
    with open(WRITES + ".tmp", "w") as f:
        json.dump(w, f)
    os.replace(WRITES + ".tmp", WRITES)


def writes():
    import datetime
    import json
    try:
        with open(WRITES) as f:
            w = json.load(f)
    except (OSError, ValueError):
        return 0, 0
    today = w.get("today", 0) if w.get("day") == datetime.date.today().isoformat() else 0
    return today, w.get("total", 0)


def geometry():
    """{key: (x, y)} key centers in key units (15 x 5 board)."""
    out = {}
    for row, keys in enumerate(BOARD):
        x = 0.0
        for key, w in keys:
            if key == "RTRN":
                if row == 1:
                    out[key] = (x + w / 2, 1.0)  # ISO Enter spans rows 1-2
            else:
                out[key] = (x + w / 2, row + 0.5)
            x += w
    return out


def base_color(st):
    """The color the user picked, before brightness."""
    return hsv_to_hex(*level_info(st)[1])


def mode_number(name):
    """'breath', 'Breath', '2' -> 2"""
    if str(name).isdigit():
        return int(name)
    key = str(name).lower().replace(" ", "").replace("-", "")
    for i, m in enumerate(MODES):
        if m.lower().replace(" ", "") == key:
            return i
    raise ValueError(f"unknown mode {name!r}")


def hex_to_hsv(color):
    c = color.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        raise ValueError(f"bad color {color!r} (use #rrggbb)")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return round(h * 255) % 256, round(s * 255), round(v * 255)


def hsv_to_hex(h, s, v):
    r, g, b = colorsys.hsv_to_rgb(h / 255, s / 255, v / 255)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def vivid(color):
    """Same hue at full saturation and value: LEDs wash out pastel colors."""
    h, _, _ = hex_to_hsv(color)
    return hsv_to_hex(h, 255, 255)
