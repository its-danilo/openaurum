"""Files OpenAurum keeps, XDG style. Nothing is written outside these."""

import os

_home = os.path.expanduser("~")
STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(_home, ".local/state"),
                         "openaurum")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(_home, ".config"),
                          "openaurum")
RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"

SCENES = os.path.join(STATE_DIR, "scenes.json")    # scenes, overlays, scene brightness
LEVELS = os.path.join(STATE_DIR, "levels.json")    # one-color level + picked color per mode
WRITES = os.path.join(STATE_DIR, "writes.json")    # per-key writes counter (flash wear)
HEAT = os.path.join(STATE_DIR, "heat.json")        # typing heatmap counts
LOG = os.path.join(STATE_DIR, "openaurum.log")     # CLI errors (hooks discard output)
CONFIG = os.path.join(CONFIG_DIR, "config.conf")   # optional, see README
LOCK = os.path.join(RUNTIME_DIR, "openaurum.lock")
SCREEN = os.path.join(RUNTIME_DIR, "openaurum-screen")  # normal / night / cave
