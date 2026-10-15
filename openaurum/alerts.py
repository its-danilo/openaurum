"""Short pictures over a scene: a volume / brightness bar on the number row
and a light on Space when a message arrives (openaurum-notify).

  openaurum-cli bar volume|brightness 0-100   # Esc .. Backspace, gone 2 s after the last call
  openaurum-cli notify [--app NAME | --color '#rrggbb']   # Space, 5 s

Only while scenes drive the keyboard (a scene or an overlay in CustomLightning):
never over a built-in effect, in Cave Mode or with the scenes' brightness at 0.
Both follow the scenes' brightness. These writes come from the desktop, not
from the user, and the per-key table lives in flash, so they have a daily
budget (event_writes_per_day in config.conf, 500 by default); past it only the
scene is put back. The number row is one 06 12 chunk: a bar step is one write.

A call only records what to show in paths.ALERTS. The first caller that gets
paths.ALERTS_LOCK draws, at most every TICK_S (holding a volume key
coalesces), until everything expired and the scene is back; the others return.
"""

import fcntl
import json
import os
import time

from openaurum import integrations, paths
from openaurum import protocol as kb
from openaurum import scenes

BAR_S, SPACE_S, TICK_S = 2.0, 5.0, 0.12
# Esc .. Backspace: matrix indices 21-34, all inside the color table's chunk 0x38
ROW = [k for k, i in sorted(kb.KEY_INDEX.items(), key=lambda ki: ki[1]) if 21 <= i <= 34]
SPACE = "SPCE"
BAR_COLORS = {"brightness": "#ffb000"}  # volume: the theme accent
# messengers by app name or desktop entry (lowercase, substring); others: the accent.
# Colors for the LEDs, by eye: the brands' own carry too much blue there
# (WhatsApp's #25d366 shows cyan)
MESSENGERS = [
    ("zapzap", "#00ff00"), ("whatsapp", "#00ff00"),
    ("vesktop", "#3000ff"), ("discord", "#3000ff"), ("legcord", "#3000ff"),
    ("ayugram", "#0050ff"), ("telegram", "#0050ff"),
    ("signal", "#0020ff"), ("element", "#00ff30"),
]


def app_color(*names):
    """Color of a messenger, None when no name is one."""
    for name in names:
        name = (name or "").lower()
        for key, color in MESSENGERS:
            if key in name:
                return color
    return None


def _read():
    try:
        with open(paths.ALERTS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _edit(**entries):
    with open(paths.ALERTS + ".edit", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        st = {**_read(), **entries}
        with open(paths.ALERTS + ".tmp", "w") as f:
            json.dump(st, f)
        os.replace(paths.ALERTS + ".tmp", paths.ALERTS)


def _live():
    now = time.time()
    return {k: v for k, v in _read().items() if v.get("until", 0) > now}


def _scenes_on(auto=None):
    """Scenes own the keyboard (from their state file alone, no USB)."""
    st = scenes.load()
    return ((st["active"] or bool(st["overlays"])) and not st["cave_prev"]
            and st["brightness"] > 0 and (auto is None or st["auto"].get(auto, True)))


def bar(kind, value):
    if kind not in ("volume", "brightness"):
        raise ValueError(f"bar {kind!r} (volume / brightness)")
    if not _scenes_on("bar"):
        return
    _edit(bar={"kind": kind, "value": max(0, min(100, int(value))), "until": time.time() + BAR_S})
    run()


def notify(color=None):
    if not _scenes_on():
        return
    _edit(space={"color": color, "until": time.time() + SPACE_S})
    run()


def run():
    """Draw until everything expired, unless another process already does."""
    while _live():
        with open(paths.ALERTS_LOCK, "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return  # that one reads our entry on its next tick
            if not _draw():
                return
        # all expired, but an entry may have come in while letting go: look again


def _over(live, level):
    """{key: color} of what is live, at the scenes' brightness."""
    out = {}
    if "bar" in live:
        b = live["bar"]
        c = BAR_COLORS.get(b["kind"]) or integrations.theme_color()
        fill = b["value"] * len(ROW) / 100
        for i, key in enumerate(ROW):  # the last lit key shows the remainder
            out[key] = scenes.scale(c, max(0.0, min(1.0, fill - i)))
    if "space" in live:
        out[SPACE] = live["space"].get("color") or integrations.theme_color()
    return scenes.dim(out, level)


def _draw():
    """True when it ended because everything expired (and the scene is back),
    False when it gave up: the keyboard isn't the scenes' anymore, or the
    budget ran out."""
    base, shown = None, None
    while True:
        live = _live()
        with scenes._Session() as s:
            st = s.st
            if (not (st["active"] or st["overlays"]) or st["cave_prev"]
                    or s.kb().current_mode() != kb.CUSTOM):
                return False  # the scenes let go meanwhile (another effect, Cave)
            if base is None or not live:  # the scene under us (again for the way back)
                base = scenes.render(st)
            budget = integrations.event_budget()
            over = live and not (budget and kb.event_writes() >= budget)
            want = {k: base[k] for k in (*ROW, SPACE)}
            if over:
                want.update(_over(live, st["brightness"]))
            if want != shown:
                n = s.kb().push(want)
                kb.count_writes(0, events=n)
                shown = want
        if not live:
            return True
        if not over:
            return False  # out of budget: the scene is back
        time.sleep(TICK_S)
